"""Seed clearly marked, synthetic examples through the actual API + outbox."""
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import sys
from uuid import uuid4

import httpx
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "packages"))
from examwatch.local.store import Store
from examwatch.local.sync import Sync
from examwatch.api.security import DEMO_ROOM


def seed(base_url="http://127.0.0.1:8000"):
    root = Path("data/demo-seed")
    root.mkdir(parents=True, exist_ok=True)
    user = {"Authorization": "Bearer examwatch-local-demo"}
    with httpx.Client(timeout=30) as client:
        response = client.post(base_url + "/v1/devices", headers=user, json={"room_id": DEMO_ROOM, "name": "Máy demo · dữ liệu giả lập"})
        response.raise_for_status()
        token = response.json()["token"]
        sync = Sync(Store(root / (str(uuid4()) + ".sqlite3")), base_url, token, client)
        camera, mic, session = str(uuid4()), str(uuid4()), str(uuid4())
        sync.send("POST", "/v1/devices/heartbeat", {"sources": [{"id": camera, "kind": "camera", "name": "Camera demo"}, {"id": mic, "kind": "microphone", "name": "Microphone demo"}], "status": {"demo": True, "message": "Dữ liệu giả lập, không phải phát hiện từ camera"}})
        origin = datetime.now(timezone.utc) - timedelta(minutes=20)
        sync.store.enqueue("session", {"id": session, "name": "Ca thi thử · DỮ LIỆU GIẢ LẬP", "started_at": origin.isoformat(), "config": {"demo": True}})
        events = []
        for index, kind in enumerate(["standing", "side_lean", "speech_detected", "expression_observation", "turned", "rising"]):
            timestamp = (origin + timedelta(minutes=index * 2)).isoformat()
            event = {"id": str(uuid4()), "session_id": session, "source_id": mic if kind == "speech_detected" else camera, "track_id": None, "local_track_id": None, "kind": kind, "started_at": timestamp, "ended_at": timestamp, "model_version": "DEMO-SYNTHETIC", "model_confidence": None, "rule_score": None, "details": {"demo": True, "observation_only": True, "note": "Dữ liệu giả lập dùng kiểm thử giao diện"}}
            sync.store.enqueue("event", event)
            events.append(event)
        import cv2
        image = np.full((360, 640, 3), (56, 72, 38), dtype=np.uint8)
        cv2.putText(image, "EXAMWATCH / SYNTHETIC DEMO", (40, 160), cv2.FONT_HERSHEY_SIMPLEX, .8, (230, 245, 210), 2)
        cv2.putText(image, "No real camera recording", (40, 210), cv2.FONT_HERSHEY_SIMPLEX, .65, (230, 245, 210), 1)
        snapshot = root / "sample.jpg"
        snapshot.write_bytes(cv2.imencode(".jpg", image)[1].tobytes())
        import soundfile as sf
        audio = root / "sample.wav"
        sf.write(audio, np.sin(np.arange(16000) * 2 * np.pi * 440 / 16000) * .05, 16000, subtype="PCM_16")
        speech = {"id": str(uuid4()), "session_id": session, "source_id": mic, "event_id": events[2]["id"], "started_at": events[2]["started_at"], "ended_at": events[2]["ended_at"], "transcript_raw": "[Câu minh họa] Các em giữ trật tự trong phòng thi.", "model_version": "DEMO-SYNTHETIC", "processing_status": "DONE"}
        sync.store.enqueue("speech", speech)
        for event, path, content_type, speech_id in [(events[0], snapshot, "image/jpeg", None), (events[2], audio, "audio/wav", speech["id"])]:
            sync.store.enqueue("asset", {"id": str(uuid4()), "session_id": session, "event_id": event["id"], "speech_id": speech_id, "content_type": content_type, "size_bytes": path.stat().st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "local_path": str(path.resolve())})
        while sync.store.counts().get("pending", 0):
            if not sync.once():
                raise RuntimeError(sync.status)
        print("Seeded synthetic session through actual outbox/API/storage; session_id=" + session)


if __name__ == "__main__":
    seed()
