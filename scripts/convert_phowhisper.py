"""One-time conversion only; run in the isolated converter environment."""
from pathlib import Path
import hashlib
import json
import os
import sys

ROOT=Path(__file__).resolve().parent.parent
# Reuse the already installed CTranslate2 wheel; conversion-only packages stay isolated.
sys.path.append(str(ROOT/'.venv/Lib/site-packages'))
os.environ.setdefault('HF_HOME',str(ROOT/'.tmp/huggingface'))
os.environ.setdefault('HF_HUB_DISABLE_XET','1')
os.environ.setdefault('HF_HUB_DISABLE_SYMLINKS_WARNING','1')


def main():
    from huggingface_hub import HfApi,snapshot_download
    from ctranslate2.converters import TransformersConverter
    from transformers import AutoTokenizer
    class CompatibleConverter(TransformersConverter):
        def load_model(self, model_class, model_name_or_path, **kwargs):
            # CTranslate2 4.8 uses the newer dtype spelling; pinned Transformers
            # 4.51 still expects torch_dtype. Keep this compatibility local to conversion.
            if "dtype" in kwargs:
                kwargs["torch_dtype"] = kwargs.pop("dtype")
            return super().load_model(model_class, model_name_or_path, **kwargs)
    repository='vinai/PhoWhisper-base'
    revision=HfApi().model_info(repository).sha
    source=snapshot_download(repository,revision=revision,
        local_dir=str(ROOT/'.tmp/phowhisper-source'),
        allow_patterns=['*.json','*.txt','*.safetensors','pytorch_model.bin'])
    output=ROOT/'models/whisper-phowhisper-base'
    if not (output/'model.bin').is_file():
        converter=CompatibleConverter(source,copy_files=['preprocessor_config.json'])
        converter.convert(str(output),quantization='int8',force=True)
        tokenizer=AutoTokenizer.from_pretrained(source)
        tokenizer.save_pretrained(str(output))
    records=[]
    for path in output.glob('*'):
        if path.is_file():
            records.append(dict(file=path.relative_to(ROOT/'models').as_posix(),
                repository=repository,revision=revision,quantization='int8',
                bytes=path.stat().st_size,sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
    manifest_path=ROOT/'models/manifest.json'
    manifest=json.loads(manifest_path.read_text(encoding='utf-8'))
    names={r['file'] for r in records}
    manifest['artifacts']=[r for r in manifest['artifacts'] if r['file'] not in names]+records
    manifest_path.write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    print(f'Converted {repository} to local INT8: {output}',flush=True)


if __name__=='__main__':
    main()
