# ExamWatch offline v2

Đây là mã nguồn ứng dụng trong gói v2 cập nhật 04/11/2026, đưa vào repo ngày 05/11/2026. `V2_SOURCE.json` lưu hash gốc của runtime/giao diện portable và hash chuẩn hóa LF để kiểm tra sau Git checkout, cùng hash ZIP đã đối chiếu. Chạy `python scripts/verify_v2_source.py` để đối chiếu snapshot. Việc sửa source sau này có thể làm hash khác; cập nhật manifest khi tạo phiên bản tiếp theo.

## Chuẩn bị và chạy

Windows x64, Python 3.12 x64, camera/micro và Edge/Chrome. Từ thư mục này:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\prepare.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\start.ps1
```

Lần prepare cần mạng để cài thư viện và tải mô hình. Sau đó web chạy offline tại http://127.0.0.1:8000/. Thư mục hiện tại của shell không ảnh hưởng: script tự chuyển về thư mục của nó. CMD cũng chạy được hai lệnh trên.

Model: YuNet, SFace, Emotion ONNX, MediaPipe Pose Lite, Zipformer 30M nguyên mẫu INT8. Chuẩn bị không cài Torch/CUDA hay dataset. Không cần Node.js để chạy web; Node 22 chỉ dùng chạy test JavaScript. Không ép cài dependencies từ pyproject/uv.lock ở thư mục cha.

## Nghiệp vụ

- Đăng ký danh tính rồi theo dõi tối đa 3 người. Nhận diện mơ hồ hiển thị chưa xác định.
- Hiệu chuẩn ngồi trong mỗi phiên. Tracking giữ baseline qua mất mặt ngắn; góc bụng cần hiệu chuẩn khi hông bị che.
- Nhổm dậy: chọn thời gian 1–300 giây. Tay vượt 45 độ gắn cờ, tăng thêm 5 độ thì tạo cảnh báo. Nghiêng thân từ 20 độ giữ 2 giây hoặc tăng thêm 5 độ thì tạo cảnh báo.
- Các cảnh báo tư thế lưu WebM khoảng 10 giây trước và 5 giây sau, không tiếng; thiếu dữ liệu đầu/cuối thì clip ngắn hơn. Cảm xúc tiêu cực kéo dài lưu ảnh. Không tự kết luận gian lận.
- Micro chép lời Zipformer vào phiên. Camera hiển thị FPS AI thực đo; trần gửi 20 Hz không cam kết 20 FPS trên mọi máy.

Mã nguồn lưu dữ liệu tại `data/` trong thư mục này; portable lưu tại `%LOCALAPPDATA%\ExamWatch\data`. Không chạy hai server trên cùng một thư mục dữ liệu. Ctrl+C để dừng server.

## Kiểm thử

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q --basetemp=.pytest-tmp
node --test tests/test_audio_worklet.cjs tests/test_frame_pair.cjs tests/test_mic_check.cjs
```

Unit/API tests dùng fixture hoặc dữ liệu tổng hợp, không cần tải trọng số, không truy cập camera/micro thật. Xem CONTRIBUTING.md ở gốc repo để hiểu phạm vi kiểm chứng.

## Build Windows

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File packaging/windows/build_v2.ps1
.\.venv\Scripts\python.exe packaging/windows/archive_v1.py --version v2
.\.venv\Scripts\python.exe packaging/windows/verify_v2_zip.py
```

Build cần `.venv` đã prepare, model nguồn, Internet và compiler C# .NET Framework x64. Builder từ chối ghi đè `release/v2`; giữ bản cũ rồi dùng thư mục checkout mới nếu cần dựng lại. Xem `packaging/windows/BUILD_V2.md`.

## Mã nguồn chính

- `examwatch/vision.py`, `tracking.py`: model ảnh, ghép track và cache hiệu chuẩn.
- `rules.py`: góc tay, gốc bụng, smoothing và điều kiện thời gian.
- `runtime.py`: vòng đời phiên, điều phối camera/STT và cảnh báo.
- `clips.py`, `store.py`: video vòng đệm và SQLite.
- `speech.py`: Zipformer và nhánh Whisper tùy chọn.
- `web/`: HTML/CSS/JS thu camera/micro và dashboard cùng origin.
- `tests/`: regression tests; `scripts/`: chuẩn bị model, kiểm tra và huấn luyện tùy chọn.

Không có model, dữ liệu người dùng hay dataset trong Git. Giữ license/attribution tại `licenses/` và `THIRD_PARTY_NOTICES.md`; model có điều kiện sử dụng riêng, trong đó Zipformer là CC-BY-NC-ND-4.0.

## Thay đổi cấu trúc repository

Repo GitHub `Gokigenzo/AI-based-exam-proctoring-extended` hiện dùng cấu trúc v2 ngay ở thư mục gốc. Các lệnh `uv sync`, `scripts/demo_server.py`, Next.js cổng 3000 và Supabase trước đây không còn là cách chạy ứng dụng chính.

```cmd
git clone https://github.com/Gokigenzo/AI-based-exam-proctoring-extended.git
cd AI-based-exam-proctoring-extended
powershell -NoProfile -ExecutionPolicy Bypass -File .\prepare.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\start.ps1
```

Hoặc nhấp đúp `Start ExamWatch V2.cmd` sau khi chuẩn bị. Web chính phục vụ tại cổng 8000, cùng giao diện bản portable. Mã API/Next.js/Supabase trước đây được lưu trong `legacy/cloud/`, không chạy song song và không đồng bộ cloud trong ứng dụng v2. Hướng dẫn lưu trữ cũ tại `legacy/cloud/README.md` có đường dẫn/lệnh theo cấu trúc cũ, chỉ phục vụ tham khảo; không dùng để khởi động v2.

Nếu đã có checkout cũ, nên clone vào thư mục mới thay vì tái sử dụng `.venv`, `node_modules`, `.env` hoặc `data` của cloud. Không xóa các dữ liệu cũ nếu chưa sao lưu. Bản v2 từ mã nguồn và portable dùng hai vị trí dữ liệu khác nhau như mô tả ở trên.
