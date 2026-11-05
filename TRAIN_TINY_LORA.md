# PhoWhisper-tiny LoRA — tập nhỏ

Model nguồn: `vinai/PhoWhisper-tiny`, revision `cc51d32be916efebde04ff549854fa1741cb5c02` (BSD-3-Clause). Khởi tạo từ tiny gốc, không từ bản base đã fine-tune trước đây.

## Dữ liệu đang giữ

`Audio-dataset/vivos-small/` chứa 1.467 train, 100 validation và 100 test, tổng 1.667 audio FLAC, khoảng 119 MiB. Audio train khoảng 1,79 giờ. VIVOS nguồn: `AILAB-VNUHCM/vivos`, revision `3cbfb2502e5e84776b4b778b020a09759f723f52`, CC-BY-NC-SA-4.0. Archive nguồn ~1,47 GB được đọc dạng stream, không giữ trên đĩa; không tải lại VietSuperSpeech.

Các mẫu được giữ theo quota từng người nói; 5 người nói train gốc được dành cho validation, test lấy từ phần test gốc. Giữ mẫu mono 16 kHz, dài 1–8 giây, transcript 3–55 từ; loại âm thanh không hữu hạn, quá nhỏ, clipping nhiều và audio trùng hoàn toàn. Chuẩn hóa NFC, chữ thường và khoảng trắng, giữ dấu tiếng Việt. Lưu lossless FLAC. Đây là kiểm tra tự động; chưa nghe/soát nhãn từng mẫu bằng người.

33 mẫu train thiếu so với mục tiêu 1.500 do quota/điều kiện lọc; giữ 1.467 thay vì lấy các mẫu không đạt. Giới hạn audio giữ lại 300 MiB. Metadata và manifest nằm cùng thư mục; `download-status.json` ghi số lượng và dung lượng thực.

**VIVOS từng được PhoWhisper dùng khi pretrain.** Tách người nói ở đây chỉ độc lập với lần fine-tune này. WER thấp trên tập này không chứng minh khả năng nhận dạng tiếng trao đổi nhỏ/xa trong phòng thi. Cần tập thu thực tế riêng trước khi triển khai.

## Training

```powershell
.\prepare_training.ps1
.\train_tiny_lora.ps1
```

LoRA rank 8, alpha 16, dropout 0,05 vào q_proj/v_proj của cả encoder và decoder. Khoảng 147.456 tham số train trong tổng 37,9 triệu tham số. Cờ đóng băng encoder của chế độ full fine-tune không áp dụng cho LoRA này: trọng số gốc đóng băng, LoRA encoder vẫn được train.

Batch 2, tích lũy 4 (batch hiệu dụng 8); tối đa 300 bước (~1,6 lượt qua tập train), learning rate 5e-5, warmup 5%, BF16 nếu GPU hỗ trợ, gradient checkpointing. Đánh giá mỗi 50 bước trên 64 mẫu validation, dừng sớm sau hai lần không cải thiện. Mỗi lần đọc audio có thể thêm nhiễu trắng/echo nhẹ/gain; không nhân bản dữ liệu ra đĩa. Giữ một nửa lượt lấy mẫu nguyên bản. Đây là nhiễu mô phỏng, không thay thế tiếng nói nhỏ thực tế.

Output `training-runs/phowhisper-tiny-lora/`:

- `adapter/`: adapter nhỏ có thể giữ để tái sử dụng.
- `final/`: model đầy đủ đã gộp LoRA để export.
- `baseline.json`, `comparison.json`, `run.json`: tham số và kết quả trước/sau.

Script từ chối ghi đè `final/` đang có. Nếu muốn train lại, chọn `--output` mới khi gọi trực tiếp `scripts/train_stt.py`; không chạy lặp lại wrapper vào cùng thư mục.

## Export và đánh giá

Wrapper export tiny gốc và tiny LoRA sang INT8 trong hai thư mục riêng:

- `models/whisper-phowhisper-tiny/`
- `models/whisper-phowhisper-tiny-lora/`

Hai bản tiny cùng base gốc được so sánh trên cùng 100 mẫu test (seed 42), dùng `examwatch.speech.Speech`: CPU 2 threads, VAD, beam 5, bộ lọc độ tin cậy. Đầu ra bị loại tính như lỗi, không bỏ mẫu. Báo cáo sạch: `training-runs/tiny-lora-int8-test.json`. Có phép thử bổ sung nhiễu trắng SNR 15 dB: `training-runs/tiny-lora-int8-noise-test.json`. WER Trainer và WER web khác pipeline, cần đọc riêng.

Chạy thử web sau khi dừng server đang chạy:

```powershell
.\start.ps1 -Whisper phowhisper-tiny-lora
```

Đối chứng tiny gốc: `-Whisper phowhisper-tiny`. Quay lại base gốc: `-Whisper phowhisper-base`. Không đổi mặc định web hay ghi đè bất kỳ model cũ nào.

## Kết quả lượt chạy 24/10/2026

Train dừng sớm ở 150 bước, thời gian Trainer ghi nhận 227,88 giây (3 phút 48 giây, gồm các lần đánh giá trong train; không gồm chuẩn bị, baseline, đánh giá cuối và kiểm thử INT8). Chọn checkpoint-50. WER validation 64 mẫu: tiny gốc 2,98%, LoRA 3,10%, chưa cải thiện trên validation.

100 mẫu test giống nhau, seed 42, sau export CPU INT8:

| Model | WER sạch (%) | WER nhiễu trắng 15 dB (%) |
|---|---:|---:|
| Tiny gốc | 10,60 | 12,88 |
| Tiny LoRA | 10,51 | 12,78 |
| Base gốc | 7,83 | 10,31 |

Tiny LoRA chỉ giảm khoảng 0,10 điểm phần trăm WER so với tiny gốc, tương ứng một lỗi từ trên bộ mẫu này; chưa phải cải thiện đáng kể. Base vẫn chính xác hơn. RTF đo trong lượt nhiễu: tiny gốc 0,224; tiny LoRA 0,219; base 0,390. Các lượt đo diễn ra khi web chính vẫn có thể hoạt động, không phải benchmark CPU cô lập.

Trọng số INT8 tiny gốc và tiny LoRA đều 40.520.007 byte, khoảng 40,5 MB; hash khác nhau xác nhận đã gộp cập nhật. Dataset gồm metadata khoảng 119,35 MiB. Các model base cũ giữ nguyên.

28 kiểm thử Python qua, JavaScript và script Python kiểm tra cú pháp thành công. Web thử tiny LoRA chạy riêng ở `http://localhost:8001`, dùng `.tmp/tiny-web-data`. Đã gửi ảnh và audio mẫu 5,04 giây qua API thật, nhận transcript, kết thúc phiên và xác nhận lịch sử trên trình duyệt. Bằng chứng `.tmp/tiny-web-result.json` và `.tmp/tiny-web-proof.png`. Không tuyên bố đã kiểm thử micro/camera trực tiếp hoặc độ chính xác phòng thi. Web chính cổng 8000 và phiên đang mở được giữ nguyên.
