"""Prepare timestamped DOCX + audio as a small Whisper dataset, preserving labels."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import re
import unicodedata
from zipfile import ZipFile
import xml.etree.ElementTree as ET

TIMESTAMP = re.compile(r'^(?:(\d+):)?(\d{1,2}):(\d{2})$')
NS = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}


def paragraphs(path):
    with ZipFile(path) as archive:
        root = ET.fromstring(archive.read('word/document.xml'))
    return [''.join(t.text or '' for t in p.findall('.//w:t', NS)).strip()
            for p in root.findall('.//w:p', NS)]


def cues(lines):
    result, headings = [], []
    for line in lines:
        match = TIMESTAMP.fullmatch(line)
        if match:
            h, m, s = match.groups()
            if int(s) >= 60 or (h and int(m) >= 60):
                raise ValueError(f'Invalid timestamp: {line}')
            start = int(h or 0)*3600 + int(m)*60 + int(s)
            if result and start <= result[-1]['start']:
                raise ValueError(f'Non-increasing timestamp: {line}')
            result.append(dict(start=start, lines=[]))
        elif line:
            # DOCX section headings are metadata, not spoken transcription.
            if line in {'Định Nghĩa', 'Định nghĩa'} or not result:
                headings.append(line)
            else:
                result[-1]['lines'].append(line)
    return result, headings


def clean(text):
    return ' '.join(unicodedata.normalize('NFC', text).replace('\u200b', '').lower().split())


def main():
    import numpy as np
    import soundfile as sf
    from faster_whisper.audio import decode_audio
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--input', type=Path, default=Path('transcripts'))
    parser.add_argument('--output', type=Path, default=Path('Audio-dataset/transcripts-tiny'))
    args = parser.parse_args()
    audio_files = [p for p in args.input.iterdir() if p.suffix.lower() in {'.mp3','.wav','.flac','.m4a'}]
    docs = list(args.input.glob('*.docx'))
    if len(audio_files) != 1 or len(docs) != 1:
        raise ValueError('Expected exactly one audio and one DOCX')
    if args.output.exists():
        raise FileExistsError('Choose a new output folder; never overwrite prepared labels')
    audio_path, doc = audio_files[0], docs[0]
    parsed, headings = cues(paragraphs(doc))
    audio = decode_audio(str(audio_path), sampling_rate=16000)
    duration = len(audio)/16000
    if not parsed or parsed[-1]['start'] >= duration:
        raise ValueError('Transcript timestamps exceed audio duration')
    # Merge complete cues only. Never cut long audio and retain the complete label.
    groups, pending = [], None
    for index, cue in enumerate(parsed):
        end = parsed[index+1]['start'] if index+1 < len(parsed) else duration
        if pending and end-pending['start'] > 24:
            groups.append(pending)
            pending = None
        if pending is None:
            pending = dict(start=cue['start'], end=end, text=' '.join(cue['lines']))
        else:
            pending['end'] = end
            pending['text'] += ' ' + ' '.join(cue['lines'])
    if pending:
        groups.append(pending)
    out = args.output
    (out/'audio').mkdir(parents=True)
    (out/'splits').mkdir()
    (out/'transcript-extracted.txt').write_text('\n'.join(paragraphs(doc)), encoding='utf-8')
    rows, rejected, review = {s:[] for s in ['train','validation','test']}, [], []
    seen = set()
    # Contiguous time blocks with 20-second guards; one speaker/recording only.
    boundaries = (duration*.8, duration*.9)
    for index, group in enumerate(groups):
        start, end = group['start'], group['end']
        raw, text = group['text'], clean(group['text'])
        clip = audio[round(start*16000):round(end*16000)]
        reason = None
        if not text or not 1 <= len(clip)/16000 <= 30:
            reason = 'empty_label_or_invalid_duration'
        elif any(start < point+20 and end > point-20 for point in boundaries):
            reason = 'split_guard'
        elif float(np.sqrt(np.mean(clip**2))) < .002:
            reason = 'quiet'
        digest = hashlib.sha256(clip.tobytes()).hexdigest()
        if digest in seen:
            reason = 'duplicate_audio'
        seen.add(digest)
        if reason:
            rejected.append(dict(**group,reason=reason))
            continue
        split = 'train' if end < boundaries[0] else ('validation' if end < boundaries[1] else 'test')
        key = f'lecture_{index:04d}'
        relative = f'audio/{key}.flac'
        sf.write(str(out/relative),clip,16000,format='FLAC',subtype='PCM_16')
        row = dict(audio=relative,text=text,duration=len(clip)/16000,
                   source=f'lecture-temporal-{split}', recording=audio_path.name,
                   start=start,end=end,label_status='unreviewed',sha256=digest)
        rows[split].append(row)
        review.append(dict(id=key,split=split,start=start,end=end,text=text,
                           original_text=raw,reviewed='no',audio=relative,
                           note='Check timestamp boundaries, words, numbers and spoken letter names'))
    for split, values in rows.items():
        (out/'splits'/f'{split}.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in values),encoding='utf-8')
    with (out/'review.csv').open('w',encoding='utf-8-sig',newline='') as target:
        writer = csv.DictWriter(target,fieldnames=list(review[0]))
        writer.writeheader()
        writer.writerows(review)
    summary = dict(audio=str(audio_path.resolve()),docx=str(doc.resolve()),seconds=duration,
                   audio_sha256=hashlib.sha256(audio_path.read_bytes()).hexdigest(),
                   docx_sha256=hashlib.sha256(doc.read_bytes()).hexdigest(),
                   timestamps=len(parsed),excluded_headings=headings,
                   splits={s:dict(clips=len(v),minutes=sum(r['duration'] for r in v)/60) for s,v in rows.items()},
                   rejected=rejected, label_status='unreviewed',
                   warning='Timestamp labels are not forced-aligned or manually verified. Same recording and speaker in all splits; not independent generalization evaluation.')
    (out/'manifest.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in summary.items() if k!='rejected'},ensure_ascii=True))


if __name__ == '__main__':
    main()
