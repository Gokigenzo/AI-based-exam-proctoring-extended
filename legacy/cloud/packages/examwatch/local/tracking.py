from dataclasses import dataclass
import numpy as np
from scipy.optimize import linear_sum_assignment


def iou(a, b):
    left, top = np.maximum(a[:2], b[:2])
    right, bottom = np.minimum(a[2:], b[2:])
    intersection = max(0, right - left) * max(0, bottom - top)
    area = lambda box: max(0, box[2] - box[0]) * max(0, box[3] - box[1])
    return intersection / max(1, area(a) + area(b) - intersection)


@dataclass
class Observation:
    landmarks: np.ndarray  # 33 x 4, pixel x/y, z, visibility
    box: np.ndarray

    @property
    def center(self):
        return (self.box[:2] + self.box[2:]) / 2


class KalmanTrack:
    def __init__(self, identifier, observation, timestamp):
        self.id, self.observation, self.last_seen = identifier, observation, timestamp
        self.x = np.r_[observation.center, 0., 0.]
        self.p = np.eye(4) * 100
        self.predicted_at = timestamp

    def predict(self, timestamp):
        dt = max(0, timestamp - self.predicted_at)
        f = np.array([[1, 0, dt, 0], [0, 1, 0, dt], [0, 0, 1, 0], [0, 0, 0, 1]])
        self.x = f @ self.x
        self.p = f @ self.p @ f.T + np.eye(4) * max(1, dt * 10)
        self.predicted_at = timestamp

    def update(self, observation, timestamp):
        h = np.eye(2, 4)
        gain = self.p @ h.T @ np.linalg.inv(h @ self.p @ h.T + np.eye(2) * 16)
        self.x += gain @ (observation.center - h @ self.x)
        self.p = (np.eye(4) - gain @ h) @ self.p
        points = observation.landmarks.copy()
        valid = (points[:, 3] >= .5) & (self.observation.landmarks[:, 3] >= .5)
        points[valid, :3] = .4 * points[valid, :3] + .6 * self.observation.landmarks[valid, :3]
        self.observation = Observation(points, observation.box)
        self.last_seen = timestamp


class Tracker:
    def __init__(self, max_age=1.5):
        self.tracks = []
        self.next_id = 1
        self.max_age = max_age

    def update(self, observations, timestamp):
        self.tracks = [track for track in self.tracks if timestamp - track.last_seen <= self.max_age]
        for track in self.tracks:
            track.predict(timestamp)
        costs = np.ones((len(self.tracks), len(observations))) * 100
        for i, track in enumerate(self.tracks):
            for j, obs in enumerate(observations):
                scale = max(40, np.linalg.norm(obs.box[2:] - obs.box[:2]))
                distance = np.linalg.norm(track.x[:2] - obs.center) / scale
                valid = (obs.landmarks[:, 3] > .5) & (track.observation.landmarks[:, 3] > .5)
                pose_distance = 1.
                if valid.sum() >= 4:
                    a = obs.landmarks[valid, :2] - obs.center
                    b = track.observation.landmarks[valid, :2] - track.observation.center
                    pose_distance = min(1, np.linalg.norm(a - b, axis=1).mean() / scale)
                if distance < .6:
                    costs[i, j] = .55 * distance + .25 * (1 - iou(track.observation.box, obs.box)) + .2 * pose_distance
        assigned, result = set(), []
        if costs.size:
            rows, columns = linear_sum_assignment(costs)
            for i, j in zip(rows, columns):
                cost = costs[i, j]
                competitors = np.r_[np.delete(costs[i], j), np.delete(costs[:, j], i)]
                if cost > .65 or (competitors.size and competitors.min() - cost < .08):
                    continue  # Ambiguity must not silently preserve an identity.
                track = self.tracks[i]
                track.update(observations[j], timestamp)
                assigned.add(j)
                result.append(track)
        for j, obs in enumerate(observations):
            if j not in assigned:
                track = KalmanTrack(self.next_id, obs, timestamp)
                self.next_id += 1
                self.tracks.append(track)
                result.append(track)
        return result
