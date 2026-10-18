import re
from fastapi.testclient import TestClient
from examwatch.local.app import create_app


def test_local_config_csrf_and_status_without_hardware(tmp_path):
    with TestClient(create_app(tmp_path)) as client:
        response = client.get("/")
        assert response.status_code == 200
        token = re.search(r"const token='([^']+)'", response.text)[1]
        assert client.get("/status").json()["running"] is False
        config = client.get("/config").json()
        assert client.post("/config", json=config).status_code == 403
        assert client.post("/config", json=config, headers={"X-Local-Token": token, "Origin": "https://evil.example"}).status_code == 403
        assert client.post("/config", json=config, headers={"X-Local-Token": token}).status_code == 200
        config["api_url"] = "http://public.example"
        assert client.post("/config", json=config, headers={"X-Local-Token": token}).status_code == 422
