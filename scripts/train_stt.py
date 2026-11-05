"""Fine-tune the FP32 PhoWhisper-base source; INT8 runtime weights are not trainable."""
import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import re
import unicodedata

ROOT = Path(__file__).resolve().parent.parent

def augment_audio(audio, rng):
    """Mild synthetic noise/echo, applied on demand without extra audio files."""
    import numpy as np
    if rng.random() < .5:
        return audio
    result = audio.copy()
    if rng.random() < .7:
        noise = rng.normal(size=len(audio)).astype(np.float32)
        power = max(float(np.sqrt(np.mean(audio**2))), 1e-6)
        noise *= power / (10 ** (rng.uniform(15, 30) / 20))
        result += noise
    if rng.random() < .5:
        delay = int(rng.uniform(.04, .18) * 16000)
        if len(result) > delay:
            result[delay:] += rng.uniform(.05, .18) * audio[:-delay]
    result *= rng.uniform(.7, 1.1)
    peak = float(np.max(np.abs(result)))
    return result / max(1.0, peak / .98)

def normalize(text):
    text = unicodedata.normalize('NFC', text).casefold()
    return ' '.join(re.sub(r'[^\w\s]', ' ', text).split())

def read_rows(root, split, limit=0):
    rows = []
    with (root / 'splits' / f'{split}.jsonl').open(encoding='utf-8') as source:
        for line in source:
            row = json.loads(line)
            # Never silently crop a long utterance while retaining its full text.
            if not normalize(row['text']) or not 0.3 <= float(row['duration']) <= 30:
                continue
            path = (root / row['audio']).resolve()
            if not path.is_relative_to(root.resolve()):
                raise ValueError('Audio path escapes dataset root')
            if not path.is_file():
                raise FileNotFoundError(f'{path}: run download_audio_dataset.py first')
            rows.append(row)
            if limit and len(rows) >= limit:
                break
    if not rows:
        raise ValueError(f'Empty {split} dataset')
    return rows

