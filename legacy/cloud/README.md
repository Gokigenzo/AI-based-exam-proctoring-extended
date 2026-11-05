# ExamWatch — F08 / F09 / F10

Hệ thống quan sát phòng thi chạy AI tại máy Windows, đồng bộ bằng chứng lên web để giám thị xem lại. Mã track chỉ dùng trong phiên; không nhận dạng danh tính, không tự kết luận gian lận hoặc lo lắng.

## Thành phần đã có

- **F08:** YuNet → ghép mặt với track → TalkAI FER+ ONNX → cửa sổ thời gian. Checkpoint gốc đã tải, chuyển đổi và đối chiếu số học với MXNet.
- **F09:** microphone → resample mono 16 kHz → Silero VAD → lưu WAV → worker PhoWhisper CPU → bản chép gốc/bản chỉnh lý.
- **F10:** MediaPipe 33 điểm → Kalman/Hungarian → baseline vùng ghế → hình học/máy trạng thái và cooldown.
- **Local:** preview localhost, SQLite outbox, ring buffer, ảnh/clip H.264, retry khi mất mạng, Credential Manager.
- **API:** FastAPI, quyền phòng/thiết bị, UUID chống trùng, signed URLs, xác minh checksum và retention.
- **Web:** Next.js, Supabase Auth, bộ lọc, xem/nghe bằng chứng, thẩm tra, chỉnh bản chép, quản lý token thiết bị.
- **Cloud:** Supabase project và schema/RLS/private bucket đã tạo. Render/Vercel có cấu hình triển khai; cần cấu hình secret production trước khi chạy API cloud.

## Chạy demo local không cần camera

Trên máy đã cài dependencies, nhấp đúp **Start ExamWatch Demo.cmd** ở thư mục gốc để mở API, web giám thị (3000) và giao diện camera (8765). Không cần đổi Execution Policy của Windows; camera vẫn dừng cho đến khi bấm Bắt đầu phiên. Cổng 8000 là API và có trang chỉ dẫn tới hai giao diện.

Nếu khởi động lỗi, xem `data/startup/api.log`, `web.log`, `local.log`. Có thể chạy lại launcher; dịch vụ đang hoạt động được giữ nguyên.

Python 3.11–3.12 x64, Node ≥22 và `uv` dành cho môi trường phát triển:

```powershell
uv sync --frozen --extra local --extra dev
.venv/Scripts/python.exe scripts/demo_server.py
```

Ở terminal khác:

```powershell
.venv/Scripts/python.exe scripts/seed_demo.py
cd web
npm.cmd ci
$env:NEXT_PUBLIC_DEMO_MODE='true'
$env:NEXT_PUBLIC_API_URL='http://127.0.0.1:8000'
npm.cmd run dev
```

Mở `http://127.0.0.1:3000` → **Chế độ demo local** → nhập `examwatch-local-demo` và Enter. Dữ liệu, ảnh và âm thanh trong demo đều được đánh dấu giả lập. Không bật DEMO_MODE khi deploy cloud.

## Chạy camera và AI

```powershell
.venv/Scripts/python.exe scripts/prepare_models.py --root models
# Chuyển FER+ một lần theo docs/MODELS.md nếu chưa có ONNX đã đạt parity.
.venv/Scripts/python.exe scripts/launcher.py
```

Mở giao diện local, chọn thư mục `models`, kiểm tra camera, vẽ vùng ghế, lưu rồi bắt đầu. Token thiết bị lấy qua web; demo API cũng cho phép đăng ký thiết bị bằng token demo. Không dùng token đăng nhập giám thị thay token thiết bị.

## Kiểm thử

```powershell
.venv/Scripts/python.exe -m pytest -q --basetemp .cache/pytest
.venv/Scripts/python.exe scripts/check_models.py --root models
cd web
npm.cmd run typecheck
npm.cmd run build
npm.cmd audit
```

`tests/rls.sql` kiểm tra quyền thực trên Supabase và rollback dữ liệu thử. Các tests Python bao gồm quyền chéo phòng, thu hồi thiết bị, idempotency, upload checksum, chỉnh bản chép, retention, retry outbox, tracking mơ hồ và máy trạng thái.

## Tài liệu

- [Cài đặt/chạy Windows](docs/WINDOWS.md)
- [Model, preprocessing và kiểm chứng ONNX](docs/MODELS.md)
- [Triển khai Supabase / Render / Vercel](docs/DEPLOYMENT.md)
- [Kết quả kiểm chứng và phần chưa nghiệm thu](docs/VERIFICATION.md)

Bản demo chưa được nghiệm thu 90 phút với webcam/microphone thật hoặc trên máy Windows sạch. Không suy rộng kết quả số học/unit test thành độ chính xác nhận diện trong phòng thi thực tế.
