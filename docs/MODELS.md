# Nguồn model và kiểm chứng

Model không nằm trong Git. `scripts/prepare_models.py` tải từ nguồn gốc và ghi SHA-256 vào `models/manifest.json`; PhoWhisper được ghim theo revision Hugging Face. Các worker chỉ nạp file local sau kiểm tra checksum.

| Model | Nguồn |
|---|---|
| FER+ VGG13 | TalkAI notebook `Gluon_FERPlus.ipynb`, checkpoint `s3.amazonaws.com/mxnet-demo-models/models/fer/fer-0000.params` và symbol cùng thư mục |
| YuNet | OpenCV Zoo `face_detection_yunet_2023mar.onnx` |
| Pose | MediaPipe pose_landmarker_lite float16, version 1 |
| ASR | `vinai/PhoWhisper-base`, tùy chọn `vinai/PhoWhisper-tiny` |
| VAD | ONNX đi kèm package `silero-vad==5.1.2` |

FER+: MIT theo repo TalkAI. PhoWhisper: BSD-3-Clause. Khi phân phối, giữ thông tin tác giả/giấy phép và các giấy phép thư viện, model phụ thuộc. Bản build cần lưu toàn bộ notices kèm runtime.

## Chuyển FER+ sang ONNX

MXNet mới không có wheel Windows phù hợp. Quy trình đã chạy sử dụng Python 3.8 và MXNet 1.7.0.post2 cách ly, với NumPy 1.23.5 override giới hạn metadata cũ. Không đưa runtime này vào máy thu hình khi ONNX đạt kiểm chứng.

```powershell
uv venv --python 3.8 .venv-legacy
uv pip install --python .venv-legacy/Scripts/python.exe --override scripts/requirements-legacy.txt -r scripts/requirements-legacy.txt
.venv/Scripts/python.exe scripts/make_parity_fixtures.py models
.venv-legacy/Scripts/python.exe scripts/export_fer_legacy.py models --fixtures models/fer_fixtures.npy
.venv/Scripts/python.exe scripts/verify_fer.py --root models --fixtures models/fer_fixtures.npy
.venv/Scripts/python.exe scripts/check_models.py --root models
```

Exporter đặt đúng opset 9 của MXNet cũ và chạy kiểm tra toàn bộ ONNX model sau xuất. `verify_fer.py` chỉ cho phép model hoạt động khi agreement ≥99% và max probability error ≤0.001.

Fixtures đi kèm quy trình là **100 tensor tổng hợp để kiểm tra số học**, không phải ảnh thí sinh, không phải tập đo độ chính xác FER+. Nghiệm thu cần lặp lại parity trên ảnh mặt thật đã được phép sử dụng và đo macro-F1 trên tập có nhãn.

Tiền xử lý dùng grayscale uint8 64×64, lấy mẫu affine bilinear với biên reflect theo `utils/image_utils.py`, histogram equalization, loại mặt phẳng độ sáng và chuẩn hóa độ lệch chuẩn. Không dùng chia 255 đơn thuần. Thứ tự nhãn: neutral, happiness, surprise, sadness, anger, disgust, fear, contempt.

Nếu cần chạy MXNet trực tiếp, `LegacyFER` và JSON-lines worker có sẵn cho tích hợp môi trường cũ. Luồng mặc định sử dụng ONNX đã đạt parity; ứng dụng không tự đổi sang model FER khác khi lỗi.

Nếu checkpoint nguồn không còn tải được, không tạo model giả. Huấn luyện theo notebook TalkAI trên FER2013 + nhãn FER+ (cần quyền truy cập dataset), xuất symbol/params, lặp lại quy trình trên.
