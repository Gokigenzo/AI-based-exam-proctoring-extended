"""Start all three localhost services without PowerShell policy changes.

Only opens the camera control page; never calls /start or opens capture devices.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser

ROOT = Path(__file__).resolve().parents[1]


def probe(port, path, kind):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(f"http://127.0.0.1:{port}{path}", timeout=2) as response:
            body = response.read(2 * 1024 * 1024).decode("utf-8")
            if kind == "api":
                return json.loads(body).get("info", {}).get("title") == "ExamWatch API"
            if kind == "local":
                data = json.loads(body)
                return isinstance(data.get("running"), bool) and "outbox" in data
            return "ExamWatch" in body and "__next" in body
    except (OSError, ValueError, urllib.error.URLError):
        return False


def port_open(port):
    with socket.socket() as connection:
        connection.settimeout(.5)
        return connection.connect_ex(("127.0.0.1", port)) == 0


def service(name, port, path, kind, command, cwd, env):
    if probe(port, path, kind):
        print(f"[OK] {name}: already running on {port}", flush=True)
        return
    if port_open(port):
        raise RuntimeError(f"Port {port} is occupied or still starting. Retry shortly; no process was stopped.")
    logs = ROOT / "data" / "startup"
    logs.mkdir(parents=True, exist_ok=True)
    log_path = logs / f"{kind}.log"
    flags = (subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP) if os.name == "nt" else 0
    with log_path.open("ab") as log:
        child = subprocess.Popen(command, cwd=cwd, env=env, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, creationflags=flags, start_new_session=os.name != "nt")
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        if probe(port, path, kind):
            print(f"[OK] {name}: http://127.0.0.1:{port}", flush=True)
            return
        if child.poll() is not None:
            raise RuntimeError(f"{name} exited. See {log_path}")
        time.sleep(.5)
    raise RuntimeError(f"{name} is not ready yet. See {log_path}; no process was stopped.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    node = shutil.which("node")
    if not node:
        raise RuntimeError("Install Node.js 22 or newer to run the local supervisor web.")
    version = subprocess.check_output([node, "--version"], text=True).strip()
    if int(version.lstrip("v").split(".")[0]) < 22:
        raise RuntimeError("Node.js 22 or newer required; found " + version)
    next_entry = ROOT / "web/node_modules/next/dist/bin/next"
    if not next_entry.exists():
        raise RuntimeError("Web dependencies missing. In web/, run npm.cmd ci, then retry.")
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "packages") + os.pathsep + env.get("PYTHONPATH", "")
    env["NEXT_PUBLIC_DEMO_MODE"] = "true"
    env["NEXT_PUBLIC_API_URL"] = "http://127.0.0.1:8000"
    env["NEXT_TELEMETRY_DISABLED"] = "1"
    model_root = ROOT / "models"
    if not (model_root / "manifest.json").exists():
        model_root = ROOT / "dist/ExamWatch/models"
    if (model_root / "manifest.json").exists():
        env["EXAMWATCH_BUNDLED_MODELS"] = str(model_root)
    service("API", 8000, "/openapi.json", "api", [sys.executable, str(ROOT / "scripts/demo_server.py")], ROOT, env)
    # Invoke Node directly: no npm.ps1, execution-policy changes, or shell quoting.
    service("Supervisor web", 3000, "/", "web", [node, str(next_entry), "dev", "--hostname", "127.0.0.1", "--port", "3000"], ROOT / "web", env)
    service("Camera controls (capture stopped)", 8765, "/status", "local", [sys.executable, "-c", "from examwatch.local.app import run; run()"], ROOT, env)
    print("Demo login: open 'Che do demo local', enter examwatch-local-demo and press Enter.")
    print("Camera stays stopped until you press Start session in the local controls.")
    if not args.no_browser:
        webbrowser.open("http://127.0.0.1:3000")
        webbrowser.open("http://127.0.0.1:8765")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print("Startup error:", error, file=sys.stderr)
        raise SystemExit(1)
