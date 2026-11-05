"""Approve an exported TalkAI model only after numerical parity succeeds."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import numpy as np
import onnxruntime as ort

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "packages"))
from examwatch.local.adapters import LABELS

parser = argparse.ArgumentParser()
parser.add_argument("--root", type=Path, default=Path("models"))
parser.add_argument("--fixtures", type=Path, required=True)
args = parser.parse_args()
samples = np.load(args.fixtures)
reference = np.load(args.root / "fer_reference.npy")
if samples.ndim != 4 or samples.shape[1:] != (1, 64, 64) or len(samples) < 100:
    raise SystemExit("At least 100 preprocessed fixture faces (N,1,64,64) required")
session = ort.InferenceSession(str(args.root / "fer.onnx"), providers=["CPUExecutionProvider"])
logits = np.concatenate([session.run(None, {session.get_inputs()[0].name: sample[None].astype(np.float32)})[0] for sample in samples])
probabilities = np.exp(logits - logits.max(axis=1, keepdims=True))
probabilities /= probabilities.sum(axis=1, keepdims=True)
if reference.shape != probabilities.shape or not np.isfinite(probabilities).all():
    raise SystemExit("Invalid comparison shapes or probabilities")
match = float((reference.argmax(axis=1) == probabilities.argmax(axis=1)).mean())
maximum = float(abs(reference - probabilities).max())
report = {"samples": len(samples), "label_agreement": match, "max_probability_error": maximum, "passed": match >= .99 and maximum <= .001, "fixtures_sha256": hashlib.sha256(args.fixtures.read_bytes()).hexdigest()}
(args.root / "fer_parity.json").write_text(json.dumps(report, indent=2))
print(json.dumps(report))
if not report["passed"]:
    raise SystemExit(1)
manifest_path = args.root / "manifest.json"
manifest = json.loads(manifest_path.read_text())
manifest["fer"] = {"path": "fer.onnx", "sha256": hashlib.sha256((args.root / "fer.onnx").read_bytes()).hexdigest(), "labels": LABELS, "version": "TalkAI-FER+-VGG13-onnx", "output": "logits", "parity_verified": True, "source_params_sha256": manifest["fer_params"]["sha256"], "parity_report": report}
manifest_path.write_text(json.dumps(manifest, indent=2))
