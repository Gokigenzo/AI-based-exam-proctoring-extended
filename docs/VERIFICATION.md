# Kết quả kiểm chứng

Ngày 18/10/2026, trên máy phát triển Windows hiện tại.

## Đã xác nhận

- 19 tests Python đạt: phân quyền, token thu hồi, nguồn thu chéo thiết bị, batch rollback, UUID chống ghi trùng, checksum, URL ký hết hạn, giữ bản chép gốc, audit, retention retry, phục hồi outbox/ASR, tracking mơ hồ, cửa sổ biểu cảm, hình học/tư thế và CSRF local.
- Test tạo clip thực bằng FFmpeg/H.264, kiểm tra phát lại và thời lượng khoảng 15 giây; test dọn cache không xóa file chưa đồng bộ.
- Supabase có đủ 10 bảng, RLS bật cho tất cả, bucket `evidence` private. `tests/rls.sql` đã chạy trực tiếp: user chỉ thấy phòng của mình, không đọc token hash, không đọc speech trực tiếp, không ghi bảng từ client. Dữ liệu thử đã rollback.
- FER+ checkpoint gốc đã tải từ đường dẫn trong notebook TalkAI. ONNX opset 9 đạt agreement 100%, max probability error `2.682209014892578e-7` trên 100 tensor tổng hợp. Đây là **parity số học**, không phải accuracy FER+.
- Model smoke test: MediaPipe, FER+/YuNet, PhoWhisper-base, Silero VAD nạp thành công offline; khung trống không có pose/mặt, VAD không coi im lặng là tiếng nói. Đã sửa đường dẫn tiếng Việt bằng nạp model từ bộ nhớ cho MediaPipe/YuNet.
- Web production build và TypeScript đạt. Dependencies web Next.js 16.4.2/React 19.3.1; npm audit sau cập nhật báo 0 vulnerabilities.
- Browser QA với dữ liệu giả lập: đăng nhập demo, lọc/danh sách sự kiện, mở ảnh ký URL, lưu thẩm tra thấy audit, tải WAV giải mã thành công (duration 1 giây, readyState 4, không lỗi), chỉnh bản chép và mở lại bản gốc đều hoạt động.

Ảnh kiểm chứng và báo cáo JSON nằm trong `deliverables/verification/`.

## Chưa được coi là đạt nghiệm thu

- Chưa thu ca 90 phút bằng webcam/microphone thật trên máy đích; chưa đo FPS/CPU/RAM khi tất cả nhánh chạy cùng lúc.
- Chưa có tập ảnh/video/âm thanh phòng thi được gán nhãn để đo WER/CER, macro-F1, precision/recall và số cảnh báo giả mỗi giờ.
- Parity chưa được lặp trên tập khuôn mặt thật; chỉ có kiểm tra số học tổng hợp.
- Chưa thử bộ portable trên một máy Windows sạch khác.
- Chưa triển khai API/web production trên Render/Vercel: repo đã được chủ dự án chỉ định; secret production cần được cấu hình trực tiếp tại Render.
- Chưa có tài khoản giám thị thật hoặc phòng thật trên cloud; cần bootstrap membership sau khi tạo Auth user.

## Nghiệm thu thực địa

1. Chia người/clip hiệu chỉnh và kiểm tra riêng, không dùng lại cùng dữ liệu để chọn ngưỡng và báo điểm.
2. Thu ít nhất 30 lần cho đứng, nhổm/ngồi dậy, nghiêng và quay đầu; thêm ngồi viết bình thường, che khuất, ra/vào khung và hai người đi gần nhau.
3. Thu câu tiếng Việt rõ, nhỏ, nhiễu/chồng lời; đối chiếu bản chép bằng người nghe. Dùng `scripts/evaluate.py asr dataset.jsonl` để xuất WER/CER; mỗi dòng gồm `path`, `reference`.
4. Đánh giá phân loại bằng `scripts/evaluate.py classification predictions.jsonl`; mỗi dòng gồm `truth`, `prediction`. Không gộp biểu cảm với kết luận lo lắng/gian lận.
5. Chạy ca 90 phút, đo tốc độ thu và độ trễ; ngắt mạng 15 phút, khởi động lại app khi upload, rút camera và thử cảnh báo đĩa thấp.
6. Mục tiêu demo F10: precision ≥85%, recall ≥80% cho đứng/nghiêng đủ quan sát; cảnh báo video lên web ≤10 giây sau đủ điều kiện, bản chép ≤30 giây sau hết lời khi mạng ổn định. Nếu không đạt, công bố cấu hình đo được và hiệu chỉnh/tải lại model trước khi nghiệm thu.

Lưu ý: clip có 10 giây hình sau sự kiện nên chỉ sẵn sàng sau thời gian này cộng thời gian mã hóa/upload. Ảnh và metadata được gửi trước; không hứa clip hoàn chỉnh đã lên web trong 10 giây kể từ lúc kích hoạt.
