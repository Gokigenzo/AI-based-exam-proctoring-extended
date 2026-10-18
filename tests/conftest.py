from datetime import datetime, timezone
from uuid import uuid4
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from examwatch.api.config import Settings
from examwatch.api.main import create_app
from examwatch.api.security import DEMO_ROOM


def pytest_sessionstart(session):
    Path(".cache").mkdir(exist_ok=True)


@pytest.fixture
def api(tmp_path):
    config = Settings(_env_file=None, env="test", database_url=f"sqlite:///{tmp_path / 'api.sqlite3'}", data_dir=tmp_path / "cloud", signing_secret="a" * 40, demo_token="demo-test", supabase_url="", supabase_key="")
    app = create_app(config)
    with TestClient(app) as client:
        client.user_headers = {"Authorization": "Bearer demo-test"}
        response = client.post("/v1/devices", headers=client.user_headers, json={"room_id": DEMO_ROOM, "name": "Test device"})
        assert response.status_code == 200, response.text
        registration = response.json()
        client.device_id = registration["id"]
        client.device_headers = {"Authorization": "Bearer " + registration["token"]}
        client.device_token = registration["token"]
        client.camera_id, client.mic_id = str(uuid4()), str(uuid4())
        response = client.post("/v1/devices/heartbeat", headers=client.device_headers, json={"sources": [{"id": client.camera_id, "kind": "camera", "name": "camera"}, {"id": client.mic_id, "kind": "microphone", "name": "mic"}], "status": {}})
        assert response.status_code == 200, response.text
        client.session_id = str(uuid4())
        client.timestamp = datetime.now(timezone.utc).isoformat()
        response = client.post("/v1/sessions", headers=client.device_headers, json={"id": client.session_id, "name": "Test session", "started_at": client.timestamp, "config": {}})
        assert response.status_code == 200, response.text
        yield client


@pytest.fixture
def event(api):
    return {"id": str(uuid4()), "session_id": api.session_id, "source_id": api.camera_id, "track_id": None, "local_track_id": None, "kind": "standing", "started_at": api.timestamp, "ended_at": api.timestamp, "model_version": "pose-test", "model_confidence": None, "rule_score": None, "details": {"observation_only": True}}
