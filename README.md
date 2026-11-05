# ExamWatch v2

Ứng dụng giám sát phiên thi chạy offline trên Windows, dành cho demo 1–3 thí sinh bằng camera và microphone. Mã nguồn chính ở **thư mục gốc repository**, cùng runtime và giao diện với bản portable v2. Backend FastAPI phục vụ dashboard tại **http://127.0.0.1:8000/**; suy luận trên CPU.

## 1. Chuẩn bị máy phát triển

| Thành phần | Yêu cầu |
|---|---|
| Hệ điều hành | Windows x64 |
| Git | Cài Git để clone và gửi thay đổi |
| Python | **Python 3.12 x64**, có Python Launcher `py` |
| Trình duyệt | Edge hoặc Chrome, cho phép camera/micro |
| Internet | Cần khi cài thư viện và tải model lần đầu |
| Node.js | Node 22 nếu chạy test JavaScript; không cần để chạy ứng dụng |

Không cần GPU rời, CUDA, tài khoản Supabase hoặc khóa cloud để chạy bản v2. RAM 8 GB là mốc đề xuất cho demo, chưa phải cấu hình tối thiểu đã được kiểm thử trên mọi máy.

Mở **Command Prompt (CMD)** hoặc PowerShell và kiểm tra:

```cmd
git --version
py -3.12 --version
py -3.12 -c "import struct; print(struct.calcsize('P') * 8)"
```

Lệnh cuối cần in `64`. Nếu `py -3.12` không chạy, cài Python 3.12 x64 kèm Python Launcher rồi mở terminal mới.

## 2. Clone và chạy lần đầu

Dán lần lượt các lệnh sau vào **CMD hoặc PowerShell**:

```cmd
git clone https://github.com/Gokigenzo/AI-based-exam-proctoring-extended.git examwatch-v2
cd examwatch-v2
powershell -NoProfile -ExecutionPolicy Bypass -File .\prepare.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\start.ps1
```

Chờ `prepare.ps1` hoàn tất thành công trước khi chạy `start.ps1`. Script chuẩn bị sẽ:

1. Tạo môi trường riêng `.venv/` bằng Python 3.12 nếu chưa có.
2. Cài các thư viện CPU từ requirements/constraints.
3. Tải model vào `models/` và kiểm tra nạp mô hình.

Khi terminal báo `Uvicorn running on http://127.0.0.1:8000`, mở **http://127.0.0.1:8000/**. Giữ terminal mở trong lúc dùng; nhấn **Ctrl+C** để dừng backend.

**Chạy lệnh trong thư mục vừa clone**, nơi có `prepare.ps1`, `start.ps1`, `examwatch/` và `web/`. Không chạy từ thư mục cha chỉ chứa folder repo.

Nếu đã clone phiên bản cloud cũ, nên clone v2 vào **thư mục mới** như ví dụ trên. Không dùng lại `.venv`, `.env`, `node_modules` hoặc `data` của cloud; giữ dữ liệu cũ để sao lưu khi cần.

## 3. Model có trong GitHub không

**GitHub không chứa trọng số model.** Repo chỉ có mã nguồn, thông báo license và script tải:

| Chức năng | Model được chuẩn bị mặc định |
|---|---|
| Phát hiện khuôn mặt | YuNet |
| Nhận diện danh tính | SFace |
| Nhãn cảm xúc | Emotion ONNX |
| Khung xương và tư thế | MediaPipe Pose Lite |
| Chép lời tiếng Việt | Zipformer 30M nguyên mẫu INT8 |

Chạy `prepare.ps1` một lần khi có mạng. Chuẩn bị mặc định không tải dataset, checkpoint LoRA hoặc cài môi trường Torch/CUDA. Sau khi thư viện và model đã có, `start.ps1` chạy offline. Nếu chuyển sang máy khác bằng cách clone, phải chạy prepare trên máy đó.

Gói **portable v2.zip** được tạo bằng quy trình build riêng, có runtime và model đi kèm; ZIP này không được lưu trong Git. Repo không mặc định cung cấp link tải GitHub Release.

## 4. Những lần chạy tiếp theo

Trong thư mục repo:

```cmd
powershell -NoProfile -ExecutionPolicy Bypass -File .\start.ps1
```

Hoặc nhấp đúp **`Start ExamWatch V2.cmd`** sau khi đã prepare. Không cần kích hoạt virtualenv thủ công.

Nếu cổng 8000 đang được ứng dụng khác sử dụng, dừng ứng dụng đó hoặc chọn cổng khác:

```cmd
powershell -NoProfile -ExecutionPolicy Bypass -File .\start.ps1 -Port 8001
```

