# Thử nghiệm Zipformer joiner LoRA với VIVOS

Script: `scripts/train_zipformer_lora.py`. Đây là LoRA thực sự trên ba lớp
linear của joiner: encoder_proj, decoder_proj và output_linear, rank 8,
alpha 16. Encoder và prediction decoder được đóng băng, không phải LoRA
toàn bộ mạng và không sử dụng script train Whisper.

Nguồn model là `hynt/Zipformer-30M-RNNT-6000h`, revision
`ad6f873b5f5b6ed083821253a88d81afed2505c4`. File TorchScript gốc nằm ở
`.tmp/zipformer-training-probe/jit_script.pt`; hash được ghi trong run.json.
Không thay trọng số model web trong quá trình này. Model có giấy phép
CC-BY-NC-ND-4.0; đầu ra là thử nghiệm cục bộ, không được tự động phân phối.

TorchScript không cho thay trực tiếp lớp bằng PEFT. Script dựng lại joiner
bằng PyTorch và nạp trọng số, giữ nguyên encoder/decoder TorchScript.
Kiểm tra joiner trước LoRA cho sai số tối đa 0 trên tensor thử ngẫu nhiên.
4 đoạn smoke test cho cùng chuỗi dự đoán với bản ONNX INT8 của web.
Đây là kiểm tra giới hạn, không phải chứng minh hai backend tương đương
trên mọi đầu vào.

Đặc trưng: Kaldi-native-fbank, 80 bins, 16 kHz, dither 0, snip_edges false,
low_freq 20, high_freq -400, waveform float [-1,1] như Sherpa mặc định.
Không nhân biên độ 32768. Đã phát hiện và sửa lỗi thang biên độ trong lượt
smoke đầu; chỉ smoke-v2 và lượt train đầy đủ dùng tiền xử lý đúng.
Tokenizer BPE gốc dùng chữ hoa, RNNT loss blank 0 từ torchaudio CUDA.

Dataset: tập VIVOS nhỏ hiện có, 1467 train / 100 validation / 100 test,
tách source giữa train và validation. Chưa xác nhận VIVOS có trong dữ liệu
huấn luyện gốc hay không. Đây không phải phép đánh giá hội thoại phòng thi.

Batch size được thử 1,2,4,8,16,32 theo hình dạng padding tệ nhất của tập
train; chọn mức có peak bộ nhớ tensor dưới 70% tổng VRAM. Kiểm tra gradient
hữu hạn và khác 0. Đặc trưng frozen encoder/decoder được cache CPU để giảm
tính toán. Không augmentation âm thanh vì cache cố định trong thử nghiệm
này. Train FP32, AdamW LR 1e-4, 3 epoch, clip gradient 5, seed 42.

Chọn checkpoint bằng validation WER, có cả baseline làm ứng viên. Test chỉ
đánh giá ở cuối sau chọn checkpoint. Nếu mọi checkpoint tệ hơn baseline,
best-joiner.pt và adapter.pt tương ứng baseline; last-joiner.pt vẫn giữ
trọng số LoRA đã train của epoch cuối. Không tự nạp kết quả vào web.

```powershell
$env:OMP_NUM_THREADS='2'
$env:OPENBLAS_NUM_THREADS='2'
.\.venv-training\Scripts\python.exe -u scripts/train_zipformer_lora.py --epochs 3 --max-batch 32
```

Chọn --output mới cho lần train khác. Không tái sử dụng frozen-features.pt
khi đổi dataset, tiền xử lý hoặc model nguồn; chọn thư mục output mới.
Kết quả tại training-runs/zipformer-vivos-lora gồm run.json,
baseline.json, comparison.json, best-joiner.pt, last-joiner.pt và adapter.pt.
Đây chưa phải gói ONNX triển khai. Trước khi đưa vào web cần merge LoRA,
export joiner, kiểm tra cùng encoder/decoder ONNX và đánh giá lại độ chính
xác sau lượng tử hóa.

## Lượt tối đa 100 epoch với warmup và cosine

Output riêng: `training-runs/zipformer-vivos-lora-cosine100`. Khởi tạo lại từ
model gốc, không ghi đè lượt 3 epoch. Tái sử dụng cache đặc trưng đã kiểm
tra model hash và danh sách audio/nhãn, không tính encoder lại.

```powershell
.\.venv-training\Scripts\python.exe -u scripts/train_zipformer_lora.py --epochs 100 --max-batch 16 --learning-rate 0.0001 --min-learning-rate 0.000001 --warmup-ratio 0.05 --patience 10 --min-delta 0.01 --feature-cache training-runs/zipformer-vivos-lora/frozen-features.pt --output training-runs/zipformer-vivos-lora-cosine100
```

92 update/epoch, tối đa 9200 update. Warmup tuyến tính 460 update (5 epoch),
sau đó cosine giảm LR từ 1e-4 về 1e-6 theo từng update. Dừng sớm nếu WER
validation không giảm ít nhất 0,01 điểm phần trăm trong 10 epoch liên tiếp.
Giá trị validation bằng nhau không reset patience. Checkpoint tốt nhất vẫn
được chọn theo WER thấp nhất, gồm baseline; không dùng test để chọn.
Nếu early stop thì lịch cosine dừng tại update tương ứng, không ép xuống
LR tối thiểu. progress.json được cập nhật sau mỗi epoch; last-training-state.pt
giữ trọng số, optimizer, bước và trạng thái RNG cho việc khôi phục sau này
(script hiện chưa có cờ tự động resume).

Log lượt nền: `.tmp/zipformer-cosine100.log` và
`.tmp/zipformer-cosine100-errors.log`. Web vẫn dùng Zipformer nguyên bản.

## Lượt điều chỉnh warmup và dropout

Lượt cosine100 cũ dừng sớm ở epoch 14. Theo yêu cầu tiếp theo, chạy lại từ
model gốc vào `training-runs/zipformer-vivos-lora-cosine100-dropout`, giữ
nguyên mọi kết quả cũ. Các thay đổi:

- Warmup 10% = 920 update = 10 epoch trên tối đa 100 epoch; sau đó cosine.
- AdamW (đã dùng từ đầu), LR đỉnh 1e-4, tối thiểu 1e-6, weight decay 0,01.
- LoRA dropout 0,1 chỉ trên nhánh cập nhật hạng thấp; tắt khi validation/test.
- Chỉ đếm epoch không cải thiện từ epoch 20; trước đó stale_epochs luôn 0.
  Patience 10 nên sớm nhất có thể dừng tại cuối epoch 29. Vẫn ghi nhận và
  lưu checkpoint tốt nhất từ đầu, không bỏ kết quả tốt ở giai đoạn warmup.
- Batch size tối đa 16, tối đa 100 epoch, cùng cache đặc trưng VIVOS.

Các cờ bổ sung: `--warmup-ratio 0.10 --early-stopping-start-epoch 20
--lora-dropout 0.1`. Log mới: `.tmp/zipformer-cosine100-dropout.log`;
lỗi ở `.tmp/zipformer-cosine100-dropout-errors.log`.
