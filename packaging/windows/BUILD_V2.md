# Dựng portable v2 từ checkout mới

Không cần gói v1 có sẵn. Chạy `prepare.ps1` trong `offline-v2` để có `.venv` và model nguồn, rồi:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File packaging/windows/build_v2.ps1
$env:EXAMWATCH_HOME = Join-Path $PWD '.tmp/build-selftest'
.\release\v2\runtime\python.exe .\release\v2\app\portable_server.py --self-test
.\release\v2\ExamWatch.exe --self-test
.\.venv\Scripts\python.exe packaging/windows/archive_v1.py --version v2
.\.venv\Scripts\python.exe packaging/windows/verify_v2_zip.py
```

`EXAMWATCH_HOME` chỉ dùng cho QA để không mở dữ liệu người dùng. Bỏ biến trước khi dùng thật: `Remove-Item Env:EXAMWATCH_HOME`.

Build cần mạng, Python embeddable 3.12.10 x64, wheel CPU, compiler C# .NET Framework x64 và model đã prepare. VC Redistributable tải từ Microsoft, kiểm tra chữ ký. ZIP/checksum nằm ở `release/v2.zip` và `release/v2.zip.sha256`. Builder từ chối ghi đè `release/v2`; dùng checkout mới khi cần dựng lại và giữ bản cũ.

`qa_v1.py` là bài kiểm tra tùy chọn, cần fixture ngoài repo và Faster-Whisper chỉ để đọc audio. Nó không cần cho chạy v2: unit/API tests và portable self-test không cần fixture cá nhân. Nếu dùng bài này, cung cấp ảnh có quyền sử dụng ở `.tmp/fixtures/person1.jpg`, WAV ở `.tmp/fixtures/vi-clean.wav`, cài Faster-Whisper riêng và đặt `EXAMWATCH_QA_VERSION=v2`.

`verify_v2_zip.py` kiểm tra hash, đường dẫn ZIP và khởi động bản giải nén. Self-test nạp model với ảnh đen/im lặng không chứng minh độ chính xác trong phòng thi. Thử thêm camera thật trước khi phân phối cho máy khác. Build không bảo đảm giống từng byte vì timestamp và tài nguyên tải ngoài có thể khác.