def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--dataset', type=Path, default=ROOT / 'Audio-dataset')
    parser.add_argument('--model', default='vinai/PhoWhisper-base')
    parser.add_argument('--revision', default='7ebdb9e88f5cc5271fb88f4d642c82ff9388650e')
    parser.add_argument('--output', type=Path, default=ROOT / 'training-runs/phowhisper-vietsuper')
    parser.add_argument('--epochs', type=float, default=3)
    parser.add_argument('--max-steps', type=int, default=-1)
    parser.add_argument('--batch-size', type=int, default=2)
    parser.add_argument('--gradient-accumulation', type=int, default=8)
    parser.add_argument('--learning-rate', type=float, default=1e-5)
    parser.add_argument('--eval-steps', type=int, default=500)
    parser.add_argument('--max-train-samples', type=int, default=0)
    parser.add_argument('--max-eval-samples', type=int, default=256)
    parser.add_argument('--freeze-encoder', action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument('--cpu', action='store_true')
    parser.add_argument('--resume', default=None, help='Checkpoint directory')
    parser.add_argument('--lora', action='store_true')
    parser.add_argument('--lora-rank', type=int, default=8)
    parser.add_argument('--augment', action='store_true')
    parser.add_argument('--early-stopping', type=int, default=0, help='Number of evaluation intervals without WER improvement')
    parser.add_argument('--precision', choices=['auto','fp16','bf16','fp32'], default='auto')
    args = parser.parse_args()
    import numpy as np
    import soundfile as sf
    import torch
    from scipy.signal import resample_poly
    from math import gcd
    from jiwer import wer, cer
    from transformers import (WhisperProcessor, WhisperForConditionalGeneration,
                              Seq2SeqTrainingArguments, Seq2SeqTrainer, set_seed)
    set_seed(42)
    if not args.cpu and not torch.cuda.is_available():
        raise RuntimeError('CUDA unavailable. Install prepare_training.ps1 or pass --cpu for a small smoke test.')
    if (args.output / 'final').exists():
        raise FileExistsError('Final output exists; choose a new --output directory')
    root = args.dataset.resolve()
    train_rows = read_rows(root, 'train', args.max_train_samples)
    eval_rows = read_rows(root, 'validation', args.max_eval_samples)
    if {r['source'] for r in train_rows} & {r['source'] for r in eval_rows}:
        raise ValueError('Source leakage between train and validation')
    processor = WhisperProcessor.from_pretrained(args.model, revision=args.revision,
                                                language='vi', task='transcribe',
                                                cache_dir=str(ROOT / '.tmp/huggingface-training'))
    model = WhisperForConditionalGeneration.from_pretrained(args.model, revision=args.revision,
                                                            cache_dir=str(ROOT / '.tmp/huggingface-training'))
    model.generation_config.language = 'vi'
    model.generation_config.task = 'transcribe'
    model.generation_config.forced_decoder_ids = None
    model.config.forced_decoder_ids = None
    model.config.use_cache = False
    model.generation_config.use_cache = True
    if args.freeze_encoder and not args.lora:
        model.freeze_encoder()
    if args.lora:
        from peft import LoraConfig, get_peft_model
        # Generic PeftModel forwards input_features; SEQ_2_SEQ_LM's text wrapper
        # injects input_ids which Whisper.forward does not accept.
        model = get_peft_model(model, LoraConfig(r=args.lora_rank,
            lora_alpha=2 * args.lora_rank, lora_dropout=.05,
            target_modules=['q_proj', 'v_proj'], bias='none'))
        model.print_trainable_parameters()

    class AudioRows(torch.utils.data.Dataset):
        # Extract one sample on demand, avoiding >100 GB of padded feature caches.
        def __init__(self, rows, training=False):
            self.rows = rows
            self.training = training
            self.rng = np.random.default_rng(42)
        def __len__(self):
            return len(self.rows)
        def __getitem__(self, index):
            row = self.rows[index]
            audio, rate = sf.read(str(root / row['audio']), dtype='float32', always_2d=True)
            audio = audio.mean(axis=1)
            if rate != 16000:
                divisor = gcd(rate, 16000)
                audio = resample_poly(audio, 16000 // divisor, rate // divisor).astype(np.float32)
            if not len(audio) or len(audio) > 480000 or not np.isfinite(audio).all():
                raise ValueError(f'Invalid audio length/data: {row["audio"]}')
            if args.augment and self.training:
                audio = augment_audio(audio, self.rng)
            labels = processor.tokenizer(' '.join(unicodedata.normalize('NFC', row['text']).lower().split())).input_ids
            if len(labels) > model.config.max_target_positions:
                raise ValueError(f'Transcript exceeds decoder limit: {row["audio"]}')
            inputs = processor.feature_extractor(audio, sampling_rate=16000, return_attention_mask=True)
            return dict(input_features=inputs.input_features[0],
                        attention_mask=inputs.attention_mask[0], labels=labels)

    @dataclass
    class Collator:
        def __call__(self, features):
            batch = processor.feature_extractor.pad(
                [{'input_features': f['input_features']} for f in features], return_tensors='pt')
            batch['attention_mask'] = torch.tensor(np.stack([f['attention_mask'] for f in features]))
            padded = processor.tokenizer.pad([{'input_ids': f['labels']} for f in features], return_tensors='pt')
            labels = padded.input_ids.masked_fill(padded.attention_mask.ne(1), -100)
            if (labels[:, 0] == model.config.decoder_start_token_id).all().item():
                labels = labels[:, 1:]
            batch['labels'] = labels
            return batch

    def metrics(prediction):
        ids = prediction.predictions
        if isinstance(ids, tuple):
            ids = ids[0]
        labels = np.where(prediction.label_ids == -100, processor.tokenizer.pad_token_id, prediction.label_ids)
        predicted = [normalize(t) for t in processor.batch_decode(ids, skip_special_tokens=True)]
        references = [normalize(t) for t in processor.batch_decode(labels, skip_special_tokens=True)]
        return {'wer': 100 * wer(references, predicted), 'cer': 100 * cer(references, predicted)}

    precision = args.precision
    if precision == 'auto':
        precision = 'fp32' if args.cpu else ('bf16' if torch.cuda.is_bf16_supported() else 'fp16')
    training = Seq2SeqTrainingArguments(
        output_dir=str(args.output), per_device_train_batch_size=args.batch_size,
        per_device_eval_batch_size=1, gradient_accumulation_steps=args.gradient_accumulation,
        learning_rate=args.learning_rate, warmup_ratio=.05, num_train_epochs=args.epochs,
        max_steps=args.max_steps, gradient_checkpointing=True,
        gradient_checkpointing_kwargs={'use_reentrant': False},
        fp16=precision == 'fp16', bf16=precision == 'bf16', use_cpu=args.cpu,
        eval_strategy='steps', save_strategy='steps',
        eval_steps=args.eval_steps, save_steps=args.eval_steps, logging_steps=10,
        save_total_limit=2, load_best_model_at_end=True, metric_for_best_model='wer',
        greater_is_better=False, predict_with_generate=True, generation_max_length=448,
        generation_num_beams=1, remove_unused_columns=False, dataloader_num_workers=0,
        dataloader_pin_memory=not args.cpu, report_to=[], seed=42, push_to_hub=False,
        label_names=['labels'])
    callbacks = []
    if args.early_stopping:
        from transformers import EarlyStoppingCallback
        callbacks.append(EarlyStoppingCallback(early_stopping_patience=args.early_stopping))
    trainer = Seq2SeqTrainer(model=model, args=training, processing_class=processor,
                            data_collator=Collator(), train_dataset=AudioRows(train_rows, training=True),
                            eval_dataset=AudioRows(eval_rows), compute_metrics=metrics, callbacks=callbacks)
    args.output.mkdir(parents=True, exist_ok=True)
    processor.save_pretrained(str(args.output / 'processor'))
    run = {k: str(v) if isinstance(v, Path) else v for k, v in vars(args).items()}
    status_path = root / 'download-status.json'
    dataset_metadata = json.loads(status_path.read_text(encoding='utf-8')) if status_path.exists() else json.loads((root / 'manifest.json').read_text(encoding='utf-8'))
    run.update(train_samples=len(train_rows), validation_samples=len(eval_rows),
               resolved_model_revision=getattr(model.config, '_commit_hash', None),
               actual_precision=precision,
               trainable_parameters=sum(p.numel() for p in model.parameters() if p.requires_grad),
               total_parameters=sum(p.numel() for p in model.parameters()),
               dataset_revision=dataset_metadata.get('revision', dataset_metadata.get('audio_sha256')),
               label_status=dataset_metadata.get('label_status', 'unspecified'),
               dataset_warning=dataset_metadata.get('warning'))
    (args.output / 'run.json').write_text(json.dumps(run, indent=2), encoding='utf-8')
    baseline = trainer.evaluate(metric_key_prefix='baseline')
    (args.output / 'baseline.json').write_text(json.dumps(baseline, indent=2), encoding='utf-8')
    trainer.train(resume_from_checkpoint=args.resume)
    final = trainer.evaluate(metric_key_prefix='finetuned')
    if args.lora:
        trainer.save_model(str(args.output / 'adapter'))
        model = model.merge_and_unload()
        model.save_pretrained(str(args.output / 'final'), safe_serialization=True)
    else:
        trainer.save_model(str(args.output / 'final'))
    processor.save_pretrained(str(args.output / 'final'))
    model.generation_config.save_pretrained(str(args.output / 'final'))
    trainer.save_state()
    report = {'baseline': baseline, 'finetuned': final,
              'improved_validation_wer': final['finetuned_wer'] < baseline['baseline_wer'],
              'note': 'Validation subset only. Test independence depends on dataset provenance; see run.json dataset_warning.'}
    (args.output / 'comparison.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2))

if __name__ == '__main__':
    main()
