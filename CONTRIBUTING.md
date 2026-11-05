# Phát triển ExamWatch v2

Ứng dụng chính ở gốc repo có cùng mã runtime và giao diện với bản portable v2. Cloud cũ được giữ trong `legacy/cloud/`; phần này không tham gia chạy, build hoặc test mặc định của v2. Hướng dẫn cũ chỉ dùng tham khảo.

## Thiết lập

Python 3.12 x64, Windows x64, camera/micro và Edge/Chrome. Chạy `prepare.ps1` rồi `start.ps1` theo README. Không cần Node để chạy web, không cần uv/Supabase/khóa cloud. Node 22 dùng cho test JavaScript. Nên clone vào thư mục mới nếu trước đây dùng bản cloud.

## Kiểm thử

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q --basetemp=.pytest-tmp
node --test tests/test_audio_worklet.cjs tests/test_frame_pair.cjs tests/test_mic_check.cjs
```

Tests không cần model/camera, không chứa dữ liệu người dùng. CI chạy Python/Node ở gốc; cloud lưu trữ không được đưa vào test mặc định. Nếu sửa tracking/góc, kiểm tra thiếu landmark, người giao nhau và thay đổi danh tính. Nếu sửa video, kiểm tra pre/post-roll, flush khi dừng và giải mã WebM. Nếu tối ưu tốc độ, đo cùng đầu vào trước/sau và kiểm tra cảnh báo không bị mất; phân biệt FPS webcam, trần gửi và FPS AI.

## Cấu trúc và build

`examwatch/` là backend, tracking, luật, STT và SQLite; `web/` là giao diện cùng origin; `scripts/` chuẩn bị model và công cụ nghiên cứu tùy chọn; `tests/` là regression suite; `packaging/windows/` chứa builder. Xem `packaging/windows/BUILD_V2.md`. Builder v2 chạy từ checkout mới, không cần release v1 có sẵn.

`V2_SOURCE.json` lưu hash snapshot runtime/web đã đối chiếu với ZIP v2; cập nhật khi phát hành mới. Không commit model, dataset, virtualenv, database, ảnh/âm thanh thí sinh, token hoặc ZIP. Giữ license/attribution. Mã hóa UTF-8; script PowerShell có tiếng Việt cần BOM cho Windows PowerShell 5.1.

PR cần mô tả hành vi, test/đo lường và giới hạn. Tests unit/API không chứng minh độ chính xác trong phòng thi. Đọc POSE_ANGLE_ALERTS.md và REALTIME_OPTIMIZATION.md trước khi thay luật hoặc tối ưu mô hình.
