from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import String, Text, Float, Integer, Boolean, JSON, ForeignKey, UniqueConstraint, Index
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def now():
    return datetime.now(timezone.utc).isoformat()


def uid():
    return str(uuid4())


class Base(DeclarativeBase):
    pass


class Room(Base):
    __tablename__ = "rooms"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    name: Mapped[str] = mapped_column(String(160))


class Member(Base):
    __tablename__ = "room_members"
    room_id: Mapped[str] = mapped_column(ForeignKey("rooms.id"), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    role: Mapped[str] = mapped_column(String(16), default="reviewer")


class Device(Base):
    __tablename__ = "devices"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    room_id: Mapped[str] = mapped_column(ForeignKey("rooms.id"), index=True)
    name: Mapped[str] = mapped_column(String(160))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)
    last_seen: Mapped[str | None] = mapped_column(String(40))
    status: Mapped[dict] = mapped_column(JSON, default=dict)


class Source(Base):
    __tablename__ = "sources"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    device_id: Mapped[str] = mapped_column(ForeignKey("devices.id"), index=True)
    kind: Mapped[str] = mapped_column(String(16))
    name: Mapped[str] = mapped_column(String(160))


class ExamSession(Base):
    __tablename__ = "exam_sessions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    room_id: Mapped[str] = mapped_column(ForeignKey("rooms.id"), index=True)
    device_id: Mapped[str] = mapped_column(ForeignKey("devices.id"))
    name: Mapped[str] = mapped_column(String(160))
    started_at: Mapped[str] = mapped_column(String(40))
    ended_at: Mapped[str | None] = mapped_column(String(40))
    config: Mapped[dict] = mapped_column(JSON, default=dict)


class Track(Base):
    __tablename__ = "tracks"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("exam_sessions.id"), index=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id"))
    local_id: Mapped[int] = mapped_column(Integer)
    __table_args__ = (UniqueConstraint("session_id", "source_id", "local_id"),)


class Event(Base):
    __tablename__ = "events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("exam_sessions.id"))
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id"))
    track_id: Mapped[str | None] = mapped_column(ForeignKey("tracks.id"))
    kind: Mapped[str] = mapped_column(String(40))
    started_at: Mapped[str] = mapped_column(String(40))
    ended_at: Mapped[str] = mapped_column(String(40))
    model_version: Mapped[str] = mapped_column(String(200))
    model_confidence: Mapped[float | None] = mapped_column(Float)
    rule_score: Mapped[float | None] = mapped_column(Float)
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    review_status: Mapped[str] = mapped_column(String(24), default="pending")
    __table_args__ = (Index("events_session_time", "session_id", "started_at"),)


class Speech(Base):
    __tablename__ = "speech_segments"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("exam_sessions.id"))
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id"))
    event_id: Mapped[str | None] = mapped_column(ForeignKey("events.id"))
    started_at: Mapped[str] = mapped_column(String(40))
    ended_at: Mapped[str] = mapped_column(String(40))
    transcript_raw: Mapped[str | None] = mapped_column(Text)
    transcript_corrected: Mapped[str | None] = mapped_column(Text)
    model_version: Mapped[str] = mapped_column(String(200))
    processing_status: Mapped[str] = mapped_column(String(16))
    expires_at: Mapped[str] = mapped_column(String(40))
    __table_args__ = (Index("speech_session_time", "session_id", "started_at"),)


class Asset(Base):
    __tablename__ = "evidence_assets"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("exam_sessions.id"))
    event_id: Mapped[str | None] = mapped_column(ForeignKey("events.id"))
    speech_id: Mapped[str | None] = mapped_column(ForeignKey("speech_segments.id"))
    object_path: Mapped[str] = mapped_column(String(300), unique=True)
    content_type: Mapped[str] = mapped_column(String(80))
    size_bytes: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), default="pending")
    expires_at: Mapped[str] = mapped_column(String(40), index=True)


class Review(Base):
    __tablename__ = "reviews"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    event_id: Mapped[str | None] = mapped_column(ForeignKey("events.id"))
    speech_id: Mapped[str | None] = mapped_column(ForeignKey("speech_segments.id"))
    user_id: Mapped[str] = mapped_column(String(36))
    verdict: Mapped[str] = mapped_column(String(32))
    note: Mapped[str] = mapped_column(Text, default="")
    correction: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(String(40), default=now)
