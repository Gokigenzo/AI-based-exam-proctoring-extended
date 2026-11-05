"""Export a trained HF checkpoint to a separate, deployable CTranslate2 INT8 model."""
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--checkpoint', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=ROOT / 'models/whisper-phowhisper-vietsuper')
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError('Choose a new output directory; existing models are never overwritten')
    if not (args.checkpoint / 'config.json').is_file():
        raise FileNotFoundError('Expected a complete HF checkpoint, e.g. training-runs/.../final')
    from ctranslate2.converters import TransformersConverter
    from transformers import AutoTokenizer
    class CompatibleConverter(TransformersConverter):
        def load_model(self, model_class, model_name_or_path, **kwargs):
            if 'dtype' in kwargs:
                kwargs['torch_dtype'] = kwargs.pop('dtype')
            return super().load_model(model_class, model_name_or_path, **kwargs)
    CompatibleConverter(str(args.checkpoint), copy_files=['preprocessor_config.json']).convert(
        str(args.output), quantization='int8')
    AutoTokenizer.from_pretrained(str(args.checkpoint)).save_pretrained(str(args.output))
    artifacts = []
    for file in sorted(args.output.iterdir()):
        if file.is_file():
            artifacts.append(dict(file=file.name, bytes=file.stat().st_size,
                                  sha256=hashlib.sha256(file.read_bytes()).hexdigest()))
    from faster_whisper import WhisperModel
    model = WhisperModel(str(args.output), device='cpu', compute_type='int8', local_files_only=True)
    assert model is not None
    (args.output / 'training-export.json').write_text(json.dumps(
        dict(checkpoint=str(args.checkpoint.resolve()), quantization='int8', artifacts=artifacts,
             runtime_load_verified=True), indent=2), encoding='utf-8')
    print(f'Export verified: {args.output}. Test WER before choosing this model in start.ps1.')

if __name__ == '__main__':
    main()
