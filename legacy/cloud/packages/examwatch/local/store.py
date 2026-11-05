"""Durable ordered outbox. Never hold only an in-memory copy of evidence metadata."""
from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3
import time
from uuid import uuid4


class Store:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS outbox (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT, key TEXT UNIQUE NOT NULL,
                    kind TEXT NOT NULL, payload TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'pending',
                    attempts INTEGER NOT NULL DEFAULT 0, next_try REAL NOT NULL DEFAULT 0,
                    error TEXT, created REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS speech_jobs (
                    id TEXT PRIMARY KEY, payload TEXT NOT NULL, path TEXT NOT NULL,
                    state TEXT NOT NULL DEFAULT 'QUEUED', error TEXT
                );
                CREATE TABLE IF NOT EXISTS state (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            """)
            # A process may have died after claim and before completion.
            db.execute("UPDATE speech_jobs SET state='QUEUED' WHERE state='PROCESSING'")

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def enqueue(self, kind, payload, key=None, db=None):
        key = key or str(uuid4())
        values = (key, kind, json.dumps(payload, ensure_ascii=False), time.time())
        query = "INSERT OR IGNORE INTO outbox(key,kind,payload,created) VALUES(?,?,?,?)"
        if db is not None:
            db.execute(query, values)
        else:
            with self.connect() as connection:
                connection.execute(query, values)
        return key

    def peek(self):
        with self.connect() as db:
            row = db.execute("SELECT * FROM outbox WHERE state='pending' ORDER BY seq LIMIT 1").fetchone()
            return dict(row) if row and row["next_try"] <= time.time() else None

    def ack(self, seq):
        with self.connect() as db:
            db.execute("UPDATE outbox SET state='done',error=NULL WHERE seq=?", (seq,))

    def fail(self, seq, error, permanent=False):
        with self.connect() as db:
            row = db.execute("SELECT attempts FROM outbox WHERE seq=?", (seq,)).fetchone()
            attempts = row["attempts"] + 1
            # Expired evidence is terminal; auth and connectivity failures retain their place.
            db.execute("UPDATE outbox SET attempts=?,next_try=?,error=?,state=? WHERE seq=?", (attempts, time.time() + min(60, 2 ** min(attempts, 6)), error[:300], "expired" if permanent else "pending", seq))

    def put(self, key, value):
        with self.connect() as db:
            db.execute("INSERT INTO state VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, json.dumps(value)))

    def get(self, key, default=None):
        with self.connect() as db:
            row = db.execute("SELECT value FROM state WHERE key=?", (key,)).fetchone()
            return json.loads(row["value"]) if row else default

    def counts(self):
        with self.connect() as db:
            return {row["state"]: row["count"] for row in db.execute("SELECT state,count(*) AS count FROM outbox GROUP BY state")}

    def add_speech(self, payload, path):
        with self.connect() as db:
            db.execute("INSERT INTO speech_jobs(id,payload,path) VALUES(?,?,?)", (payload["id"], json.dumps(payload), str(path)))
            self.enqueue("speech", payload, key=payload["id"] + ":QUEUED", db=db)

    def claim_speech(self):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM speech_jobs WHERE state='QUEUED' ORDER BY rowid LIMIT 1").fetchone()
            if row:
                db.execute("UPDATE speech_jobs SET state='PROCESSING' WHERE id=?", (row["id"],))
            return dict(row) if row else None

    def finish_speech(self, payload, error=None):
        with self.connect() as db:
            db.execute("UPDATE speech_jobs SET state=?,payload=?,error=? WHERE id=?", (payload["processing_status"], json.dumps(payload), error, payload["id"]))
            self.enqueue("speech", payload, key=payload["id"] + ":" + payload["processing_status"], db=db)

    def retry_speech(self):
        with self.connect() as db:
            db.execute("UPDATE speech_jobs SET state='QUEUED',error=NULL WHERE state='FAILED'")

    def speech_counts(self):
        with self.connect() as db:
            return {row["state"]: row["count"] for row in db.execute("SELECT state,count(*) AS count FROM speech_jobs GROUP BY state")}

    def cleanup_local(self, evidence_root, age_days=30):
        """Only acknowledged, expired files inside the evidence directory are eligible."""
        root = Path(evidence_root).resolve()
        with self.connect() as db:
            rows = db.execute("SELECT seq,payload FROM outbox WHERE kind='asset' AND state IN ('done','expired') AND created<?", (time.time() - age_days * 86400,)).fetchall()
            for row in rows:
                path = Path(json.loads(row["payload"])["local_path"]).resolve()
                if path.is_relative_to(root):
                    path.unlink(missing_ok=True)
            for row in db.execute("SELECT seq,payload FROM outbox WHERE kind='speech' AND state='done' AND created<?", (time.time() - age_days * 86400,)):
                payload = json.loads(row["payload"])
                payload["transcript_raw"] = None
                db.execute("UPDATE outbox SET payload=? WHERE seq=?", (json.dumps(payload), row["seq"]))
            # Retain job IDs/states, remove expired local transcript contents.
            for row in db.execute("SELECT id,payload FROM speech_jobs WHERE state IN ('DONE','FAILED')"):
                payload = json.loads(row["payload"])
                from datetime import datetime, timezone
                started = payload.get("started_at")
                if started and datetime.now(timezone.utc).timestamp() - datetime.fromisoformat(started).timestamp() > age_days * 86400:
                    payload["transcript_raw"] = None
                    db.execute("UPDATE speech_jobs SET payload=? WHERE id=?", (json.dumps(payload), row["id"]))
