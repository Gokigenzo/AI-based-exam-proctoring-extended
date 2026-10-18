from collections import deque
from dataclasses import dataclass, field
import hashlib
from pathlib import Path
import subprocess
import threading
from uuid import uuid4


@dataclass
class PendingClip:
    event: dict
    trigger: float
    frames: list = field(default_factory=list)


class Evidence:
    def __init__(self, root, store, fps=15):
        self.root, self.store, self.fps = Path(root), store, fps
        self.root.mkdir(parents=True, exist_ok=True)
        self.ring = deque(maxlen=10 * fps)
        self.pending = []
        self.lock = threading.Lock()
        self.encoding = threading.Semaphore(2)
        self.threads = []
        self.error = None

    def frame(self, timestamp, frame):
        import cv2
        # Compressed ring bounds RAM even for a long session.
        ok, encoded = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
        if not ok:
            return
        item = (timestamp, encoded.tobytes())
        with self.lock:
            self.ring.append(item)
            done = []
            for clip in self.pending:
                clip.frames.append(item)
                if timestamp >= clip.trigger + 10:
                    done.append(clip)
            for clip in done:
                self.pending.remove(clip)
                self._schedule(clip)

    def trigger(self, event, timestamp):
        with self.lock:
            if len(self.pending) >= 12:
                self.error = "Quá tải ghi clip; sự kiện đã lưu nhưng clip chưa đầy đủ"
                return
            frames = [item for item in self.ring if item[0] >= timestamp - 5]
            clip = PendingClip(event, timestamp, frames)
            self.pending.append(clip)
            if frames:
                path = self.root / f"{event['id']}.jpg"
                path.write_bytes(frames[-1][1])
                self.asset(path, event["session_id"], event_id=event["id"], content_type="image/jpeg")

    def asset(self, path, session_id, event_id=None, speech_id=None, content_type="video/mp4"):
        checksum = hashlib.sha256()
        with open(path, "rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                checksum.update(block)
        self.store.enqueue("asset", {"id": str(uuid4()), "session_id": session_id, "event_id": event_id, "speech_id": speech_id, "content_type": content_type, "size_bytes": Path(path).stat().st_size, "sha256": checksum.hexdigest(), "local_path": str(Path(path).resolve())})

    def _schedule(self, clip):
        self.threads = [thread for thread in self.threads if thread.is_alive()]
        if not self.encoding.acquire(blocking=False):
            self.error = "Bộ mã hóa đang quá tải; vẫn giữ ảnh bằng chứng"
            return
        def work():
            try:
                self._encode(clip)
            except Exception as error:
                self.error = f"Không ghi được clip: {type(error).__name__}"
            finally:
                self.encoding.release()
        thread = threading.Thread(target=work, daemon=True)
        self.threads.append(thread)
        thread.start()

    def _encode(self, clip):
        if not clip.frames:
            return
        import imageio_ffmpeg
        path = self.root / f"{clip.event['id']}.mp4"
        command = [imageio_ffmpeg.get_ffmpeg_exe(), "-loglevel", "error", "-y", "-f", "image2pipe", "-vcodec", "mjpeg", "-framerate", str(self.fps), "-i", "-", "-an", "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(path)]
        process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        try:
            # Resample by capture timestamps; frame drops must not speed up the evidence.
            index = 0
            start, finish = clip.frames[0][0], clip.frames[-1][0]
            for step in range(max(1, int((finish - start) * self.fps) + 1)):
                target = start + step / self.fps
                while index + 1 < len(clip.frames) and clip.frames[index + 1][0] <= target:
                    index += 1
                process.stdin.write(clip.frames[index][1])
            process.stdin.close()
            error = process.stderr.read()
            if process.wait(timeout=60):
                raise RuntimeError(error.decode(errors="replace")[:300])
            self.asset(path, clip.event["session_id"], event_id=clip.event["id"])
        finally:
            if process.poll() is None:
                process.kill()

    def close(self):
        with self.lock:
            for clip in self.pending:
                self._schedule(clip)
            self.pending.clear()
        for thread in self.threads:
            thread.join(timeout=65)
