"""Evaluate annotated, consented data; never mix numerical parity with accuracy."""
import argparse
import json
from pathlib import Path
import re
import sys
import time
import unicodedata

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "packages"))


def distance(a, b):
    row = list(range(len(b) + 1))
    for i, left in enumerate(a, 1):
        following = [i]
        for j, right in enumerate(b, 1):
            following.append(min(following[-1] + 1, row[j] + 1, row[j - 1] + (left != right)))
        row = following
    return row[-1]


def words(text):
    return re.findall(r"\w+", unicodedata.normalize("NFC", text).casefold())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("task", choices=["asr", "classification"])
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--models", default="models")
    parser.add_argument("--variant", choices=["base", "tiny"], default="base")
    parser.add_argument("--output", type=Path, default=Path("deliverables/verification/evaluation.json"))
    args = parser.parse_args()
    records = [json.loads(line) for line in args.dataset.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not records:
        raise SystemExit("Dataset is empty")
    report = {"samples": len(records), "task": args.task}
    if args.task == "asr":
        from examwatch.local.adapters import Transcriber
        model = Transcriber(args.models, args.variant)
        word_errors = character_errors = word_total = character_total = 0
        outputs = []
        for record in records:
            started = time.monotonic()
            prediction = model.transcribe(str(args.dataset.parent / record["path"]))
            reference_words, predicted_words = words(record["reference"]), words(prediction)
            reference_chars, predicted_chars = " ".join(reference_words), " ".join(predicted_words)
            word_errors += distance(reference_words, predicted_words)
            character_errors += distance(reference_chars, predicted_chars)
            word_total += len(reference_words)
            character_total += len(reference_chars)
            outputs.append({"path": record["path"], "prediction": prediction, "decode_seconds": time.monotonic() - started})
        report.update(model=model.version, wer=word_errors / max(1, word_total), cer=character_errors / max(1, character_total), outputs=outputs, normalization="Unicode NFC, lowercase, word/punctuation tokenization")
    else:
        labels = sorted({record["truth"] for record in records} | {record["prediction"] for record in records})
        scores = {}
        for label in labels:
            tp = sum(r["truth"] == label and r["prediction"] == label for r in records)
            fp = sum(r["truth"] != label and r["prediction"] == label for r in records)
            fn = sum(r["truth"] == label and r["prediction"] != label for r in records)
            precision, recall = tp / max(1, tp + fp), tp / max(1, tp + fn)
            scores[label] = {"precision": precision, "recall": recall, "f1": 2 * precision * recall / max(1e-12, precision + recall), "support": tp + fn}
        report.update(per_class=scores, macro_f1=sum(s["f1"] for s in scores.values()) / len(scores))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Evaluation written to", args.output)


if __name__ == "__main__":
    main()
