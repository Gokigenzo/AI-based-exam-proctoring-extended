"""Portable backend entry point. Never downloads models or installs dependencies."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import traceback

PACKAGE = Path(__file__).resolve().parent.parent


def main():
    version=json.loads((PACKAGE/'VERSION.json').read_text(encoding='utf-8'))['version']
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8000)
    parser.add_argument('--token', default='')
    parser.add_argument('--self-test', action='store_true')
    args = parser.parse_args()
    if not args.self_test and len(args.token) < 32:
        raise ValueError('Launcher authentication token required')
    home = Path(os.environ.get('EXAMWATCH_HOME', str(Path(os.environ['LOCALAPPDATA'])/'ExamWatch')))
    home.mkdir(parents=True, exist_ok=True)
    logs = home/'logs'; logs.mkdir(exist_ok=True)
    os.environ.update(EXAMWATCH_DATA=str(home/'data'),EXAMWATCH_MODELS=str(PACKAGE/'models'),
        EXAMWATCH_WHISPER='zipformer-vi-30m',EXAMWATCH_THREADS='2',OMP_NUM_THREADS='2',
        OPENBLAS_NUM_THREADS='2',HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',
        MPLCONFIGDIR=str(home/'cache/matplotlib'))
    for name,digest in json.loads((PACKAGE/'models/checksums.json').read_text()).items():
        path=PACKAGE/'models'/name
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=digest:
            raise RuntimeError('Model missing or damaged: '+name)
    from examwatch.config import Settings
    from examwatch.runtime import Runtime
    from examwatch.speech import Speech
    from examwatch.main import create_app
    import numpy as np
    import uvicorn
    runtime=Runtime(Settings.load())
    served=False
    try:
        runtime.load_vision()
        runtime.speech=Speech(runtime.settings)
        runtime.vision.process(np.zeros((480,640,3),dtype=np.uint8),[])
        assert runtime.speech.transcribe(np.zeros(16000,dtype=np.float32),16000)==[]
        if args.self_test:
            print(json.dumps(dict(ok=True,version=version,python=sys.version,model=runtime.settings.whisper_name,
                models=runtime.model_status(),data=str(home/'data')),ensure_ascii=True),flush=True)
            return
        app=create_app(runtime=runtime)
        server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=args.port,workers=1,
                                            access_log=False,log_level='info'))
        from fastapi import Request, HTTPException
        # Evaluate Request annotation in module globals for FastAPI.
        globals()['Request']=Request
        def authenticate(request):
            import secrets
            if not secrets.compare_digest(request.headers.get('x-examwatch-launcher',''),args.token):
                raise HTTPException(403)
        @app.get('/_launcher/health',include_in_schema=False)
        def health(request: Request):
            authenticate(request)
            return {'ready':True,'version':version,'model':'zipformer-vi-30m'}
        @app.post('/_launcher/shutdown',include_in_schema=False)
        def shutdown(request: Request):
            authenticate(request)
            server.should_exit=True
            return {'stopping':True}
        served=True
        server.run()
    finally:
        # create_app lifespan owns shutdown after uvicorn has started.
        if not served:
            runtime.close()


if __name__=='__main__':
    try:main()
    except Exception:
        traceback.print_exc()
        sys.exit(1)
