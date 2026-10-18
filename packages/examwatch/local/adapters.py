"""Optional inference dependencies are loaded only when a source starts."""
import hashlib
import json
from pathlib import Path
import subprocess

import numpy as np

from .tracking import Observation


LABELS = ["neutral", "happiness", "surprise", "sadness", "anger", "disgust", "fear", "contempt"]


def checked_model(root, name):
    root = Path(root)
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    entry = manifest[name]
    path = (root / entry["path"]).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError("Model path outside registry")
    if path.is_file():
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
    else:
        digest = hashlib.sha256()
        for file in sorted(path.rglob("*")):
            if file.is_file():
                digest.update(file.relative_to(path).as_posix().encode())
                with file.open("rb") as handle:
                    for block in iter(lambda: handle.read(1024 * 1024), b""):
                        digest.update(block)
        actual = digest.hexdigest()
    if not path.exists() or actual != entry["sha256"]:
        raise ValueError(f"Missing or corrupt model: {name}; run prepare_models.py")
    return path, entry


class PoseAdapter:
    def __init__(self, root):
        import mediapipe as mp
        path, entry = checked_model(root, "pose")
        # Native Windows fopen in MediaPipe fails on Vietnamese paths; use model bytes.
        options = mp.tasks.vision.PoseLandmarkerOptions(base_options=mp.tasks.BaseOptions(model_asset_buffer=path.read_bytes()), running_mode=mp.tasks.vision.RunningMode.VIDEO, num_poses=4, min_pose_detection_confidence=.5, min_pose_presence_confidence=.5, min_tracking_confidence=.5)
        self.mp = mp
        self.model = mp.tasks.vision.PoseLandmarker.create_from_options(options)
        self.version = entry["version"]
        self.last_ms = -1

    def predict(self, frame, milliseconds):
        import cv2
        milliseconds = max(int(milliseconds), self.last_ms + 1)
        self.last_ms = milliseconds
        image = self.mp.Image(image_format=self.mp.ImageFormat.SRGB, data=cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        result = self.model.detect_for_video(image, milliseconds)
        height, width = frame.shape[:2]
        observations = []
        for person in result.pose_landmarks:
            points = np.array([[point.x * width, point.y * height, point.z * width, min(point.visibility, point.presence)] for point in person])
            visible = points[points[:, 3] >= .5, :2]
            if len(visible) >= 4:
                observations.append(Observation(points, np.r_[visible.min(axis=0), visible.max(axis=0)]))
        return observations

    def close(self):
        self.model.close()


def fer_normalize(gray):
    """TalkAI: histogram equalization, plane fitting, unit standard deviation.

    Crop/resize to 64x64 occurs before this function, as in training process_data.py.
    """
    height, width = gray.shape
    y, x = np.mgrid[:height, :width]
    a = np.stack([np.ones(width * height), x.ravel(), y.ravel()], axis=1)
    flat = gray.ravel().astype(int)
    histogram = np.bincount(flat, minlength=256)
    cdf = histogram.cumsum()
    equalized = (cdf * (2.0 / cdf[-1]) - 1.0)[flat]
    diff = equalized - a @ (np.linalg.pinv(a) @ equalized)
    std = np.sqrt(diff @ diff / len(diff))
    if std > 1e-6:
        diff /= std
    return diff.astype(np.float32).reshape(1, 1, height, width)


class FERAdapter:
    def __init__(self, root):
        import cv2
        import onnxruntime as ort
        path, entry = checked_model(root, "fer")
        if entry.get("labels") != LABELS or not entry.get("parity_verified"):
            raise ValueError("FER export requires original label order and passing parity report")
        self.version = entry["version"]
        self.output = entry.get("output", "logits")
        options = ort.SessionOptions()
        options.intra_op_num_threads = 2
        self.model = ort.InferenceSession(str(path), sess_options=options, providers=["CPUExecutionProvider"])
        self.input_name = self.model.get_inputs()[0].name
        detector, _ = checked_model(root, "yunet")
        self.detector = cv2.FaceDetectorYN.create("onnx", np.frombuffer(detector.read_bytes(), dtype=np.uint8), np.empty(0, dtype=np.uint8), (320, 320), .85, .3, 5000)

    def predict(self, frame):
        import cv2
        height, width = frame.shape[:2]
        self.detector.setInputSize((width, height))
        _, faces = self.detector.detect(frame)
        results = []
        for face in faces if faces is not None else []:
            x, y, w, h = face[:4]
            box = np.array([max(0, x), max(0, y), min(width, x + w), min(height, y + h)]).astype(int)
            left_eye, right_eye, nose = face[4:6], face[6:8], face[8:10]
            middle = (left_eye + right_eye) / 2
            frontal = abs(nose[0] - middle[0]) < .22 * w
            quality = bool(w >= 48 and h >= 48 and frontal and face[-1] >= .85)
            if not quality:
                results.append((box, None, False))
                continue
            crop = frame[box[1]:box[3], box[0]:box[2]]
            if crop.size == 0:
                continue
            # Match TalkAI's image_utils.crop_img: bilinear affine sampling,
            # reflected boundary, uint8 range, followed by its normalization.
            from scipy.ndimage import affine_transform
            gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
            scale = np.diag([(gray.shape[0] - 1) / 63, (gray.shape[1] - 1) / 63])
            gray = affine_transform(gray, scale, output_shape=(64, 64), order=1, mode="reflect", prefilter=False)
            tensor = fer_normalize(gray)
            output = self.model.run(None, {self.input_name: tensor})[0].reshape(-1)
            if self.output == "logits":
                output = np.exp(output - output.max())
                output /= output.sum()
            if output.shape != (8,) or not np.isfinite(output).all():
                raise ValueError("Invalid FER output")
            results.append((box, output, True))
        return results


class LegacyFER:
    """Persistent JSON-lines worker in a separate, explicitly configured Python runtime."""
    def __init__(self, python, script, root):
        checked_model(root, "fer_params")
        checked_model(root, "fer_symbol")
        self.process = subprocess.Popen([python, str(script), str(root)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, bufsize=1)

    def predict_tensor(self, tensor):
        self.process.stdin.write(json.dumps(tensor.tolist()) + "\n")
        self.process.stdin.flush()
        response = self.process.stdout.readline()
        if not response:
            raise RuntimeError("MXNet worker terminated")
        result = json.loads(response)
        if "error" in result:
            raise RuntimeError(result["error"])
        return np.array(result["probabilities"])

    def close(self):
        self.process.terminate()
        self.process.wait(timeout=5)


class Transcriber:
    def __init__(self, root, variant="base"):
        import torch
        torch.set_num_threads(2)
        from transformers import pipeline
        path, entry = checked_model(root, "phowhisper-" + variant)
        self.version = entry["version"]
        self.pipeline = pipeline("automatic-speech-recognition", model=str(path), device=-1)

    def transcribe(self, path):
        import soundfile as sf
        samples, rate = sf.read(path, dtype="float32")
        if rate != 16000 or samples.ndim != 1:
            raise ValueError("Expected mono 16 kHz audio")
        return self.pipeline({"array": samples, "sampling_rate": rate}, generate_kwargs={"language": "vi", "task": "transcribe"})["text"].strip()


class VAD:
    def __init__(self):
        import torch
        from silero_vad import load_silero_vad
        torch.set_num_threads(1)
        self.torch = torch
        self.model = load_silero_vad(onnx=True)

    def __call__(self, block):
        return float(self.model(self.torch.from_numpy(block.copy()), 16000)) >= .5
