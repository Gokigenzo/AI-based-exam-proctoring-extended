import argparse
import json
from pathlib import Path
import sys
import time
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "packages"))
from examwatch.local.adapters import PoseAdapter, FERAdapter, Transcriber, VAD

parser = argparse.ArgumentParser()
parser.add_argument("--root", default="models")
parser.add_argument("--speech", help="An optional real 16 kHz mono WAV for ASR smoke testing")
args = parser.parse_args()
report = {}
for name, load in [("pose", lambda: PoseAdapter(args.root)), ("fer", lambda: FERAdapter(args.root)), ("asr", lambda: Transcriber(args.root)), ("vad", VAD)]:
    try:
        started = time.monotonic()
        model = load()
        report[name] = {"loaded": True, "load_seconds": round(time.monotonic() - started, 3)}
        if name == "pose":
            report[name]["blank_frame_people"] = len(model.predict(np.zeros((720, 1280, 3), np.uint8), 0))
            model.close()
        if name == "fer":
            report[name]["blank_frame_faces"] = len(model.predict(np.zeros((720, 1280, 3), np.uint8)))
        if name == "vad":
            report[name]["silence_is_speech"] = model(np.zeros(512, np.float32))
        if name == "asr" and args.speech:
            started = time.monotonic()
            report[name]["transcript"] = model.transcribe(args.speech)
            report[name]["decode_seconds"] = time.monotonic() - started
    except Exception as error:
        report[name] = {"loaded": False, "error": f"{type(error).__name__}: {error}"}
path = Path("deliverables/verification")
path.mkdir(parents=True, exist_ok=True)
(path / "models.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(report, ensure_ascii=True, indent=2))
raise SystemExit(not all(item["loaded"] for item in report.values()))
