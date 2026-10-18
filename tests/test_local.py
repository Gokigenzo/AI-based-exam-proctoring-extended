import json
from pathlib import Path
import numpy as np
from uuid import uuid4

from examwatch.local.store import Store
from examwatch.local.sync import Sync
from examwatch.local.speech import Segmenter, remove_overlap, speech_allowed
from examwatch.local.posture import joint_angle, features, Baseline, PostureState
from examwatch.local.tracking import Tracker, Observation
from examwatch.local.expression import ExpressionWindow


def test_outbox_restart_order_and_retry(tmp_path):
    store = Store(tmp_path / "outbox.db")
    store.enqueue("event", {"id": "first"}, key="first")
    store.enqueue("event", {"id": "first"}, key="first")
    store.enqueue("event", {"id": "second"}, key="second")
    store = Store(tmp_path / "outbox.db")
    row = store.peek()
    assert json.loads(row["payload"])["id"] == "first"
    store.fail(row["seq"], "offline")
    assert store.peek() is None
    assert store.counts()["pending"] == 2
    store.ack(row["seq"])
    assert json.loads(store.peek()["payload"])["id"] == "second"


def test_outbox_to_api_end_to_end(api, event, tmp_path):
    store = Store(tmp_path / "local.db")
    store.enqueue("event", event, key=event["id"])
    sync = Sync(store, "http://testserver", api.device_token, client=api)
    assert sync.once()
    assert store.counts()["done"] == 1
    # Simulate a crash before local acknowledgement: replay exact same event.
    store.enqueue("event", event, key="replay")
    assert sync.once()
    assert len(api.get(f"/v1/events?session_id={api.session_id}", headers=api.user_headers).json()["items"]) == 1


def test_audio_samples_silence_long_segments_and_overlap():
    segmenter = Segmenter(max_seconds=1, overlap=.2, silence=.1)
    block = np.zeros(512, dtype=np.float32)
    for _ in range(3):
        assert segmenter.push(block, False) is None
    segment = None
    for _ in range(32):
        segment = segmenter.push(block, True) or segment
    assert segment.start_sample == 1536 and len(segment.samples) >= 16000
    second = segmenter.flush()
    assert second.continuation and second.start_sample == segment.end_sample - 3200
    assert remove_overlap("các em giữ trật tự", "giữ trật tự trong phòng thi") == "trong phòng thi"
    assert speech_allowed(10, 20, [[0, 30]]) and not speech_allowed(10, 40, [[0, 30]])


def test_posture_hysteresis_missing_points_and_hold():
    sample = {"hip_x": 100., "hip_y": 200., "shoulder_y": 100., "length": 100., "tilt": 0., "knee": 90., "head_offset": 0.}
    base = Baseline.from_samples([sample] * 20)
    state = PostureState()
    standing = {**sample, "hip_y": 140., "shoulder_y": 40., "knee": 170.}
    assert state.update(standing, base, 0) is None
    assert state.update(standing, base, .5) is None
    assert state.update(standing, base, 1) is None
    assert state.update(standing, base, 1.5) == "STANDING"
    assert state.classify({**standing, "knee": None}, base) == "UNKNOWN"
    assert state.update(None, base, 2) is None and state.state == "UNKNOWN"
    assert abs(joint_angle(np.array([0, 0]), np.array([0, 1]), np.array([1, 1])) - 90) < .001
    assert joint_angle(np.zeros(2), np.zeros(2), np.ones(2)) is None
    assert features(np.zeros((33, 4))) is None


def observation(x):
    points = np.zeros((33, 4))
    points[:, 0] = x
    points[:, 1] = np.arange(33) * 3
    points[:, 3] = 1
    return Observation(points, np.array([x - 20, 0, x + 20, 100.]))


def test_tracking_short_motion_and_ambiguous_crossing():
    tracker = Tracker()
    ids = [track.id for track in tracker.update([observation(100), observation(300)], 0)]
    assert [track.id for track in tracker.update([observation(105), observation(295)], .2)] == ids
    tracker.update([], 3)
    assert tracker.update([observation(105)], 3.2)[0].id not in ids
    tracker = Tracker()
    old = [track.id for track in tracker.update([observation(100), observation(102)], 0)]
    new = [track.id for track in tracker.update([observation(101), observation(101)], .2)]
    assert not set(old) & set(new)


def test_expression_requires_continuity_and_quality():
    labels = ["neutral", "fear"]
    window = ExpressionWindow(labels)
    for timestamp in np.arange(0, 3, .5):
        assert window.update([.1, .9], timestamp) is None
    assert window.update([.1, .9], 3)["label"] == "fear"
    assert window.update([.1, .9], 4) is None
    window.update(None, 5, False)
    assert not window.samples


def test_recover_interrupted_speech_job(tmp_path):
    path = tmp_path / "local.db"
    store = Store(path)
    store.add_speech({"id": "job", "processing_status": "QUEUED"}, "speech.wav")
    assert store.claim_speech()["id"] == "job"
    store = Store(path)
    assert store.claim_speech()["id"] == "job"
