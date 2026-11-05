"""Stream VIVOS archive; retain only a small speaker-separated FLAC subset."""
import argparse
from collections import Counter
import gzip
import hashlib
import io
import json
from pathlib import Path
import random
import re
import tarfile
import unicodedata

ROOT = Path(__file__).resolve().parent.parent
REPO = 'AILAB-VNUHCM/vivos'
REVISION = '3cbfb2502e5e84776b4b778b020a09759f723f52'

def quotas(speakers, total):
    return {s: total // len(speakers) + (i < total % len(speakers)) for i, s in enumerate(speakers)}

def clean_text(text):
    return ' '.join(unicodedata.normalize('NFC', text).lower().split())

def finalize(root, rows, args):
    counts = {s: len(v) for s, v in rows.items()}
    requested = dict(train=args.train, validation=args.validation, test=args.test)
    if any(counts[s] < .9 * requested[s] for s in requested):
        raise RuntimeError(f'Not enough valid samples: {counts}')
    speakers = {s: {r['source'] for r in v} for s, v in rows.items()}
    assert not (speakers['train'] & speakers['validation'] or speakers['train'] & speakers['test']
                or speakers['validation'] & speakers['test'])
    total_bytes = 0
    for samples in rows.values():
        for row in samples:
            path = (root / row['audio']).resolve()
            if not path.is_relative_to(root) or not path.is_file():
                raise ValueError('Invalid local audio path')
            total_bytes += path.stat().st_size
    report = dict(repository=REPO, revision=REVISION, complete=True, counts=counts,
        requested=requested, bytes=total_bytes,
        hours={s: sum(r['duration'] for r in v)/3600 for s, v in rows.items()},
        license='CC-BY-NC-SA-4.0', source_archive_retained=False,
        note='VIVOS was used in PhoWhisper pretraining. Split separation applies only to this fine-tuning run; no room-domain accuracy claim.')
    (root / 'download-status.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2))

def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'Audio-dataset/vivos-small')
    parser.add_argument('--train', type=int, default=1500)
    parser.add_argument('--validation', type=int, default=100)
    parser.add_argument('--test', type=int, default=100)
    parser.add_argument('--max-mib', type=int, default=300)
    parser.add_argument('--finalize-existing', action='store_true')
    args = parser.parse_args()
    import numpy as np
    import requests
    import soundfile as sf
    from huggingface_hub import hf_hub_url
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=True)
    if args.finalize_existing:
        rows = {s: [json.loads(line) for line in (root / 'splits' / f'{s}.jsonl').read_text(encoding='utf-8').splitlines()]
                for s in ('train', 'validation', 'test')}
        finalize(root, rows, args)
        return
    if (root / 'download-status.json').exists():
        status = json.loads((root / 'download-status.json').read_text(encoding='utf-8'))
        if status.get('complete'):
            print('Dataset already prepared:', root)
            return
    http = requests.Session()
    records = {}
    train_speakers = set()
    test_speakers = set()
    for split, speakers in [('train', train_speakers), ('test', test_speakers)]:
        url = hf_hub_url(REPO, f'data/prompts-{split}.txt.gz', repo_type='dataset', revision=REVISION)
        response = http.get(url, timeout=60)
        response.raise_for_status()
        for line in gzip.decompress(response.content).decode('utf-8').splitlines():
            sample_id, text = line.split(' ', 1)
            if not re.fullmatch(r'[A-Za-z0-9_]+', sample_id):
                raise ValueError('Unsafe sample ID')
            text = clean_text(text)
            if not 3 <= len(text.split()) <= 55:
                continue
            speaker = sample_id.split('_')[0]
            speakers.add(speaker)
            records[sample_id] = dict(id=sample_id, text=text, source=speaker)
    speakers = sorted(train_speakers)
    random.Random(42).shuffle(speakers)
    validation_speakers, training_speakers = speakers[:5], speakers[5:]
    assert not train_speakers & test_speakers
    assignment = {s: split for split, group in [('train', training_speakers),
                  ('validation', validation_speakers), ('test', sorted(test_speakers))] for s in group}
    targets = {**quotas(training_speakers, args.train), **quotas(validation_speakers, args.validation),
               **quotas(sorted(test_speakers), args.test)}
    kept = Counter()
    rows = {s: [] for s in ('train', 'validation', 'test')}
    seen = set()
    audio_dir = root / 'audio/vivos'
    audio_dir.mkdir(parents=True, exist_ok=True)
    total_bytes = 0
    url = hf_hub_url(REPO, 'data/vivos.tar.gz', repo_type='dataset', revision=REVISION)
    print('Streaming ~1.47 GB source archive; archive is not saved. Keeping <=300 MiB subset.', flush=True)
    with http.get(url, stream=True, timeout=(30, 180)) as response:
        response.raise_for_status()
        with tarfile.open(fileobj=response.raw, mode='r|gz') as archive:
            for member in archive:
                if not member.isfile() or not member.name.endswith('.wav'):
                    continue
                sample_id = Path(member.name).stem
                row = records.get(sample_id)
                if not row or kept[row['source']] >= targets[row['source']]:
                    continue
                if member.size > 16000 * 2 * 31 + 4096:
                    continue
                audio, rate = sf.read(io.BytesIO(archive.extractfile(member).read()), dtype='float32')
                if audio.ndim != 1 or rate != 16000 or not 1 <= len(audio)/rate <= 8:
                    continue
                if not np.isfinite(audio).all() or float(np.sqrt(np.mean(audio**2))) < .003:
                    continue
                if float(np.mean(np.abs(audio) >= .999)) > .01:
                    continue
                fingerprint = hashlib.sha256(audio.tobytes()).hexdigest()
                if fingerprint in seen:
                    continue
                seen.add(fingerprint)
                target = audio_dir / f'{sample_id}.flac'
                sf.write(str(target), audio, rate, subtype='PCM_16')
                total_bytes += target.stat().st_size
                if total_bytes > args.max_mib * 1024**2:
                    target.unlink()
                    raise RuntimeError('Subset exceeded size cap; reduce sample count')
                kept[row['source']] += 1
                split = assignment[row['source']]
                rows[split].append(dict(audio=target.relative_to(root).as_posix(), text=row['text'],
                    source=row['source'], duration=len(audio)/rate, sha256=fingerprint))
                if sum(kept.values()) % 100 == 0:
                    print(f'Kept {sum(kept.values())} samples; {total_bytes/1024**2:.1f} MiB', flush=True)
                if all(kept[s] >= count for s, count in targets.items()):
                    break
    split_dir = root / 'splits'
    split_dir.mkdir(exist_ok=True)
    for split, samples in rows.items():
        random.Random(42).shuffle(samples)
        with (split_dir / f'{split}.jsonl').open('w', encoding='utf-8') as out:
            for row in samples:
                out.write(json.dumps(row, ensure_ascii=False) + '\n')
    finalize(root, rows, args)

if __name__ == '__main__':
    main()
