"""Compare deployable INT8 models on the same held-out audio and decoding rules."""
import argparse
from datetime import datetime
import json
import random
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from scripts.train_stt import normalize, read_rows
from examwatch.config import Settings
from examwatch.speech import Speech

def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--dataset', type=Path, default=ROOT / 'Audio-dataset')
    parser.add_argument('--models', nargs='+', default=['phowhisper-base', 'phowhisper-vietsuper'])
    parser.add_argument('--samples', type=int, default=100)
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument('--chunk-seconds', type=float, default=0,
                        help='0 evaluates full clips; 8 approximates the web capture duration cap')
    parser.add_argument('--noise-snr', type=float, default=None,
                        help='Optional synthetic white-noise SNR in dB, identical for every compared model')
    parser.add_argument('--split', choices=['test', 'validation'], default='test')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.chunk_seconds < 0:
        parser.error('--chunk-seconds must be nonnegative')
    from faster_whisper.audio import decode_audio
    from jiwer import wer, cer
    import numpy as np
    rows = read_rows(args.dataset.resolve(), args.split)
    if args.samples:
        rows = random.Random(args.seed).sample(rows, min(args.samples, len(rows)))
    output = args.output or ROOT / 'training-runs' / f'evaluation-{datetime.now():%Y%m%d-%H%M%S}.json'
    if output.exists():
        raise FileExistsError(output)
    report = {'split': args.split, 'samples': len(rows), 'seed': args.seed,
              'chunk_seconds': args.chunk_seconds, 'noise_snr_db': args.noise_snr, 'models': {}}
    for name in args.models:
        speech = Speech(Settings(whisper_name=name))
        refs, hyps, details = [], [], []
        elapsed = duration = 0.0
        for row in rows:
            audio = decode_audio(str(args.dataset / row['audio']), sampling_rate=16000)
            if args.noise_snr is not None:
                rng = np.random.default_rng(args.seed + len(details))
                noise = rng.normal(size=len(audio)).astype(np.float32)
                rms = max(float(np.sqrt(np.mean(audio**2))), 1e-8)
                noise *= rms / (max(float(np.sqrt(np.mean(noise**2))), 1e-8) * 10**(args.noise_snr/20))
                audio = audio + noise
                audio /= max(1.0, float(np.max(np.abs(audio))) / .99)
            start = time.perf_counter()
            chunk_size = max(1, round(args.chunk_seconds * 16000)) if args.chunk_seconds else len(audio)
            text = ' '.join(s['text'] for offset in range(0, len(audio), chunk_size)
                            for s in speech.transcribe(audio[offset:offset + chunk_size], 16000))
            elapsed += time.perf_counter() - start
            duration += len(audio) / 16000
            refs.append(normalize(row['text']))
            hyps.append(normalize(text))  # Empty/rejected outputs count as errors.
            details.append({'audio': row['audio'], 'reference': row['text'], 'prediction': text})
            if len(details) % 10 == 0:
                print(f'{name}: {len(details)}/{len(rows)}', flush=True)
        report['models'][name] = dict(wer=100 * wer(refs, hyps), cer=100 * cer(refs, hyps),
            audio_seconds=duration, processing_seconds=elapsed, real_time_factor=elapsed / duration,
            empty_predictions=sum(not p for p in hyps), predictions=details)
        del speech
        print(f"{name}: WER={report['models'][name]['wer']:.2f}, RTF={report['models'][name]['real_time_factor']:.3f}", flush=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(output)

if __name__ == '__main__':
    main()
