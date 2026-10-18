from contextlib import asynccontextmanager
import ipaddress
import os
from pathlib import Path
import secrets
import sys

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel, Field, model_validator

from .runtime import Runtime


class ConfigIn(BaseModel):
    camera: int = Field(0, ge=0, le=10)
    microphone: int | None = Field(None, ge=0)
    api_url: str
    device_token: str | None = Field(None, max_length=300)
    model_root: str
    variant: str = "base"
    zones: list[list[float]] = Field(default_factory=list, max_length=4)
    allowed_intervals: list[list[float]] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def validate_config(self):
        from urllib.parse import urlparse
        url = urlparse(self.api_url)
        if url.scheme not in ("https", "http") or not url.hostname or url.username or url.password:
            raise ValueError("API URL không hợp lệ")
        if url.scheme == "http" and url.hostname not in ("127.0.0.1", "localhost"):
            raise ValueError("Cloud API phải dùng HTTPS")
        if self.variant not in ("base", "tiny"):
            raise ValueError("Chọn base hoặc tiny")
        for box in self.zones:
            if len(box) != 4 or not all(0 <= value <= 1 for value in box) or box[0] >= box[2] or box[1] >= box[3]:
                raise ValueError("Vùng ghế không hợp lệ")
        for interval in self.allowed_intervals:
            if len(interval) != 2 or not 0 <= interval[0] < interval[1]:
                raise ValueError("Khoảng phát biểu không hợp lệ")
        return self


class StartIn(BaseModel):
    name: str = Field(min_length=1, max_length=160)


class ProbeIn(BaseModel):
    camera: int = Field(ge=0, le=10)


def create_app(root=None):
    root = root or Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "ExamWatch"
    token = secrets.token_urlsafe(32)

    @asynccontextmanager
    async def lifespan(app):
        app.state.runtime = Runtime(root)
        yield
        app.state.runtime.close()

    app = FastAPI(title="ExamWatch local", lifespan=lifespan, docs_url=None, redoc_url=None)

    @app.middleware("http")
    async def local_only(request: Request, call_next):
        from urllib.parse import urlparse
        host = request.headers.get("host", "").split(":")[0]
        if host not in ("127.0.0.1", "localhost", "testserver"):
            return Response(status_code=403)
        origin = request.headers.get("origin")
        if origin and urlparse(origin).netloc != request.headers.get("host"):
            return Response(status_code=403)
        if request.method != "GET" and not secrets.compare_digest(request.headers.get("X-Local-Token", ""), token):
            return Response(status_code=403)
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.get("/", response_class=HTMLResponse)
    def index():
        return Path(__file__).with_name("static").joinpath("index.html").read_text(encoding="utf-8").replace("__LOCAL_TOKEN__", token)

    @app.get("/status")
    def status(request: Request):
        return request.app.state.runtime.status()

    @app.get("/config")
    def config(request: Request):
        return request.app.state.runtime.config

    @app.post("/config")
    def save(data: ConfigIn, request: Request):
        try:
            request.app.state.runtime.save_config(data.model_dump())
        except Exception as error:
            raise HTTPException(400, str(error)) from None
        return {"saved": True}

    @app.get("/devices")
    def devices():
        try:
            import sounddevice as sd
            return {"microphones": [{"id": index, "name": item["name"]} for index, item in enumerate(sd.query_devices()) if item["max_input_channels"] > 0]}
        except Exception as error:
            raise HTTPException(503, f"Không liệt kê được microphone: {error}") from None

    @app.get("/preview.jpg")
    def preview(request: Request):
        data = request.app.state.runtime.jpeg
        if not data:
            return Response(status_code=204)
        return Response(data, media_type="image/jpeg")

    @app.post("/probe-camera")
    def probe(data: ProbeIn, request: Request):
        if request.app.state.runtime.running:
            raise HTTPException(409, "Camera đang chạy trong phiên")
        import cv2
        camera = cv2.VideoCapture(data.camera, cv2.CAP_DSHOW if os.name == "nt" else cv2.CAP_ANY)
        try:
            camera.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
            camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
            frame = None
            for _ in range(5):
                ok, frame = camera.read()
                if not ok:
                    raise HTTPException(503, "Không mở được camera; kiểm tra quyền thiết bị")
            ok, image = cv2.imencode(".jpg", frame)
            if not ok:
                raise HTTPException(503, "Không tạo được hình xem trước")
            return Response(image.tobytes(), media_type="image/jpeg")
        finally:
            camera.release()

    @app.post("/start")
    def start(data: StartIn, request: Request):
        try:
            request.app.state.runtime.start(data.name)
        except Exception as error:
            raise HTTPException(400, str(error)) from None
        return {"started": True}

    @app.post("/stop")
    def stop(request: Request):
        request.app.state.runtime.stop()
        return {"stopped": True}

    @app.post("/retry-speech")
    def retry(request: Request):
        request.app.state.runtime.store.retry_speech()
        request.app.state.runtime.ensure_asr()
        return {"queued": True}

    return app


def run():
    import multiprocessing
    import uvicorn
    multiprocessing.freeze_support()
    uvicorn.run(create_app(), host="127.0.0.1", port=8765, log_level="warning")
