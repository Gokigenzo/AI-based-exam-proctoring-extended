"""Assemble assets into an already prepared embedded runtime; no personal data."""
import hashlib
import importlib.metadata
import json
from pathlib import Path
import shutil
import argparse

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'release/v1'


def main():
    global OUT
    parser=argparse.ArgumentParser()
    parser.add_argument('--version',choices=['v1','v2'],default='v1')
    version=parser.parse_args().version
    OUT=ROOT/'release'/version
    (OUT/'app').mkdir(exist_ok=True)
    for name in ['examwatch','web']:
        shutil.copytree(ROOT/name,OUT/'app'/name,dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    shutil.copy2(ROOT/'packaging/windows/portable_server.py',OUT/'app/portable_server.py')
    models=OUT/'models';models.mkdir(exist_ok=True)
    for name in ['yunet.onnx','sface.onnx','emotion.onnx','pose_lite.task']:
        shutil.copy2(ROOT/'models'/name,models/name)
    voice=models/'zipformer-vi-30m';voice.mkdir(exist_ok=True)
    for name in ['encoder.int8.onnx','decoder.onnx','joiner.int8.onnx','tokens.txt','bpe.model','source.json']:
        shutil.copy2(ROOT/'models/zipformer-vi-30m'/name,voice/name)
    checksums={p.relative_to(models).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
               for p in models.rglob('*') if p.is_file() and p.name!='checksums.json'}
    (models/'checksums.json').write_text(json.dumps(checksums,indent=2),encoding='utf-8')
    notices=OUT/'licenses';notices.mkdir(exist_ok=True)
    for name in ['deepface-MIT.txt','mediapipe-Apache-2.0.txt','sface-LICENSE.txt','yunet-LICENSE.txt']:
        shutil.copy2(ROOT/'licenses'/name,notices/name)
    shutil.copy2(OUT/'runtime/LICENSE.txt',notices/'Python-LICENSE.txt')
    packages=OUT/'runtime/Lib/site-packages'
    records=[]
    for dist in sorted(importlib.metadata.distributions(path=[str(packages)]),key=lambda d:d.metadata['Name'].lower()):
        name=dist.metadata['Name'];dependency_version=dist.version
        records.append(dict(name=name,version=dependency_version))
        dest=notices/'dependencies'/name
        for item in dist.files or []:
            rel=Path(str(item));parts=rel.parts
            if any('license' in part.lower() or 'notice' in part.lower() or 'copying' in part.lower() for part in parts[1:]):
                src=Path(dist.locate_file(item))
                if src.is_file():
                    dst=dest/Path(*parts[1:]);dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,dst)
        dest.mkdir(parents=True,exist_ok=True)
        (dest/'METADATA.txt').write_text(dist.read_text('METADATA') or '',encoding='utf-8')
    (OUT/'runtime-lock.json').write_text(json.dumps(records,indent=2),encoding='utf-8')
    (OUT/'VERSION.json').write_text(json.dumps(dict(version=version,platform='Windows x64',python='3.12.10',
        model='hynt/Zipformer-30M-RNNT-6000h original INT8',data='%LOCALAPPDATA%/ExamWatch/data',
        personal_data_included=False),indent=2),encoding='utf-8')
    (OUT/'licenses/MODEL_SOURCES.txt').write_text('''Zipformer: hynt/Zipformer-30M-RNNT-6000h
https://huggingface.co/hynt/Zipformer-30M-RNNT-6000h
License: CC-BY-NC-ND-4.0. Original INT8 release, no LoRA modifications.
Sherpa model release: https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-zipformer-vi-30M-int8-2026-02-09.tar.bz2
YuNet/SFace: OpenCV Zoo, https://github.com/opencv/opencv_zoo
Emotion: https://huggingface.co/serengil/deepface (facial_expression_model_weights.onnx)
Pose Lite: Google MediaPipe https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task
This release is a noncommercial offline demo; retain the upstream notices.
''',encoding='utf-8')
    print(f'Assembled {version}; models and runtime dependencies recorded')


if __name__=='__main__':main()
