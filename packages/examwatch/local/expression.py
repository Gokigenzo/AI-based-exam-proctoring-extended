from collections import deque
import numpy as np


class ExpressionWindow:
    def __init__(self, labels, threshold=.7, hold=3, cooldown=15):
        self.labels = labels
        self.threshold, self.hold, self.cooldown = threshold, hold, cooldown
        self.samples = deque()
        self.last = -1e9

    def update(self, probabilities, timestamp, quality=True):
        if not quality or probabilities is None:
            self.samples.clear()
            return None
        if self.samples and timestamp - self.samples[-1][0] > 1:
            self.samples.clear()
        self.samples.append((timestamp, np.asarray(probabilities, dtype=float)))
        while self.samples and self.samples[0][0] < timestamp - self.hold - .5:
            self.samples.popleft()
        if timestamp - self.samples[0][0] < self.hold:
            return None
        average = np.mean([sample[1] for sample in self.samples], axis=0)
        index = int(average.argmax())
        if average[index] < self.threshold or self.labels[index].lower() in ("neutral", "happiness"):
            return None
        if any(int(sample[1].argmax()) != index for sample in self.samples):
            return None
        if timestamp - self.last < self.cooldown:
            return None
        self.last = timestamp
        return {"label": self.labels[index], "probabilities": {label: float(value) for label, value in zip(self.labels, average)}, "confidence": float(average[index])}


def associate_face(face_box, tracks):
    center = (np.asarray(face_box[:2]) + face_box[2:]) / 2
    candidates = []
    for track in tracks:
        points = track.observation.landmarks
        visible = points[:11][points[:11, 3] >= .5]
        if len(visible) < 3:
            continue
        head = visible[:, :2].mean(axis=0)
        scale = max(20, np.linalg.norm(points[11, :2] - points[12, :2]))
        distance = np.linalg.norm(center - head) / scale
        if distance < .6:
            candidates.append((distance, track.id))
    candidates.sort()
    if not candidates or (len(candidates) > 1 and candidates[1][0] - candidates[0][0] < .2):
        return None
    return candidates[0][1]
