"""Optional synthetic 3-person smoke test from three supplied portrait files."""
from pathlib import Path
import argparse
import json
import sys
import time
import cv2
import numpy as np

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
from examwatch.config import Settings
from examwatch.vision import Vision


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('images',nargs=3)
    args=parser.parse_args()
    vision=Vision(Settings())
    canvas=np.zeros((720,960,3),dtype=np.uint8)
    gallery=[]
    for i,file in enumerate(args.images):
        original=cv2.imread(file)
        gallery.append(dict(id=str(i),name=f'Fixture {i}',embeddings=[vision.enrollment(original)]))
        h,w=original.shape[:2]
        scale=min(300/w,600/h)
        resized=cv2.resize(original,(round(w*scale),round(h*scale)))
        x=i*320+(320-resized.shape[1])//2
        y=(720-resized.shape[0])//2
        canvas[y:y+resized.shape[0],x:x+resized.shape[1]]=resized
    timings=[]
    for _ in range(5):
        begin=time.perf_counter()
        tracks,overflow=vision.process(canvas,gallery)
        timings.append((time.perf_counter()-begin)*1000)
    report=dict(detected=len(tracks),identified=sum(t.student_id is not None for t in tracks),
                poses=sum(bool(t.landmarks) for t in tracks),overflow=overflow,
                median_frame_ms=round(float(np.median(timings[1:])),1),synthetic_composite=True)
    assert report['detected']==3,report
    assert report['identified']==3,report
    (ROOT/'.tmp'/'three-person-smoke.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2))
    vision.close()


if __name__=='__main__':
    main()
