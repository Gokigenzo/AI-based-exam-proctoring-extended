"""Idempotent retention job; failed object deletion remains retryable."""
import logging
from sqlalchemy import select

from .config import settings
from .db import database
from .models import Asset, Speech, Review, now
from .storage import Storage


def cleanup(factory, storage, timestamp=None):
    cutoff = timestamp or now()
    deleted = failed = 0
    with factory() as db:
        for row in db.scalars(select(Asset).where(Asset.expires_at <= cutoff, Asset.status != "expired")):
            try:
                storage.delete(row)
                row.status = "expired"
                db.commit()
                deleted += 1
            except Exception:
                db.rollback()
                logging.warning("Evidence deletion failed; retained for retry: %s", row.id)
                failed += 1
        for row in db.scalars(select(Speech).where(Speech.expires_at <= cutoff)):
            row.transcript_raw = row.transcript_corrected = None
            for review in db.scalars(select(Review).where(Review.speech_id == row.id)):
                review.correction = None
                review.note = "[Nội dung đã hết hạn]"
        db.commit()
    return {"deleted": deleted, "failed": failed}


def main():
    config = settings()
    engine, factory = database(config.database_url)
    try:
        result = cleanup(factory, Storage(config))
        print(result)
        if result["failed"]:
            raise SystemExit(1)
    finally:
        engine.dispose()
