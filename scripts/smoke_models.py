"""Exercise real local models on supplied fixtures; never downloads test data."""
import argparse
import json
from pathlib import Path
import sys
import time
import socket

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--image',required=True)
    parser.add_argument('--audio')
    parser.add_argument('--language',default='vi')
    args=parser.parse_args()
    import cv2
    import numpy as np
    from examwatch.config import Settings
    from examwatch.vision import Vision
    from examwatch.speech import Speech
    # Prove model initialization/inference does not require an internet connection.
    def no_network(*a,**kw):
        raise RuntimeError('Network access attempted during offline inference')
    socket.create_connection=no_network
    socket.socket.connect=no_network
    settings=Settings.load()
    vision=Vision(settings)
    image=cv2.imread(args.image)
    vector=vision.enrollment(image)
    gallery=[dict(id='fixture',name='Fixture',embeddings=[vector])]
    times=[]
    for _ in range(6):
        begin=time.perf_counter()
        rows,_=vision.process(image,gallery)
        times.append((time.perf_counter()-begin)*1000)
    assert rows and rows[0].student_id=='fixture'
    assert rows[0].emotion in {'angry','disgust','fear','happy','sad','surprise','neutral','unknown'}
    report=dict(offline_network_blocked=True,embedding_dimensions=len(vector),
                face_count=len(rows),identity=rows[0].student_id,emotion=rows[0].emotion,
                pose_detected=bool(rows[0].landmarks),warm_frame_ms_median=round(float(np.median(times[1:])),1))
    vision.close()
    speech=Speech(settings)
    assert speech.transcribe(np.zeros(16000,dtype=np.float32),16000)==[]
    if args.audio:
        from faster_whisper.audio import decode_audio
        audio=decode_audio(args.audio)
        begin=time.perf_counter()
        segments,_=speech.model.transcribe(audio,language=args.language,beam_size=1,vad_filter=True)
        segments=list(segments)
        assert segments
        report.update(audio_seconds=round(len(audio)/16000,2),
                      asr_seconds=round(time.perf_counter()-begin,2),
                      asr_text=' '.join(s.text for s in segments),fixture_language=args.language)
    print(json.dumps(report,ensure_ascii=True,indent=2))
    (ROOT/'.tmp'/'model-smoke.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')


if __name__=='__main__':
    main()
