"""Compare local vision pipelines on identical frames, without camera access."""
import json
import sys
import time
import types
from pathlib import Path
import numpy as np
import cv2

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from examwatch.config import Settings
from examwatch.vision import Vision

def measure(cls):
    vision = cls(Settings())
    image = cv2.imread(str(ROOT / '.tmp/fixtures/person1.jpg'))
    image = cv2.resize(image, (960, round(image.shape[0] * 960 / image.shape[1])))
    gallery = [dict(id='fixture', name='Fixture', embeddings=[vision.enrollment(image)])]
    times = []
    for i in range(40):
        start = time.perf_counter()
        tracks, _ = vision.process(image, gallery, now=100 + i * .12)
        times.append((time.perf_counter() - start) * 1000)
        assert tracks and tracks[0].student_id == 'fixture'
    result = dict(median_ms=round(float(np.median(times[3:])), 1),
                  p95_ms=round(float(np.percentile(times[3:], 95)), 1),
                  emotion=tracks[0].emotion, pose=bool(tracks[0].landmarks))
    vision.close()
    return result

if __name__ == '__main__':
    old = types.ModuleType('examwatch.vision_before')
    old.__package__ = 'examwatch'
    exec((ROOT / '.tmp/vision_before_speed.py').read_text(encoding='utf-8'), old.__dict__)
    report = {'before': measure(old.Vision), 'after': measure(Vision)}
    print(json.dumps(report))
    (ROOT / '.tmp/vision-speed.json').write_text(json.dumps(report, indent=2))
