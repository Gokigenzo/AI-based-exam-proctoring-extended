"""Download upstream artifacts once; inference is offline and checksum-verified.

Usage: python scripts/prepare_models.py --root models --include pose yunet phowhisper-base fer-source
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "packages"))
from examwatch.local.adapters import LABELS


URLS = {
    "pose": ("pose_landmarker_lite.task", "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task", "mediapipe-pose-lite-float16-v1"),
    "yunet": ("face_detection_yunet_2023mar.onnx", "https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx", "opencv-yunet-2023mar"),
    "fer_params": ("fer-0000.params", "https://s3.amazonaws.com/mxnet-demo-models/models/fer/fer-0000.params", "TalkAI-FER+-VGG13"),
    "fer_symbol": ("fer-symbol.json", "https://s3.amazonaws.com/mxnet-demo-models/models/fer/fer-symbol.json", "TalkAI-FER+-VGG13"),
}


def checksum(path):
    digest = hashlib.sha256()
    if path.is_file():
        files = [path]
    else:
        files = sorted(file for file in path.rglob("*") if file.is_file())
    for file in files:
        if path.is_dir():
            digest.update(file.relative_to(path).as_posix().encode())
        with file.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
    return digest.hexdigest()


def prepare(root, include):
    root.mkdir(parents=True, exist_ok=True)
    manifest_path = root / "manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    failures = []
    names = [key for name in include for key in (["fer_params", "fer_symbol"] if name == "fer-source" else [name])]
    for name in names:
        try:
            if name in URLS:
                filename, url, version = URLS[name]
                target = root / filename
                if not target.exists() or name not in manifest or checksum(target) != manifest[name]["sha256"]:
                    temporary = target.with_suffix(target.suffix + ".download")
                    try:
                        with httpx.stream("GET", url, follow_redirects=True, timeout=120) as response:
                            response.raise_for_status()
                            with temporary.open("wb") as handle:
                                for block in response.iter_bytes(1024 * 1024):
                                    handle.write(block)
                        if temporary.stat().st_size < 100:
                            raise ValueError("Artifact unexpectedly small")
                        temporary.replace(target)
                    finally:
                        temporary.unlink(missing_ok=True)
                entry = {"path": filename, "version": version, "url": url, "sha256": checksum(target)}
            elif name in ("phowhisper-base", "phowhisper-tiny"):
                from huggingface_hub import HfApi, snapshot_download
                variant = name.split("-")[1]
                repo = "vinai/PhoWhisper-" + variant
                target = root / name
                revision = manifest.get(name, {}).get("revision") or HfApi().model_info(repo).sha
                snapshot_download(repo_id=repo, revision=revision, local_dir=target, allow_patterns=["*.json", "*.txt", "*.bin", "*.safetensors", "*.model"])
                # Download-cache bookkeeping is not part of an inference model artifact.
                import shutil
                shutil.rmtree(target / ".cache", ignore_errors=True)
                entry = {"path": name, "version": repo + "@" + revision, "revision": revision, "sha256": checksum(target)}
            else:
                raise ValueError("Unknown artifact: " + name)
            manifest[name] = entry
            temporary = manifest_path.with_suffix(".tmp")
            temporary.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
            temporary.replace(manifest_path)
            print(f"Ready: {name} {entry['sha256'][:12]}", flush=True)
        except Exception as error:
            failures.append(name)
            print(f"UNAVAILABLE {name}: {type(error).__name__}: {error}", flush=True)
    return failures


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("models"))
    parser.add_argument("--include", nargs="+", default=["pose", "yunet", "phowhisper-base", "fer-source"])
    args = parser.parse_args()
    raise SystemExit(bool(prepare(args.root, args.include)))
