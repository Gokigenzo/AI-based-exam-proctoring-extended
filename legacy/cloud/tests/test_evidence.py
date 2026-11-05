import json
import time
from uuid import uuid4
import numpy as np

from examwatch.local.evidence import Evidence
from examwatch.local.store import Store


def test_h264_event_clip_ring_and_snapshot(tmp_path):
    store = Store(tmp_path / "local.db")
    evidence = Evidence(tmp_path / "evidence", store, fps=5)
    event = {"id": str(uuid4()), "session_id": str(uuid4())}
    frame = np.full((120, 160, 3), 100, dtype=np.uint8)
    for i in range(26):
        evidence.frame(i / 5, frame)
    evidence.trigger(event, 5)
    for i in range(26, 77):
        evidence.frame(i / 5, frame)
    evidence.close()
    assert evidence.error is None
    with store.connect() as db:
        rows = [json.loads(row["payload"]) for row in db.execute("SELECT payload FROM outbox WHERE kind='asset'")]
    assert {row["content_type"] for row in rows} == {"image/jpeg", "video/mp4"}
    import cv2
    video = next(row for row in rows if row["content_type"] == "video/mp4")
    capture = cv2.VideoCapture(video["local_path"])
    try:
        assert capture.isOpened()
        duration = capture.get(cv2.CAP_PROP_FRAME_COUNT) / capture.get(cv2.CAP_PROP_FPS)
        assert 14.5 <= duration <= 15.5
    finally:
        capture.release()


def test_local_retention_never_deletes_unsynced_files(tmp_path):
    root = tmp_path / "evidence"
    root.mkdir()
    pending, ready = root / "pending.wav", root / "ready.wav"
    pending.write_bytes(b"pending")
    ready.write_bytes(b"ready")
    store = Store(tmp_path / "local.db")
    store.enqueue("asset", {"local_path": str(ready)}, key="ready")
    store.enqueue("asset", {"local_path": str(pending)}, key="pending")
    with store.connect() as db:
        db.execute("UPDATE outbox SET created=?", (time.time() - 31 * 86400,))
        db.execute("UPDATE outbox SET state='done' WHERE key='ready'")
    store.cleanup_local(root)
    assert not ready.exists() and pending.exists()
