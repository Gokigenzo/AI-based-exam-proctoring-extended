"""Loopback-only demo API with explicit sample observations; no camera access."""
import os
import secrets
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "packages"))
from examwatch.api.config import Settings
from examwatch.api.main import create_app


if __name__ == "__main__":
    import uvicorn
    config = Settings(_env_file=None, env="development", database_url="sqlite:///./data/demo.sqlite3", data_dir=Path("data/demo-cloud"), demo_token="examwatch-local-demo", signing_secret=secrets.token_urlsafe(40), allowed_origins=["http://127.0.0.1:3000", "http://localhost:3000"])
    uvicorn.run(create_app(config), host="127.0.0.1", port=8000)