Khi đó mở **http://127.0.0.1:8001/**. Không chạy hai backend trên cùng thư mục dữ liệu.

## 5. Thử camera và các cảnh báo

1. Mở dashboard, bấm **Kết nối camera** và cấp quyền trình duyệt.
2. Vào danh sách thí sinh, đăng ký danh tính bằng ảnh của cùng một người. Nhận diện không chắc sẽ hiển thị **Chưa xác định**.
3. Nhập tên phiên và bấm **Bắt đầu phiên**; cấp quyền micro khi được hỏi.
4. Ngồi thẳng, camera thấy rõ đầu và hai vai, rồi bấm **Hiệu chuẩn ngồi**. Giữ camera cố định; đổi vị trí hoặc góc camera thì hiệu chuẩn lại.
5. Thử từng hành vi và xem góc đo, cờ, cảnh báo cùng bằng chứng.

| Điều kiện | Hành vi hệ thống |
|---|---|
| Nhổm dậy | Cảnh báo sau thời gian giám thị chọn 1–300 giây |
| Tay vượt 45° | Gắn cờ; tăng thêm ít nhất 5° sau tối thiểu 0,5 giây thì tạo cảnh báo |
| Thân nghiêng từ 20° | Gắn cờ; giữ ít nhất 2 giây hoặc tăng thêm 5° sau tối thiểu 0,5 giây thì tạo cảnh báo |
| Cảm xúc sad/angry/fear đủ tin cậy kéo dài 20 giây | Tạo cảnh báo cảm xúc |

Các góc được làm mượt và phụ thuộc độ rõ landmark. Góc nghiêng lấy gốc gần bụng; khi hông bị che cần gốc ước lượng từ hiệu chuẩn. Chi tiết tại [POSE_ANGLE_ALERTS.md](POSE_ANGLE_ALERTS.md).

Cảnh báo tư thế lưu video WebM khoảng **10 giây trước + 5 giây sau**, không có âm thanh. Chờ hoàn tất rồi bấm **Xem video**; clip ngắn hơn khi thiếu dữ liệu đầu/cuối phiên. Cảnh báo cảm xúc lưu ảnh. Transcript micro được lưu riêng vào phiên, chưa phân biệt người nói.

Dashboard hiển thị **FPS AI thực đo**. Trần gửi 20 Hz không có nghĩa mọi máy đều đạt 20 FPS. Tư thế, biểu cảm và bản chép lời là thông tin để giám thị xem xét, không tự kết luận gian lận. Khi kết thúc, bấm **Kết thúc phiên** trước khi dừng backend.

## 6. Thiết lập môi trường contributor và chạy test

Sau bước prepare, cài thêm thư viện kiểm thử:

```cmd
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.venv\Scripts\python.exe -m pytest -q --basetemp=.pytest-tmp
node --test tests/test_audio_worklet.cjs tests/test_frame_pair.cjs tests/test_mic_check.cjs
```

