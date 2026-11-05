# Fine-tune PhoWhisper-base bằng VietSuperSpeech

Model đang chạy là `vinai/PhoWhisper-base` đã chuyển sang CTranslate2 INT8. Fine-tune phải dùng checkpoint Hugging Face FP32 gốc; không thể cập nhật gradient trực tiếp trên `model.bin` INT8. Bộ script giữ kiến trúc base để kích thước và chi phí suy luận sau export tương đương model hiện tại.

Nguồn: https://huggingface.co/datasets/thanhnew2001/VietSuperSpeech
Revision dataset cố định: `cbf624ae9b30e1c2793a27e95b262115c69601f3`.
Manifest thực tế: 60.656 train + 6.749 dev, 245,42 giờ, khoảng 28 GB WAV. README tác giả có số liệu cũ. Nhãn được sinh bằng Zipformer, có lỗi và câu tiếng Anh; cần nghe/soát nhãn trước khi dùng làm bằng chứng cải thiện nhận dạng phòng thi.

## 1. Môi trường riêng

```powershell
.\prepare_training.ps1
```

Tạo `.venv-training`, PyTorch 2.7.1 CUDA 12.8 cho RTX 5050, Transformers 4.51.3 và Datasets 3.5.1. Dùng `-Cpu` nếu chỉ kiểm tra script trên CPU. Không cài thêm vào `.venv` của web. Cần internet cho cài đặt, dataset và lần tải checkpoint đầu tiên; model export vẫn chạy offline.

## 2. Tải và load dataset

```powershell
.\download_audio.ps1
```

Tải vào `Audio-dataset/audio/...`, giữ manifest gốc. Có thể chạy lại sau mất mạng, WAV hoàn chỉnh được bỏ qua. Xem `Audio-dataset/download-status.json` và `.tmp/audio-download.log` của lần tải được khởi chạy trong phiên làm việc này. `complete: true` mới là tải đầy đủ.

Script chỉ tải các tệp train/dev tham chiếu, không tải các audio dư trong repository. Kiểm tra đường dẫn, WAV đầy đủ và chừa ít nhất 3 GiB sau dung lượng audio ước tính. Giữ riêng cache/checkpoint training, cần thêm dung lượng cho môi trường CUDA và các checkpoint.

Chia theo hash SHA256 của `source` (nguồn video), seed cố định: 60.371 train / 4.119 validation / 2.915 test. Cùng video không xuất hiện ở hai tập; cùng người nói vẫn có thể xuất hiện trong các video khác nhau. Bản chia mới nằm trong `splits/`. Không dùng test để chọn model.

`index_audio_dataset.py` gọi `datasets.load_dataset('json', ...)` với manifest cục bộ và lưu `DatasetDict` vào `huggingface-dataset/`. Audio giữ dạng đường dẫn tương đối, không sao chép hàng chục GB vào Arrow. Có thể đọc bằng:

```python
from datasets import load_from_disk
ds = load_from_disk('Audio-dataset/huggingface-dataset')
# resolve audio against Audio-dataset when decoding
```

## 3. Kiểm tra nhỏ trước

```powershell
.venv-training\Scripts\python.exe scripts/train_stt.py --max-train-samples 8 --max-eval-samples 2 --max-steps 1 --eval-steps 1 --batch-size 1 --gradient-accumulation 1 --output training-runs/smoke
```

Thêm `--cpu` nếu môi trường CPU. Đây là kiểm tra đường đi dữ liệu và gradient, không tạo model có chất lượng để triển khai.

## 4. Huấn luyện

```powershell
.venv-training\Scripts\python.exe scripts/train_stt.py --epochs 3 --batch-size 2 --gradient-accumulation 8 --learning-rate 1e-5
```

Mặc định đóng băng encoder, train decoder để giảm VRAM, dùng FP16, gradient checkpointing và batch hiệu dụng 16. Có thể bật `--no-freeze-encoder` khi muốn fine-tune toàn bộ; nếu hết VRAM giảm `--batch-size 1`. Chu kỳ đánh giá/lưu mỗi 500 bước, giữ 2 checkpoint và chọn WER thấp nhất. `--resume training-runs/phowhisper-vietsuper/checkpoint-500` để tiếp tục. Không tự bắt đầu phiên train dài khi chỉ yêu cầu tạo script.

Không cache toàn bộ log-Mel: trích đặc trưng từng batch, tránh hàng trăm GB dữ liệu đệm. Kiểm tra audio <=30 giây và transcript trong giới hạn decoder; không cắt audio rồi giữ nhãn nguyên. So sánh WER/CER trước và sau trên cùng tối đa 256 mẫu validation mặc định; `--max-eval-samples 0` đánh giá toàn bộ validation. Chuẩn hóa NFC, chữ thường và dấu câu, giữ dấu tiếng Việt. WER có thể vượt 100%.

`run.json` lưu tham số và revision model thực tế. `comparison.json` chứa baseline/fine-tuned WER/CER. `final/` chứa model được chọn. Kết quả validation tốt hơn chưa chứng minh cải thiện tiếng nói nhỏ hoặc nhiễu phòng thi; cần tập thu thực tế riêng có nhãn được kiểm tra.

## 5. Export và dùng trong demo

```powershell
.venv-training\Scripts\python.exe scripts/export_stt.py --checkpoint training-runs/phowhisper-vietsuper/final
.venv-training\Scripts\python.exe scripts/evaluate_stt.py --samples 100
.\start.ps1 -Whisper phowhisper-vietsuper
```

Export tạo `models/whisper-phowhisper-vietsuper`, kiểm tra nạp bằng Faster-Whisper CPU INT8 và lưu SHA256 từng tệp. Không ghi đè model gốc và không tự đổi model mặc định. Đánh giá thêm bản INT8 trên test và âm thanh thực tế trước khi chuyển sử dụng. Fine-tuning giữ kiến trúc nên không tự tăng tốc suy luận; không thể cam kết WER tốt hơn khi chưa train và đánh giá.

Tài liệu triển khai: https://huggingface.co/blog/fine-tune-whisper và https://opennmt.net/CTranslate2/guides/transformers.html
