# Zipformer nguyên mẫu trong web

Theo lựa chọn sau thử nghiệm, Zipformer nguyên mẫu là mặc định trong
start.ps1 và Settings. Chạy `.\start.ps1` sẽ dùng bản gốc. Các bản LoRA
được giữ để tham khảo; chỉ chạy khi chọn rõ tên model.

Model: hynt/Zipformer-30M-RNNT-6000h, bản INT8 do Sherpa phát hành ngày
2026-02-09. Không fine-tune, không gợi ý đáp án hoặc sửa kết quả nhận dạng.
Nguồn: https://k2-fsa.github.io/sherpa/onnx/pretrained_models/offline-transducer/zipformer-transducer-models.html
Model và hash được lưu tại `models/zipformer-vi-30m/source.json`.
Giấy phép model: CC-BY-NC-ND-4.0.

```powershell
.\start.ps1 -Whisper zipformer-vi-30m
# Quay lại model cũ:
.\start.ps1 -Whisper phowhisper-base
```

Dừng server trước khi chạy lệnh khác trên cùng cổng. Model cũ được giữ nguyên.
Sherpa-ONNX 1.13.8 chạy CPU, 2 luồng mặc định, greedy search. Đây là model
offline, nhận từng đoạn theo khoảng ngừng nói từ pipeline web hiện có;
không phải decoder streaming liên tục. Mỗi đoạn có trạng thái giải mã riêng.
Giữ nguyên chữ hoa của model và không bổ sung model dấu câu.
Mốc thời gian transcript là đầu/cuối đoạn âm thanh, không phải từng từ.
Đoạn có RMS dưới 0.002 bị bỏ; chưa có VAD phía server cho backend Zipformer.
Các ngưỡng độ tin cậy riêng của Whisper không áp dụng cho Zipformer.

Thử WAV người dùng 8 giây: khoảng 0.114 giây xử lý trong một lượt CPU,
không bao gồm tải model/capture/queue. Vẫn sai đáp án và thiếu cuối câu,
không coi thời gian một lượt hoặc một mẫu là kết quả benchmark tổng quát.
29 bài kiểm tra Python đã đạt sau tích hợp.

## Thử bản LoRA

`models/zipformer-vi-30m-lora` là bản merge từ best-joiner.pt của lượt
`training-runs/zipformer-vivos-lora-cosine100-dropout`, epoch 6, không phải
epoch cuối 29. Merge đủ ba lớp: encoder_proj vào graph encoder, decoder_proj
vào graph decoder và output_linear vào graph joiner. Không thể chỉ thay
joiner.onnx vì các phép chiếu đã được gộp vào hai graph còn lại.
Encoder và joiner được lượng tử hóa động INT8 MatMul; decoder giữ FP32.
Hash và nguồn checkpoint ở source.json trong thư mục model mới.

```powershell
.\start.ps1 -Whisper zipformer-vi-30m-lora
```

Tên trên dashboard: Zipformer 30M LoRA · epoch 6. Bản gốc được giữ nguyên.
Kiểm tra 100 đoạn test qua Speech thực tế sau export: gốc INT8 WER 3,9643%,
LoRA ONNX WER 3,8652%. Đây là phép thử nhỏ, khác phép đánh giá TorchScript
FP32 trước export (cả hai 3,8652%), chưa thể kết luận tăng độ chính xác trong
phòng thi. Chi tiết: onnx-web-comparison.json trong thư mục lượt train.

## Bản LR thấp, epoch 10

Lựa chọn `zipformer-vi-30m-lora-low-lr20` dùng best-joiner.pt (epoch 10)
từ `training-runs/zipformer-vivos-lora-low-lr20`. Model được merge/export
riêng tại `models/zipformer-vi-30m-lora-low-lr20`; các bản cũ được giữ nguyên.
Nhãn dashboard: Zipformer LoRA LR thấp · epoch 10.

```powershell
.\start.ps1 -Whisper zipformer-vi-30m-lora-low-lr20
```

100 đoạn test qua pipeline Speech ONNX INT8: WER 3,8652%; kiểm tra hệ thống
29 passed. Báo cáo trong `training-runs/zipformer-vivos-lora-low-lr20/onnx-web-evaluation.json`.
