"""Compare decoding choices without changing the running web model."""
import argparse
import json
from pathlib import Path
import random
import re
import sys
import time
import unicodedata

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from examwatch.speech import unreliable_segment


def normalize(text):
    text = unicodedata.normalize('NFC', text).lower()
    return ' '.join(re.findall(r'\w+', text))


def wer(refs, hyps):
    if isinstance(refs, str):
        refs, hyps = [refs], [hyps]
    errors = total = 0
    for ref, hyp in zip(refs, hyps):
        a, b = ref.split(), hyp.split()
        row = list(range(len(b)+1))
        for i, word in enumerate(a, 1):
            previous, row = row, [i]
            for j, other in enumerate(b, 1):
                row.append(min(row[-1]+1, previous[j]+1, previous[j-1]+(word != other)))
        errors += row[-1]
        total += len(a)
    return errors / max(1, total)


def main():
    from faster_whisper import WhisperModel
    from faster_whisper.audio import decode_audio
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--audio', type=Path, required=True)
    parser.add_argument('--reference', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    model = WhisperModel(str(ROOT / 'models/whisper-phowhisper-base'), device='cpu',
                         compute_type='int8', cpu_threads=2, local_files_only=True)
    common = dict(language='vi', beam_size=5, best_of=1, temperature=0,
                  condition_on_previous_text=False, vad_filter=True,
                  vad_parameters=dict(threshold=.6, min_speech_duration_ms=300,
                                      min_silence_duration_ms=500, speech_pad_ms=300),
                  no_speech_threshold=.6, log_prob_threshold=-1., compression_ratio_threshold=2.2,
                  repetition_penalty=1.15, no_repeat_ngram_size=3, max_new_tokens=128,
                  without_timestamps=True, word_timestamps=False)
    # Vocabulary only: never provide the user's expected sentence or answer sequence.
    context = 'Phòng thi, thí sinh, giám thị, đề thi, câu hỏi, đáp án, ý a, ý b, ý c, ý d.'
    variants = {
        'current': {},
        'natural_repetition': dict(repetition_penalty=1., no_repeat_ngram_size=0),
        'beam10': dict(beam_size=10),
        'exam_prompt': dict(initial_prompt=context),
        'exam_hotwords': dict(hotwords=context),
        'exam_prompt_natural': dict(initial_prompt=context, repetition_penalty=1., no_repeat_ngram_size=0),
        'no_vad': dict(vad_filter=False),
    }
    root = ROOT / 'Audio-dataset/vivos-small'
    rows = [json.loads(line) for line in (root/'splits/test.jsonl').read_text(encoding='utf-8').splitlines()]
    rows = random.Random(42).sample(rows, 30)
    clips = [('user', decode_audio(str(args.audio), sampling_rate=16000), args.reference)]
    clips += [(row['audio'], decode_audio(str(root/row['audio']), sampling_rate=16000), row['text']) for row in rows]
    report = dict(reference=args.reference, context=context, control_samples=len(rows), variants={})
    for name, override in variants.items():
        details = []
        for key, audio, ref in clips:
            start = time.perf_counter()
            segments, _ = model.transcribe(audio, **(common | override))
            text = ' '.join(s.text.strip() for s in segments if not unreliable_segment(s))
            details.append(dict(audio=key, reference=ref, prediction=text, seconds=time.perf_counter()-start))
        controls = details[1:]
        result = dict(user=details[0], user_wer=100*wer(normalize(args.reference),normalize(details[0]['prediction'])),
                      control_wer=100*wer([normalize(d['reference']) for d in controls],
                                          [normalize(d['prediction']) for d in controls]),
                      control_seconds=sum(d['seconds'] for d in controls), details=controls)
        report['variants'][name] = result
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print(name, json.dumps({k:v for k,v in result.items() if k!='details'},ensure_ascii=True),flush=True)


if __name__ == '__main__':
    main()
