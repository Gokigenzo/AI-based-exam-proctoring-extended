# Windows local agent

Source: `packages/examwatch/local`. Developer setup: `scripts/setup-windows.ps1`, then `scripts/start-local.ps1`.

Open <http://127.0.0.1:8765>. Choose camera/microphone, configure the backend URL and device token, and draw up to four seat regions. Model paths are local and verified against the model manifest before loading. Keep the seated baseline still during the first ten seconds.

Capture and preview remain local. Video clips, snapshots, speech audio and metadata enter a durable SQLite outbox. ASR runs in a spawned process. Missing models are shown as degraded status rather than fabricated detections.
