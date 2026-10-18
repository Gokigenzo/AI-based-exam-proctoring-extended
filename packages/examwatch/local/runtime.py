from collections import defaultdict
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
import json
import multiprocessing as mp
from pathlib import Path
from queue import Queue, Empty, Full
import shutil
import threading
import time
from uuid import uuid4, uuid5, UUID

import numpy as np

from .store import Store
from .sync import Sync
from .evidence import Evidence
from .posture import features, Baseline, PostureState
from .tracking import Tracker
from .expression import ExpressionWindow, associate_face
from .speech import Segmenter, remove_overlap, speech_allowed


def iso(origin, seconds=0):
    return (origin + timedelta(seconds=seconds)).isoformat()


def transcription_worker(store_path, model_root, variant, stop):
    """Spawned process: capture cannot be blocked by model loading or decoding."""
    from .adapters import Transcriber
    store = Store(store_path)
    try:
        transcriber = Transcriber(model_root, variant)
    except Exception as error:
        store.put("asr_status", f"Thiếu model/phụ thuộc: {type(error).__name__}: {error}")
        return
    store.put("asr_status", "Sẵn sàng")
    while not stop.wait(.2):
        job = store.claim_speech()
        if not job:
            continue
        payload = json.loads(job["payload"])
        payload["processing_status"] = "PROCESSING"
        store.enqueue("speech", payload, key=payload["id"] + ":PROCESSING")
        context = payload.pop("_context", {})
        # Jobs hold only the wire schema; continuation context is in a separate state key.
        context = store.get("speech_context:" + payload["id"], context)
        try:
            store.put("asr_status", "Đang phiên âm")
            started = time.monotonic()
            text = transcriber.transcribe(job["path"])
            if context.get("continuation"):
                previous = store.get("previous_transcript:" + payload["session_id"], "")
                text = remove_overlap(previous, text)
            store.put("previous_transcript:" + payload["session_id"], text)
            payload.update(transcript_raw=text, processing_status="DONE")
            store.finish_speech(payload)
            store.put("asr_latency_seconds", time.monotonic() - started)
            store.put("asr_status", "Sẵn sàng")
        except Exception as error:
            payload["processing_status"] = "FAILED"
            store.finish_speech(payload, type(error).__name__)
            store.put("asr_status", f"Phiên âm lỗi: {type(error).__name__}; có thể thử lại")