Hai lệnh Python tương ứng trong **PowerShell**:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q --basetemp=.pytest-tmp
```

Các test unit/API dùng dữ liệu tổng hợp hoặc fixture của test, không cần bật camera/micro hoặc tải model. Nếu chỉ sửa code và chạy test, có thể bỏ bước tải model bằng cách tạo môi trường như sau:

```cmd
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.venv\Scripts\python.exe -m pytest -q --basetemp=.pytest-tmp
```

Node 22 vẫn cần cho test JavaScript. Kiểm thử tự động không thay thế đánh giá độ chính xác bằng camera/micro thật. Bản v2 đã được clone lại từ GitHub và kiểm tra 55 test Python, 7 test JavaScript tại lần chuyển cấu trúc ngày 05/11/2026.

Đối chiếu mã runtime/giao diện với snapshot portable v2:

```cmd
.venv\Scripts\python.exe scripts\verify_v2_source.py
```

`V2_SOURCE.json` chứa checksum gốc và checksum chuẩn hóa xuống dòng. Nếu đang sửa runtime/giao diện, lệnh này có thể báo khác snapshot; không phải mọi thay đổi đó đều là lỗi. Cập nhật manifest khi phát hành phiên bản tiếp theo.

## 7. Cấu trúc mã nguồn

```text
examwatch-v2/
├── examwatch/          # Backend, model adapters, tracking, luật, SQLite, video
├── web/                # HTML/CSS/JS dashboard và thu camera/micro
├── tests/              # Regression tests Python và JavaScript
├── scripts/            # Chuẩn bị model, smoke test và công cụ train tùy chọn
├── packaging/windows/  # Launcher C#, Python portable và script build
├── licenses/           # Thông báo giấy phép
├── models/             # Trọng số tải cục bộ, không commit
├── data/               # SQLite và bằng chứng tạo khi chạy, không commit
├── legacy/cloud/       # Hệ thống cloud trước đây, chỉ lưu trữ tham khảo
├── prepare.ps1
├── start.ps1
└── CONTRIBUTING.md
```

Các tệp chính:

- `examwatch/vision.py`, `tracking.py`: dò mặt, identity, pose và giữ hiệu chuẩn.
- `examwatch/rules.py`: góc tay/thân, làm mượt và luật theo thời gian.
- `examwatch/runtime.py`: điều phối phiên, camera và worker STT.
- `examwatch/speech.py`: Zipformer; có nhánh Whisper tùy chọn nhưng model không được prepare mặc định.
- `examwatch/clips.py`, `store.py`: vòng đệm video và lưu dữ liệu.

Đọc [CONTRIBUTING.md](CONTRIBUTING.md) trước khi gửi PR. Tạo nhánh riêng, thay đổi và chạy test trước khi commit. Không commit `.env`, token, model, dataset, `.venv`, database, bản thu hoặc dữ liệu thí sinh.

Ví dụ tạo nhánh để bắt đầu sửa code:

```cmd
git switch -c feature/ten-thay-doi
```

Trước khi commit, xem `git status` và `git diff` để kiểm tra phạm vi thay đổi. Gửi pull request sau khi test đạt; nếu không có quyền push vào repo, làm việc qua fork của bạn.

## 8. Dữ liệu và đóng gói Windows

Bản chạy từ source lưu tại **`data/` của repo**. Portable lưu tại **`%LOCALAPPDATA%\ExamWatch\data`**. Hai nơi không tự đồng bộ. Dừng ứng dụng rồi sao lưu thư mục dữ liệu nếu cần; clone/pull không phải cách sao lưu lịch sử phiên thi.

Để dựng bản Windows sau khi đã prepare:

```cmd
powershell -NoProfile -ExecutionPolicy Bypass -File packaging\windows\build_v2.ps1
.venv\Scripts\python.exe packaging\windows\archive_v1.py --version v2
.venv\Scripts\python.exe packaging\windows\verify_v2_zip.py
```

Build cần compiler C# .NET Framework x64 và mạng cho các tài nguyên chưa có. Script từ chối ghi đè `release/v2`. Xem [BUILD_V2.md](packaging/windows/BUILD_V2.md) để chạy self-test trước khi nén và hiểu các giới hạn kiểm tra.

## 9. Lỗi thường gặp

| Hiện tượng | Cách kiểm tra |
|---|---|
| Không tìm thấy script/file | Chạy `dir`, kiểm tra đang ở thư mục có `prepare.ps1` và `start.ps1` |
| `uv sync` báo thiếu `pyproject.toml` | V2 dùng script PowerShell và pip; chạy theo mục 2, không dùng lệnh của cloud cũ |
| `.venv` không chạy trong CMD | Prepare phải thành công trước; dùng dấu `\` trong đường dẫn `.venv\Scripts\python.exe` |
| PowerShell chặn `.ps1` | Dùng nguyên lệnh `powershell -NoProfile -ExecutionPolicy Bypass -File ...` ở trên; không cần đổi policy toàn hệ thống |
| Thiếu model | Chạy lại `prepare.ps1` khi có Internet và đọc lỗi tải xuống nếu có |
| Cổng 8000 đã dùng | Dừng backend cũ hoặc chọn `-Port 8001` |
| Không mở camera/micro | Kiểm tra quyền của trang trong Edge/Chrome và quyền Camera/Microphone cho desktop apps trong Windows |
| Giao diện cũ hoặc không có góc bụng/FPS AI | Kiểm tra đúng repo, backend và cổng; nhấn Ctrl+F5, tạo phiên mới rồi hiệu chuẩn |
| Đang ở giao diện cổng 3000 hoặc chạy `demo_server.py` | Đây là cách chạy cloud cũ, không phải v2 mặc định |

Không chạy các lệnh cũ như `uv sync`, `scripts/demo_server.py` hoặc Next.js ở gốc. Phần cloud được lưu nguyên trong `legacy/cloud/`; tài liệu bên trong mô tả cấu trúc trước đây, không phải lệnh chạy v2. Không cần cấu hình `.env` cloud cho ứng dụng hiện tại.

## 10. Giấy phép và phạm vi sử dụng

Giữ các thông báo tại [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) và `licenses/`. Model có điều kiện riêng; Zipformer nguyên mẫu đi kèm thông báo **CC-BY-NC-ND-4.0**. Xem nguồn và license trước khi phân phối hoặc thay đổi model. Repo không kèm dữ liệu cá nhân hoặc dataset huấn luyện.
