from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
import threading
from uuid import UUID

from fastapi import FastAPI, Depends, HTTPException, Header, Request, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from sqlalchemy import select, or_, text
from sqlalchemy.exc import IntegrityError

from .config import settings
from .db import database
from .models import Room, Member, Device, Source, ExamSession, Track, Event, Speech, Asset, Review, now
from .schemas import SessionIn, EventsBatch, SpeechBatch, Heartbeat, AssetIn, ReviewIn, DeviceIn
from .security import authenticate, require_room, digest, new_device_token, check_capability, DEMO_USER, DEMO_ROOM, DEMO_DEVICE
from .storage import Storage


def asdict(row):
    return {column.name: getattr(row, column.name) for column in row.__table__.columns}


def deadline(start):
    return (datetime.fromisoformat(start) + timedelta(days=30)).isoformat()


def create_app(config=None):
    config = config or settings()
    engine, factory = database(config.database_url)
    storage = Storage(config)

    @asynccontextmanager
    async def lifespan(_):
        if config.env != "production" and config.demo_token:
            with factory() as db:
                if not db.get(Room, DEMO_ROOM):
                    db.add(Room(id=DEMO_ROOM, name="Phòng demo"))
                    db.flush()
                    db.add(Member(room_id=DEMO_ROOM, user_id=DEMO_USER, role="admin"))
                    db.add(Device(id=DEMO_DEVICE, room_id=DEMO_ROOM, name="Máy demo", token_hash=digest(config.demo_token + "-device")))
                    db.commit()
        stop_cleanup = threading.Event()
        def retention_loop():
            from .cleanup import cleanup
            import logging
            while not stop_cleanup.is_set():
                try:
                    cleanup(factory, storage)
                except Exception:
                    logging.exception("Retention job failed; will retry")
                stop_cleanup.wait(3600)
        cleanup_thread = threading.Thread(target=retention_loop, daemon=True)
        cleanup_thread.start()
        try:
            yield
        finally:
            stop_cleanup.set()
            cleanup_thread.join(timeout=5)
            engine.dispose()

    app = FastAPI(title="ExamWatch API", version="0.1.0", lifespan=lifespan)
    app.state.factory = factory
    app.state.storage = storage
    app.add_middleware(CORSMiddleware, allow_origins=config.allowed_origins, allow_methods=["GET", "POST", "PATCH", "DELETE", "PUT"], allow_headers=["Authorization", "Content-Type"], allow_credentials=False)

    def connection():
        with factory() as db:
            try:
                yield db
            except IntegrityError:
                db.rollback()
                raise HTTPException(409, "Dữ liệu xung đột; hãy tải lại và thử lại") from None

    def principal(authorization: str = Header(default=""), db=Depends(connection)):
        if not authorization.startswith("Bearer "):
            raise HTTPException(401, "Yêu cầu đăng nhập")
        return authenticate(authorization[7:], db, config)

    def user(actor):
        if not actor.user_id:
            raise HTTPException(403, "Chức năng dành cho giám thị")

    def device(actor):
        if not actor.device_id:
            raise HTTPException(403, "Yêu cầu token thiết bị")

    def session_access(db, actor, session_id, write=False):
        session = db.get(ExamSession, str(session_id))
        if not session:
            raise HTTPException(404, "Không tìm thấy phiên thi")
        require_room(db, actor, session.room_id)
        if write and actor.device_id != session.device_id:
            raise HTTPException(403, "Thiết bị không sở hữu phiên")
        return session

    def source_access(db, actor, source_id):
        source = db.get(Source, str(source_id))
        if not source or source.device_id != actor.device_id:
            raise HTTPException(403, "Nguồn thu không thuộc thiết bị")
        return source

    def parent(db, cls, identifier, session_id):
        row = db.get(cls, str(identifier))
        if not row or row.session_id != str(session_id):
            raise HTTPException(400, "Bằng chứng/tham chiếu khác phiên thi")
        return row

    @app.get("/healthz")
    def health(db=Depends(connection)):
        db.execute(text("select 1"))
        return {"status": "ok", "version": "0.1.0"}

    @app.get("/v1/rooms")
    def rooms(actor=Depends(principal), db=Depends(connection)):
        user(actor)
        return [asdict(row) for row in db.scalars(select(Room).join(Member).where(Member.user_id == actor.user_id))]

    @app.post("/v1/devices")
    def register(data: DeviceIn, actor=Depends(principal), db=Depends(connection)):
        require_room(db, actor, str(data.room_id), admin=True)
        token = new_device_token()
        row = Device(room_id=str(data.room_id), name=data.name, token_hash=digest(token))
        db.add(row)
        db.commit()
        return {"id": row.id, "token": token, "room_id": row.room_id}

    @app.get("/v1/devices")
    def devices(room_id: UUID, actor=Depends(principal), db=Depends(connection)):
        user(actor)
        require_room(db, actor, str(room_id))
        return [{key: value for key, value in asdict(row).items() if key != "token_hash"} for row in db.scalars(select(Device).where(Device.room_id == str(room_id)))]

    @app.delete("/v1/devices/{device_id}")
    def revoke(device_id: UUID, actor=Depends(principal), db=Depends(connection)):
        row = db.get(Device, str(device_id))
        if not row:
            raise HTTPException(404)
        require_room(db, actor, row.room_id, admin=True)
        row.revoked = True
        db.commit()
        return {"revoked": True}

    @app.post("/v1/devices/heartbeat")
    def heartbeat(data: Heartbeat, actor=Depends(principal), db=Depends(connection)):
        device(actor)
        row = db.get(Device, actor.device_id)
        row.last_seen, row.status = now(), data.status
        for item in data.sources:
            source = db.get(Source, str(item.id))
            if source and (source.device_id != row.id or source.kind != item.kind):
                raise HTTPException(409, "Nguồn đã đăng ký cho thiết bị khác hoặc khác loại")
            if not source:
                db.add(Source(id=str(item.id), device_id=row.id, kind=item.kind, name=item.name))
        db.commit()
        return {"server_time": now(), "device_id": row.id, "room_id": row.room_id}

    @app.post("/v1/sessions")
    def start(data: SessionIn, actor=Depends(principal), db=Depends(connection)):
        device(actor)
        row = db.get(ExamSession, str(data.id))
        if row:
            session_access(db, actor, row.id, write=True)
        else:
            row = ExamSession(**data.model_dump(mode="json"), room_id=actor.room_id, device_id=actor.device_id)
            db.add(row)
            db.commit()
        return asdict(row)

    @app.post("/v1/sessions/{session_id}/end")
    def end(session_id: UUID, data: dict, actor=Depends(principal), db=Depends(connection)):
        device(actor)
        row = session_access(db, actor, session_id, write=True)
        try:
            value = datetime.fromisoformat(data["ended_at"])
            if value.tzinfo is None or value < datetime.fromisoformat(row.started_at):
                raise ValueError()
        except (KeyError, ValueError, TypeError):
            raise HTTPException(422, "ended_at không hợp lệ") from None
        row.ended_at = row.ended_at or value.astimezone(timezone.utc).isoformat()
        db.commit()
        return asdict(row)

    @app.get("/v1/sessions")
    def sessions(room_id: UUID, actor=Depends(principal), db=Depends(connection)):
        user(actor)
        require_room(db, actor, str(room_id))
        return [asdict(row) for row in db.scalars(select(ExamSession).where(ExamSession.room_id == str(room_id)).order_by(ExamSession.started_at.desc()).limit(200))]

    @app.get("/v1/sessions/{session_id}/sources")
    def session_sources(session_id: UUID, actor=Depends(principal), db=Depends(connection)):
        user(actor)
        session = session_access(db, actor, session_id)
        return [asdict(row) for row in db.scalars(select(Source).where(Source.device_id == session.device_id))]

    @app.get("/v1/sessions/{session_id}/tracks")
    def session_tracks(session_id: UUID, actor=Depends(principal), db=Depends(connection)):
        user(actor)
        session_access(db, actor, session_id)
        return [asdict(row) for row in db.scalars(select(Track).where(Track.session_id == str(session_id)).order_by(Track.local_id))]

    @app.post("/v1/events:batch")
    def ingest_events(data: EventsBatch, actor=Depends(principal), db=Depends(connection)):
        device(actor)
        for item in data.items:
            session_access(db, actor, item.session_id, write=True)
            source = source_access(db, actor, item.source_id)
            if (item.kind == "speech_detected") != (source.kind == "microphone"):
                raise HTTPException(400, "Loại sự kiện không phù hợp nguồn thu")
            if item.track_id:
                track = db.get(Track, str(item.track_id))
                if track and (track.session_id != str(item.session_id) or track.source_id != str(item.source_id) or track.local_id != item.local_track_id):
                    raise HTTPException(409, "Mã theo dõi xung đột")
                if not track:
                    db.add(Track(id=str(item.track_id), session_id=str(item.session_id), source_id=str(item.source_id), local_id=item.local_track_id))
                    db.flush()
            row = db.get(Event, str(item.id))
            payload = item.model_dump(mode="json", exclude={"local_track_id"})
            if row:
                if any(getattr(row, key) != value for key, value in payload.items()):
                    raise HTTPException(409, "UUID sự kiện đã có dữ liệu khác")
            else:
                db.add(Event(**payload))
                db.flush()
        db.commit()
        return {"accepted": [str(item.id) for item in data.items]}

    @app.post("/v1/speech-segments:batch")
    def ingest_speech(data: SpeechBatch, actor=Depends(principal), db=Depends(connection)):
        device(actor)
        order = {"QUEUED": 0, "PROCESSING": 1, "FAILED": 2, "DONE": 3}
        for item in data.items:
            session_access(db, actor, item.session_id, write=True)
            if source_access(db, actor, item.source_id).kind != "microphone":
                raise HTTPException(400, "Yêu cầu nguồn microphone")
            if item.event_id:
                linked = parent(db, Event, item.event_id, item.session_id)
                if linked.kind != "speech_detected" or linked.source_id != str(item.source_id):
                    raise HTTPException(400, "Đoạn nói phải liên kết sự kiện tiếng nói cùng nguồn")
            payload = item.model_dump(mode="json")
            row = db.get(Speech, str(item.id))
            if row:
                fixed = ("session_id", "source_id", "event_id", "started_at", "ended_at", "model_version")
                if any(getattr(row, key) != payload[key] for key in fixed):
                    raise HTTPException(409, "UUID đoạn nói xung đột")
                if order[item.processing_status] >= order[row.processing_status] and row.expires_at > now():
                    if row.processing_status == "DONE" and row.transcript_raw != item.transcript_raw:
                        raise HTTPException(409, "Bản chép gốc đã hoàn tất không được sửa")
                    row.transcript_raw, row.processing_status = item.transcript_raw, item.processing_status
            else:
                if deadline(payload["started_at"]) <= now():
                    payload["transcript_raw"] = None
                db.add(Speech(**payload, expires_at=deadline(payload["started_at"])))
                db.flush()
        db.commit()
        return {"accepted": [str(item.id) for item in data.items]}

    @app.post("/v1/assets/upload-url")
    def upload_url(data: AssetIn, request: Request, actor=Depends(principal), db=Depends(connection)):
        device(actor)
        session = session_access(db, actor, data.session_id, write=True)
        expiry = None
        if data.event_id:
            expiry = deadline(parent(db, Event, data.event_id, data.session_id).started_at)
        if data.speech_id:
            linked = parent(db, Speech, data.speech_id, data.session_id)
            if data.event_id and linked.event_id != str(data.event_id):
                raise HTTPException(400, "Đoạn nói và sự kiện không khớp")
            expiry = linked.expires_at
        if not expiry or expiry <= now():
            raise HTTPException(410, "Bằng chứng đã hết hạn")
        if data.size_bytes > config.max_asset_bytes:
            raise HTTPException(413)
        row = db.get(Asset, str(data.id))
        payload = data.model_dump(mode="json")
        if row:
            if any(getattr(row, key) != value for key, value in payload.items()):
                raise HTTPException(409, "UUID bằng chứng xung đột")
            if row.status == "ready":
                return {"id": row.id, "status": "ready"}
        else:
            extension = {"video/mp4": "mp4", "audio/wav": "wav", "image/jpeg": "jpg"}[data.content_type]
            row = Asset(**payload, object_path=f"{session.room_id}/{session.id}/{data.id}.{extension}", expires_at=expiry)
            db.add(row)
            db.commit()
        return {"id": row.id, "status": row.status, **storage.url(row, "upload", str(request.base_url))}

    @app.post("/v1/assets/{asset_id}/complete")
    def complete(asset_id: UUID, actor=Depends(principal), db=Depends(connection)):
        device(actor)
        row = db.get(Asset, str(asset_id))
        if not row:
            raise HTTPException(404)
        session_access(db, actor, row.session_id, write=True)
        if row.expires_at <= now():
            raise HTTPException(410)
        storage.verify(row)
        row.status = "ready"
        db.commit()
        return {"status": "ready"}

    @app.get("/v1/assets/{asset_id}/view-url")
    def view_url(asset_id: UUID, request: Request, actor=Depends(principal), db=Depends(connection)):
        user(actor)
        row = db.get(Asset, str(asset_id))
        if not row:
            raise HTTPException(404)
        session_access(db, actor, row.session_id)
        if row.status == "expired" or row.expires_at <= now():
            raise HTTPException(410, "Bằng chứng đã hết hạn")
        if row.status != "ready":
            raise HTTPException(409, "Bằng chứng chưa tải xong")
        return {"content_type": row.content_type, **storage.url(row, "view", str(request.base_url))}

    @app.api_route("/v1/assets/{asset_id}/content", methods=["GET", "PUT"])
    async def local_content(asset_id: UUID, request: Request, action: str, expires: int, signature: str):
        if config.env == "production":
            raise HTTPException(404)
        check_capability(config.signing_secret, str(asset_id), action, expires, signature)
        with factory() as db:
            row = db.get(Asset, str(asset_id))
            if not row:
                raise HTTPException(404)
            if row.expires_at <= now():
                raise HTTPException(410)
            path = storage.path(row)
            if request.method == "GET" and action == "view" and row.status == "ready":
                return FileResponse(path, media_type=row.content_type, headers={"Cache-Control": "private, no-store"})
            if request.method != "PUT" or action != "upload" or row.status == "ready":
                raise HTTPException(403)
            path.parent.mkdir(parents=True, exist_ok=True)
            temp = path.with_suffix(".upload")
            size, checksum = 0, hashlib.sha256()
            try:
                with temp.open("wb") as handle:
                    async for block in request.stream():
                        size += len(block)
                        if size > row.size_bytes:
                            raise HTTPException(413)
                        checksum.update(block)
                        handle.write(block)
                if size != row.size_bytes or checksum.hexdigest() != row.sha256:
                    raise HTTPException(409, "Checksum không khớp")
                temp.replace(path)
            finally:
                temp.unlink(missing_ok=True)
            return {"uploaded": True}

    def evidence(db, event_id=None, speech_id=None):
        query = select(Asset).where(Asset.event_id == event_id) if event_id else select(Asset).where(Asset.speech_id == speech_id)
        return [{**asdict(row), "status": "expired" if row.expires_at <= now() else row.status} for row in db.scalars(query)]

    @app.get("/v1/events")
    def list_events(session_id: UUID, source_id: UUID | None = None, kind: str | None = None, track_id: UUID | None = None, review_status: str | None = None, start: datetime | None = None, end: datetime | None = None, offset: int = Query(0, ge=0), limit: int = Query(30, ge=1, le=100), actor=Depends(principal), db=Depends(connection)):
        user(actor)
        session_access(db, actor, session_id)
        query = select(Event).where(Event.session_id == str(session_id))
        for column, value in ((Event.source_id, source_id), (Event.kind, kind), (Event.track_id, track_id), (Event.review_status, review_status)):
            if value:
                query = query.where(column == str(value))
        if start:
            query = query.where(Event.started_at >= start.astimezone(timezone.utc).isoformat())
        if end:
            query = query.where(Event.started_at <= end.astimezone(timezone.utc).isoformat())
        rows = list(db.scalars(query.order_by(Event.started_at.desc(), Event.id).offset(offset).limit(limit + 1)))
        return {"items": [{**asdict(row), "assets": evidence(db, event_id=row.id)} for row in rows[:limit]], "has_more": len(rows) > limit}

    @app.get("/v1/events/{event_id}")
    def event_detail(event_id: UUID, actor=Depends(principal), db=Depends(connection)):
        user(actor)
        row = db.get(Event, str(event_id))
        if not row:
            raise HTTPException(404)
        session_access(db, actor, row.session_id)
        return {**asdict(row), "assets": evidence(db, event_id=row.id), "reviews": [asdict(r) for r in db.scalars(select(Review).where(Review.event_id == row.id).order_by(Review.created_at))]}

    @app.get("/v1/speech-segments")
    def speech_list(session_id: UUID, q: str = Query("", max_length=200), source_id: UUID | None = None, start: datetime | None = None, end: datetime | None = None, offset: int = Query(0, ge=0), limit: int = Query(30, ge=1, le=100), actor=Depends(principal), db=Depends(connection)):
        user(actor)
        session_access(db, actor, session_id)
        query = select(Speech).where(Speech.session_id == str(session_id))
        if source_id:
            query = query.where(Speech.source_id == str(source_id))
        if start:
            query = query.where(Speech.started_at >= start.astimezone(timezone.utc).isoformat())
        if end:
            query = query.where(Speech.started_at <= end.astimezone(timezone.utc).isoformat())
        if q:
            query = query.where(Speech.expires_at > now(), or_(Speech.transcript_raw.contains(q, autoescape=True), Speech.transcript_corrected.contains(q, autoescape=True)))
        rows = list(db.scalars(query.order_by(Speech.started_at.desc(), Speech.id).offset(offset).limit(limit + 1)))
        result = []
        for row in rows[:limit]:
            item = asdict(row)
            if row.expires_at <= now():
                item.update(transcript_raw=None, transcript_corrected=None)
            result.append({**item, "assets": evidence(db, speech_id=row.id), "expired": row.expires_at <= now()})
        return {"items": result, "has_more": len(rows) > limit}

    def save_review(data, actor, db, event_row=None, speech_row=None):
        user(actor)
        row = event_row or speech_row
        session_access(db, actor, row.session_id)
        if data.correction is not None and (not speech_row or speech_row.expires_at <= now()):
            raise HTTPException(400, "Không thể sửa bản chép này")
        review = Review(event_id=event_row.id if event_row else None, speech_id=speech_row.id if speech_row else None, user_id=actor.user_id, **data.model_dump())
        db.add(review)
        if event_row:
            event_row.review_status = data.verdict
        if speech_row and data.correction is not None:
            speech_row.transcript_corrected = data.correction
        db.commit()
        return asdict(review)

    @app.post("/v1/events/{event_id}/reviews")
    def review_event(event_id: UUID, data: ReviewIn, actor=Depends(principal), db=Depends(connection)):
        row = db.get(Event, str(event_id))
        if not row:
            raise HTTPException(404)
        return save_review(data, actor, db, event_row=row)

    @app.patch("/v1/speech-segments/{speech_id}/review")
    def review_speech(speech_id: UUID, data: ReviewIn, actor=Depends(principal), db=Depends(connection)):
        row = db.get(Speech, str(speech_id))
        if not row:
            raise HTTPException(404)
        return save_review(data, actor, db, speech_row=row)

    return app


def run():
    import uvicorn
    uvicorn.run("examwatch.api.main:create_app", factory=True, host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