class Runtime:
    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.store = Store(self.root / "local.sqlite3")
        self.config = self.store.get("config", {"camera": 0, "microphone": None, "api_url": "http://127.0.0.1:8000", "model_root": str(self.root / "models"), "variant": "base", "zones": [], "allowed_intervals": []})
        import os
        if os.getenv("EXAMWATCH_BUNDLED_MODELS"):
            self.config["model_root"] = os.environ["EXAMWATCH_BUNDLED_MODELS"]
        self.device_instance = self.store.get("instance")
        if not self.device_instance:
            self.device_instance = str(uuid4())
            self.store.put("instance", self.device_instance)
        self.camera_id = str(uuid5(UUID(self.device_instance), "camera"))
        self.microphone_id = str(uuid5(UUID(self.device_instance), "microphone"))
        self.running = False
        self.lock = threading.Lock()
        self.jpeg = None
        self.tracks = []
        self.states = {}
        self.errors = {}
        self.threads = []
        self.global_stop = threading.Event()
        self.session_stop = threading.Event()
        self.asr_stop = mp.get_context("spawn").Event()
        self.asr = None
        self.synced = None
        self.sync_token = None
        self.last_heartbeat = 0
        self.session = None
        interrupted = self.store.get("active_session")
        if interrupted:
            self.store.enqueue("end", {"id": interrupted["id"], "ended_at": iso(datetime.now(timezone.utc))}, key=interrupted["id"] + ":end")
            self.store.put("active_session", None)
            self.errors["session"] = "Phiên trước bị gián đoạn; đã xếp hàng kết thúc phiên"
        thread = threading.Thread(target=self.sync_loop, daemon=True)
        thread.start()
        self.background = thread

    def token(self):
        import keyring
        return keyring.get_password("ExamWatch", self.device_instance)

    def save_config(self, data):
        if self.running:
            raise ValueError("Dừng phiên trước khi đổi cấu hình")
        if self.asr and self.asr.is_alive():
            self.asr_stop.set()
            self.asr.join(timeout=5)
            if self.asr.is_alive():
                self.asr.terminate()
                self.asr.join(timeout=5)
        token = data.pop("device_token", None)
        if token:
            import keyring
            keyring.set_password("ExamWatch", self.device_instance, token)
        self.config.update(data)
        self.store.put("config", self.config)
        self.synced = None

    def sources(self):
        return [{"id": self.camera_id, "kind": "camera", "name": f"Camera {self.config['camera']}"}, {"id": self.microphone_id, "kind": "microphone", "name": f"Microphone {self.config['microphone']}"}]

    def sync_loop(self):
        while not self.global_stop.wait(.3):
            try:
                token = self.token()
                if not token:
                    continue
                if not self.synced or token != self.sync_token:
                    self.synced = Sync(self.store, self.config["api_url"], token)
                    self.sync_token, self.last_heartbeat = token, 0
                if time.monotonic() - self.last_heartbeat >= 15:
                    self.synced.send("POST", "/v1/devices/heartbeat", {"sources": self.sources(), "status": self.status(include_sync=False)})
                    self.last_heartbeat = time.monotonic()
                    self.store.cleanup_local(self.root / "evidence")
                self.synced.once()
            except Exception as error:
                self.errors["sync"] = f"Chưa kết nối cloud: {type(error).__name__}"
            else:
                self.errors.pop("sync", None)

    def status(self, include_sync=True):
        data = {"running": self.running, "session": self.session, "errors": dict(self.errors), "tracks": self.tracks, "postures": dict(self.states), "outbox": self.store.counts(), "speech_jobs": self.store.speech_counts(), "asr": self.store.get("asr_status", "Chưa khởi động"), "asr_latency_seconds": self.store.get("asr_latency_seconds"), "free_gb": round(shutil.disk_usage(self.root).free / 1024 ** 3, 2), "evidence_error": getattr(getattr(self, "evidence", None), "error", None)}
        if include_sync:
            data["sync"] = self.synced.status if self.synced else "Chưa cấu hình token thiết bị"
        return data

    def start(self, name):
        with self.lock:
            self._start(name)

    def _start(self, name):
        if self.running:
            raise ValueError("Phiên đang chạy")
        if shutil.disk_usage(self.root).free < 1024 ** 3:
            raise ValueError("Cần ít nhất 1 GB đĩa trống để thu bằng chứng")
        self.origin = datetime.now(timezone.utc)
        self.monotonic_origin = time.monotonic()
        self.session = {"id": str(uuid4()), "name": name, "started_at": iso(self.origin), "config": {"variant": self.config["variant"], "zones": self.config["zones"], "allowed_intervals": self.config["allowed_intervals"]}}
        self.store.enqueue("session", self.session, key=self.session["id"])
        self.store.put("active_session", self.session)
        self.session_stop.clear()
        self.asr_stop.clear()
        self.frames, self.faces = Queue(maxsize=1), Queue(maxsize=1)
        self.audio = Queue(maxsize=128)
        self.evidence = Evidence(self.root / "evidence" / self.session["id"], self.store)
        self.tracks, self.states, self.errors = [], {}, {}
        self.running = True
        self.threads = []
        for target in (self.capture, self.pose_loop, self.expression_loop, self.audio_loop):
            thread = threading.Thread(target=self.guarded, args=(target,), daemon=True)
            self.threads.append(thread)
            thread.start()
        self.ensure_asr()

    def ensure_asr(self):
        if not self.asr or not self.asr.is_alive():
            self.asr_stop.clear()
            context = mp.get_context("spawn")
            self.asr = context.Process(target=transcription_worker, args=(str(self.store.path), self.config["model_root"], self.config["variant"], self.asr_stop), daemon=True)
            self.asr.start()

    def guarded(self, target):
        try:
            target()
        except Exception as error:
            self.errors[target.__name__] = f"{type(error).__name__}: {error}"
            if target == self.capture:
                self.session_stop.set()
                # Stop/finalize from a different thread to avoid joining ourselves.
                threading.Thread(target=self.stop, daemon=True).start()

    @staticmethod
    def latest(queue, item):
        try:
            queue.put_nowait(item)
        except Full:
            try:
                queue.get_nowait()
            except Empty:
                pass
            try:
                queue.put_nowait(item)
            except Full:
                pass

    def capture(self):
        import cv2
        camera = cv2.VideoCapture(int(self.config["camera"]), cv2.CAP_DSHOW if __import__("os").name == "nt" else cv2.CAP_ANY)
        try:
            camera.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
            camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
            camera.set(cv2.CAP_PROP_FPS, 15)
            if not camera.isOpened():
                raise RuntimeError("Không mở được camera; kiểm tra quyền Windows và ứng dụng khác")
            next_pose = next_face = last_disk = 0
            while not self.session_stop.is_set():
                loop = time.monotonic()
                ok, frame = camera.read()
                if not ok:
                    raise RuntimeError("Mất nguồn camera")
                timestamp = time.monotonic() - self.monotonic_origin
                if timestamp - last_disk >= 2:
                    free = shutil.disk_usage(self.root).free
                    if free < 256 * 1024 ** 2:
                        raise RuntimeError("Đĩa gần đầy; đã dừng thu để bảo vệ bằng chứng đã lưu")
                    if free < 1024 ** 3:
                        self.errors["disk"] = "Đĩa còn dưới 1 GB"
                    last_disk = timestamp
                self.evidence.frame(timestamp, frame)
                if timestamp >= next_pose:
                    self.latest(self.frames, (timestamp, frame.copy()))
                    next_pose = timestamp + .2
                if timestamp >= next_face:
                    self.latest(self.faces, (timestamp, frame.copy()))
                    next_face = timestamp + .5
                preview = frame.copy()
                for track in self.current_tracks if hasattr(self, "current_tracks") else []:
                    x1, y1, x2, y2 = track.observation.box.astype(int)
                    cv2.rectangle(preview, (x1, y1), (x2, y2), (110, 220, 50), 2)
                    cv2.putText(preview, f"T{track.id} {self.states.get(track.id, 'UNKNOWN')}", (x1, max(20, y1)), cv2.FONT_HERSHEY_SIMPLEX, .6, (110, 220, 50), 2)
                ok, jpeg = cv2.imencode(".jpg", preview)
                if ok:
                    self.jpeg = jpeg.tobytes()
                self.session_stop.wait(max(0, 1 / 15 - (time.monotonic() - loop)))
        finally:
            camera.release()

    def emit(self, kind, timestamp, version, track_id=None, details=None, confidence=None):
        event = {"id": str(uuid4()), "session_id": self.session["id"], "source_id": self.camera_id, "track_id": str(uuid5(UUID(self.session["id"]), f"{self.camera_id}:{track_id}")) if track_id else None, "local_track_id": track_id, "kind": kind, "started_at": iso(self.origin, timestamp), "ended_at": iso(self.origin, timestamp), "model_version": version, "model_confidence": confidence, "rule_score": None, "details": details or {}}
        self.store.enqueue("event", event, key=event["id"])
        self.evidence.trigger(event, timestamp)
        return event

    def pose_loop(self):
        from .adapters import PoseAdapter
        model = PoseAdapter(self.config["model_root"])
        tracker, states, samples, baselines = Tracker(), {}, defaultdict(list), {}
        episodes = {}
        calibration_start = None
        try:
            while not self.session_stop.is_set():
                try:
                    timestamp, frame = self.frames.get(timeout=.3)
                except Empty:
                    continue
                start = time.monotonic()
                tracks = tracker.update(model.predict(frame, timestamp * 1000), timestamp)
                self.current_tracks = tracks
                self.tracks = [track.id for track in tracks]
                for track in tracks:
                    state = states.setdefault(track.id, PostureState())
                    sample = features(track.observation.landmarks)
                    height, width = frame.shape[:2]
                    zone = None
                    if sample:
                        for index, bounds in enumerate(self.config["zones"]):
                            if bounds[0] <= sample["hip_x"] / width <= bounds[2] and bounds[1] <= sample["hip_y"] / height <= bounds[3]:
                                zone = index
                                break
                    # Calibration follows a seat region, never a person's biometric identity.
                    if not self.config["zones"]:
                        self.errors["calibration"] = "Chưa vẽ vùng ghế; F10 chỉ hiển thị pose"
                        self.states[track.id] = "UNKNOWN"
                        continue
                    if calibration_start is None:
                        calibration_start = timestamp
                    if timestamp - calibration_start <= 10:
                        if sample and zone is not None:
                            samples[zone].append(sample)
                        self.states[track.id] = "CALIBRATING"
                        continue
                    for index, values in samples.items():
                        if index not in baselines and len(values) >= 15:
                            baselines[index] = Baseline.from_samples(values)
                    # Assign nearest calibrated seat only within one torso length, reject ties.
                    baseline = None
                    if sample and baselines:
                        distances = sorted((abs(sample["hip_x"] - base.hip_x) / base.length, index) for index, base in baselines.items())
                        if distances[0][0] <= 1 and (len(distances) == 1 or distances[1][0] - distances[0][0] > .2):
                            baseline = baselines[distances[0][1]]
                    previous_state = state.state
                    alert = state.update(sample, baseline, timestamp)
                    self.states[track.id] = state.state
                    if previous_state != state.state:
                        episodes.pop(track.id, None)
                    if alert:
                        episode = episodes.setdefault(track.id, {"episode_id": str(uuid4()), "previous_event_id": None})
                        event = self.emit(alert.lower(), timestamp, model.version, track.id, details={"features": sample, "baseline": asdict(baseline), "observation_only": True, **episode})
                        episode["previous_event_id"] = event["id"]
                live_ids = {track.id for track in tracker.tracks}
                states = {key: value for key, value in states.items() if key in live_ids}
                self.states = {key: value for key, value in self.states.items() if key in live_ids}
                self.store.put("pose_latency_seconds", time.monotonic() - start)
        finally:
            model.close()

    def expression_loop(self):
        from .adapters import FERAdapter, LABELS
        model, windows = FERAdapter(self.config["model_root"]), {}
        while not self.session_stop.is_set():
            try:
                timestamp, frame = self.faces.get(timeout=.3)
            except Empty:
                continue
            tracks = [track for track in getattr(self, "current_tracks", []) if timestamp - track.last_seen <= .6]
            seen = set()
            for box, probabilities, quality in model.predict(frame):
                identifier = associate_face(box, tracks)
                if identifier is None:
                    continue
                seen.add(identifier)
                window = windows.setdefault(identifier, ExpressionWindow(LABELS))
                result = window.update(probabilities, timestamp, quality)
                if result:
                    self.emit("expression_observation", timestamp, model.version, identifier, details={**result, "quality": "frontal_face", "observation_only": True}, confidence=result["confidence"])
            for identifier in list(windows):
                if identifier not in seen:
                    windows[identifier].update(None, timestamp, False)
                    if identifier not in self.tracks:
                        windows.pop(identifier)

    def audio_loop(self):
        import audioop
        import sounddevice as sd
        import soundfile as sf
        from .adapters import VAD
        vad, segmenter = VAD(), Segmenter()
        native_rate = int(sd.query_devices(self.config["microphone"], "input")["default_samplerate"])
        resample_state = None
        remainder = np.empty(0, dtype=np.float32)
        audio_origin = None
        overflow = threading.Event()

        def callback(data, frames, timing, status):
            nonlocal audio_origin
            if audio_origin is None:
                # PortAudio ADC timestamp and stream currentTime share a clock.
                audio_origin = datetime.now(timezone.utc) - timedelta(seconds=max(0, timing.currentTime - timing.inputBufferAdcTime))
            if status:
                overflow.set()
            try:
                self.audio.put_nowait(data[:, 0].copy())
            except Full:
                overflow.set()

        def save(segment):
            if segment is None or len(segment.samples) < 1600:
                return
            identifier = str(uuid4())
            path = self.root / "evidence" / self.session["id"] / f"{identifier}.wav"
            sf.write(path, segment.samples, 16000, subtype="PCM_16")
            start, end = segment.start_sample / 16000, segment.end_sample / 16000
            relative_start = (audio_origin - self.origin).total_seconds() + start
            relative_end = (audio_origin - self.origin).total_seconds() + end
            event_id = None
            if not speech_allowed(relative_start, relative_end, self.config["allowed_intervals"]):
                event_id = str(uuid4())
                event = {"id": event_id, "session_id": self.session["id"], "source_id": self.microphone_id, "track_id": None, "local_track_id": None, "kind": "speech_detected", "started_at": iso(audio_origin, start), "ended_at": iso(audio_origin, end), "model_version": "silero-vad-5.1.2", "model_confidence": None, "rule_score": None, "details": {"speaker_unknown": True}}
                self.store.enqueue("event", event, key=event_id)
            payload = {"id": identifier, "session_id": self.session["id"], "source_id": self.microphone_id, "event_id": event_id, "started_at": iso(audio_origin, start), "ended_at": iso(audio_origin, end), "transcript_raw": None, "model_version": "vinai/PhoWhisper-" + self.config["variant"], "processing_status": "QUEUED"}
            self.store.put("speech_context:" + identifier, {"continuation": segment.continuation})
            self.store.add_speech(payload, path)
            self.evidence.asset(path, self.session["id"], event_id=event_id, speech_id=identifier, content_type="audio/wav")

        with sd.InputStream(device=self.config["microphone"], samplerate=native_rate, channels=1, dtype="float32", blocksize=max(1, round(native_rate * .032)), callback=callback):
            while not self.session_stop.is_set() or not self.audio.empty():
                if overflow.is_set():
                    save(segmenter.flush())
                    raise RuntimeError("Mất mẫu âm thanh; đã dừng nhánh âm thanh để tránh timestamp sai")
                try:
                    block = self.audio.get(timeout=.2)
                except Empty:
                    continue
                if native_rate != 16000:
                    pcm = (np.clip(block, -1, 1) * 32767).astype("<i2").tobytes()
                    converted, resample_state = audioop.ratecv(pcm, 2, 1, native_rate, 16000, resample_state)
                    block = np.frombuffer(converted, dtype="<i2").astype(np.float32) / 32768
                remainder = np.concatenate([remainder, block])
                while len(remainder) >= 512:
                    frame, remainder = remainder[:512], remainder[512:]
                    save(segmenter.push(frame, vad(frame)))
            if len(remainder):
                # Preserve the true source-sample duration; don't add artificial silence.
                save(segmenter.push(remainder, False))
            save(segmenter.flush())

    def stop(self):
        with self.lock:
            if not self.running:
                return
            self.session_stop.set()
            for thread in self.threads:
                if thread is not threading.current_thread():
                    thread.join(timeout=15)
            self.evidence.close()
            self.store.enqueue("end", {"id": self.session["id"], "ended_at": iso(datetime.now(timezone.utc))}, key=self.session["id"] + ":end")
            self.store.put("active_session", None)
            self.running = False
            # ASR continues draining the durable queue until app exit, including after capture stops.

    def close(self):
        self.stop()
        self.global_stop.set()
        self.asr_stop.set()
        if self.asr:
            self.asr.join(timeout=10)
            if self.asr.is_alive():
                self.asr.terminate()
                self.asr.join(timeout=5)
        self.background.join(timeout=5)
