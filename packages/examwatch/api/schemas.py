from datetime import datetime, timezone
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, field_validator, field_serializer, model_validator


class Wire(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Timed(Wire):
    started_at: datetime
    ended_at: datetime

    @field_serializer("started_at", "ended_at")
    def serialize_time(self, value):
        return value.isoformat(timespec="microseconds")

    @field_validator("started_at", "ended_at")
    @classmethod
    def aware(cls, value):
        if value.tzinfo is None:
            raise ValueError("Timezone required")
        return value.astimezone(timezone.utc)

    @model_validator(mode="after")
    def ordered(self):
        if self.ended_at < self.started_at:
            raise ValueError("End precedes start")
        return self


class SessionIn(Wire):
    id: UUID
    name: str = Field(min_length=1, max_length=160)
    started_at: datetime
    config: dict = Field(default_factory=dict)

    @field_serializer("started_at")
    def serialize_time(self, value):
        return value.isoformat(timespec="microseconds")

    @field_validator("started_at")
    @classmethod
    def aware(cls, value):
        return Timed.aware(value)


class EventIn(Timed):
    id: UUID
    session_id: UUID
    source_id: UUID
    track_id: UUID | None = None
    local_track_id: int | None = Field(default=None, ge=1)
    kind: Literal["expression_observation", "speech_detected", "rising", "standing", "side_lean", "turned"]
    model_version: str = Field(min_length=1, max_length=200)
    model_confidence: float | None = Field(default=None, ge=0, le=1)
    rule_score: float | None = Field(default=None, ge=0, le=1)
    details: dict = Field(default_factory=dict)

    @model_validator(mode="after")
    def track_pair(self):
        if (self.track_id is None) != (self.local_track_id is None):
            raise ValueError("Both track identifiers required")
        return self


class SpeechIn(Timed):
    id: UUID
    session_id: UUID
    source_id: UUID
    event_id: UUID | None = None
    transcript_raw: str | None = Field(default=None, max_length=20000)
    model_version: str = Field(max_length=200)
    processing_status: Literal["QUEUED", "PROCESSING", "DONE", "FAILED"]


class EventsBatch(Wire):
    items: list[EventIn] = Field(min_length=1, max_length=100)


class SpeechBatch(Wire):
    items: list[SpeechIn] = Field(min_length=1, max_length=100)


class SourceIn(Wire):
    id: UUID
    kind: Literal["camera", "microphone"]
    name: str = Field(min_length=1, max_length=160)


class Heartbeat(Wire):
    status: dict = Field(default_factory=dict)
    sources: list[SourceIn] = Field(default_factory=list, max_length=8)


class AssetIn(Wire):
    id: UUID
    session_id: UUID
    event_id: UUID | None = None
    speech_id: UUID | None = None
    content_type: Literal["video/mp4", "audio/wav", "image/jpeg"]
    size_bytes: int = Field(gt=0, le=50 * 1024 * 1024)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def linked(self):
        if self.event_id is None and self.speech_id is None:
            raise ValueError("An evidence parent is required")
        return self


class ReviewIn(Wire):
    verdict: Literal["confirmed", "dismissed", "needs_review"]
    note: str = Field(default="", max_length=5000)
    correction: str | None = Field(default=None, max_length=20000)


class DeviceIn(Wire):
    room_id: UUID
    name: str = Field(min_length=1, max_length=160)
