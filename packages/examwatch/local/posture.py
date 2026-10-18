from dataclasses import dataclass
import math
import numpy as np


def joint_angle(a, b, c):
    u, v = np.asarray(a) - b, np.asarray(c) - b
    denominator = np.linalg.norm(u) * np.linalg.norm(v)
    if denominator < 1e-6:
        return None
    return math.degrees(math.acos(float(np.clip(np.dot(u, v) / denominator, -1, 1))))


def features(points):
    # MediaPipe indices, deliberately separate from COCO-17.
    required = [11, 12, 23, 24]
    if any(points[index, 3] < .5 for index in required):
        return None
    shoulder = points[[11, 12], :2].mean(axis=0)
    hip = points[[23, 24], :2].mean(axis=0)
    length = np.linalg.norm(shoulder - hip)
    if length < 15:
        return None
    tilt = math.degrees(math.atan2(abs(shoulder[0] - hip[0]), hip[1] - shoulder[1]))
    knees = []
    for a, b, c in ((23, 25, 27), (24, 26, 28)):
        if min(points[[a, b, c], 3]) >= .5:
            value = joint_angle(points[a, :2], points[b, :2], points[c, :2])
            if value is not None:
                knees.append(value)
    # Relative head displacement is only an observed turn proxy, not gaze estimation.
    nose = points[0]
    head_offset = float((nose[0] - shoulder[0]) / length) if nose[3] >= .6 else None
    return {"hip_x": float(hip[0]), "hip_y": float(hip[1]), "shoulder_y": float(shoulder[1]), "length": float(length), "tilt": tilt, "knee": float(np.mean(knees)) if knees else None, "head_offset": head_offset}


@dataclass
class Baseline:
    hip_x: float
    hip_y: float
    shoulder_y: float
    length: float
    knee: float | None
    head_offset: float | None
    tilt: float

    @classmethod
    def from_samples(cls, samples):
        values = {}
        for name in cls.__dataclass_fields__:
            available = [sample[name] for sample in samples if sample[name] is not None]
            values[name] = float(np.median(available)) if available else None
        return cls(**values)


class PostureState:
    def __init__(self, hold=1.5, cooldown=10):
        self.hold, self.cooldown = hold, cooldown
        self.state = "UNKNOWN"
        self.candidate, self.since = "UNKNOWN", 0
        self.last_timestamp = None
        self.last_alert = {}

    def classify(self, sample, baseline):
        if sample is None or baseline is None:
            return "UNKNOWN"
        rise = (baseline.hip_y - sample["hip_y"]) / baseline.length
        shoulder_rise = (baseline.shoulder_y - sample["shoulder_y"]) / baseline.length
        shift = abs(sample["hip_x"] - baseline.hip_x) / baseline.length
        # Hysteresis on entry/exit; knees are mandatory for standing/rising.
        if sample["knee"] is not None:
            if rise > (.35 if self.state == "STANDING" else .5) and sample["knee"] > (140 if self.state == "STANDING" else 155):
                return "STANDING"
            if min(rise, shoulder_rise) > (.12 if self.state == "RISING" else .22):
                return "RISING"
        elif rise > .15:
            return "UNKNOWN"
        if sample["tilt"] > (18 if self.state == "SIDE_LEAN" else 28) or shift > (.25 if self.state == "SIDE_LEAN" else .4):
            return "SIDE_LEAN"
        if sample["head_offset"] is not None and baseline.head_offset is not None:
            if abs(sample["head_offset"] - baseline.head_offset) > (.3 if self.state == "TURNED" else .45):
                return "TURNED"
        return "SEATED"

    def update(self, sample, baseline, timestamp):
        candidate = self.classify(sample, baseline)
        if self.last_timestamp is not None and timestamp - self.last_timestamp > .75:
            self.candidate, self.since = "UNKNOWN", timestamp
        self.last_timestamp = timestamp
        if candidate == "UNKNOWN":
            self.state, self.candidate, self.since = "UNKNOWN", "UNKNOWN", timestamp
            return None
        if candidate != self.candidate:
            self.candidate, self.since = candidate, timestamp
        if timestamp - self.since < self.hold:
            return None
        changed = self.state != candidate
        self.state = candidate
        if candidate != "SEATED" and (changed or timestamp - self.last_alert.get(candidate, -1e9) >= 15):
            if timestamp - self.last_alert.get(candidate, -1e9) >= self.cooldown:
                self.last_alert[candidate] = timestamp
                return candidate
        return None
