# Chạy ExamWatch trên Windows

## Mở cả hai giao diện trên máy có mã nguồn

Nhấp đúp **Start ExamWatch Demo.cmd** ở thư mục gốc dự án. Launcher tự mở API và hai giao diện: web giám thị `http://127.0.0.1:3000`, điều khiển camera `http://127.0.0.1:8765`. Camera không tự thu. Web yêu cầu Node.js ≥22 và dependencies đã cài bằng `npm.cmd ci` trong thư mục `web`.

PowerShell có thể chặn `npm.ps1`: dùng `npm.cmd run dev` thay vì `npm run dev`. Không cần nới Execution Policy. API cổng 8000 không phải giao diện giám thị; trang `/` có liên kết chỉ dẫn. Log khởi động ở `data/startup/`.

## Người dùng bộ portable

1. Chép **toàn bộ** thư mục `ExamWatch` vào máy Windows 10/11 x64; không chạy từ bên trong file ZIP.
2. Chạy `Start ExamWatch.cmd`. Trình duyệt mở `http://127.0.0.1:8765`.
3. Cho phép camera/microphone trong Windows Settings → Privacy. Đóng ứng dụng khác đang giữ camera.
4. Chọn camera, microphone và đường dẫn model. Bộ portable đặt sẵn đường dẫn model đi kèm.
5. Quản trị viên đăng nhập web, đăng ký thiết bị, chép token vào giao diện local. Token được lưu trong Windows Credential Manager.
6. Bấm **Kiểm tra camera trước ca**, vẽ tối đa bốn vùng ghế trên hình xem trước, lưu cấu hình, đặt tên ca rồi bắt đầu. Giữ tư thế ngồi chuẩn trong 10 giây đầu.
7. Kiểm tra trạng thái F08, F09, F10; không nghiệm thu nếu có lỗi thiếu model hoặc thiếu nguồn thu. Xem camera chỉ tại máy này.
8. Kết thúc phiên trước khi đóng ứng dụng. Để ứng dụng mở cho đến khi hàng đợi đồng bộ hết; có thể khởi động lại để gửi tiếp khi mạng phục hồi.

Dữ liệu và SQLite: `%LOCALAPPDATA%/ExamWatch`. Đổi thư mục portable không xóa dữ liệu. Chưa gán mã track với danh tính; mất track hoặc ghép mơ hồ có thể tạo mã mới.

## Nhà phát triển

```powershell
uv sync --frozen --extra local --extra dev
.venv/Scripts/python.exe scripts/prepare_models.py --root models
```

FER+ cần chuyển checkpoint một lần bằng môi trường riêng. Xem `docs/MODELS.md`. Khi đã có `manifest.json` và ONNX đạt parity, phân phối cùng bộ portable; máy đích không cần MXNet/Python/CUDA/Docker.

```powershell
powershell -ExecutionPolicy Bypass -File scripts/build-portable.ps1
```

Bản portable chứa runtime Python riêng và các dependencies trong lockfile. Bộ build kiểm tra imports/checksum; vẫn phải thử trên một máy Windows sạch trước khi công bố hỗ trợ máy đích.

## Lỗi thường gặp

- **Camera không mở:** thử chỉ số khác, kiểm tra quyền hoặc ứng dụng đang giữ thiết bị.
- **Microphone:** ứng dụng thu ở sample rate mặc định của thiết bị, resample liên tục sang PCM mono 16 kHz trước VAD/PhoWhisper. Nếu driver không mở được, chọn thiết bị khác và kiểm tra quyền Windows.
- **UNKNOWN:** thiếu điểm mốc, chưa hiệu chỉnh, người quá nhỏ hoặc vùng ghế mơ hồ. Điều chỉnh góc máy.
- **FER thiếu:** chạy quy trình chuẩn bị và kiểm tra parity; không dùng tùy tiện model FER khác.
- **Đồng bộ 401/403:** token đã thu hồi hoặc sai phòng; đăng ký lại trên web.
- **Đồng bộ 409:** file/checksum hoặc dữ liệu UUID xung đột; xem outbox trước khi sửa. Không xóa hàng đợi để che lỗi.
- **Đĩa dưới 1 GB:** ứng dụng cảnh báo. Dưới 256 MB, dừng thu. Không tự xóa file chưa gửi.
- **Phiên âm chậm:** dùng PhoWhisper-tiny sau khi tải trước bằng `--include phowhisper-tiny`; đổi cấu hình khi đã dừng phiên.

Các khoảng cho phép phát biểu tính bằng giây từ đầu ca, ví dụ `0-60, 1800-1860`. Toàn bộ đoạn nói nằm trong khoảng được phép sẽ không tạo cảnh báo; vẫn lưu âm thanh và lịch sử.
