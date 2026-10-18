import importlib.util
from pathlib import Path
import sys


def test_launcher_calls_node_directly_and_never_starts_capture(monkeypatch):
    spec = importlib.util.spec_from_file_location("demo_startup", Path("scripts/start_demo.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    calls = []
    monkeypatch.setattr(sys, "argv", ["start_demo.py", "--no-browser"])
    monkeypatch.setattr(module.shutil, "which", lambda _: "node.exe")
    monkeypatch.setattr(module.subprocess, "check_output", lambda *a, **kw: "v24.0.0")
    monkeypatch.setattr(module.Path, "exists", lambda _: True)
    monkeypatch.setattr(module, "service", lambda *args: calls.append(args))
    module.main()
    assert [call[1] for call in calls] == [8000, 3000, 8765]
    assert calls[1][4][0] == "node.exe"
    assert "npm.ps1" not in str([call[4] for call in calls])
    assert "/start" not in str([call[4] for call in calls])


def test_api_root_explains_ui_ports(api):
    response = api.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "3000" in response.text and "8765" in response.text
