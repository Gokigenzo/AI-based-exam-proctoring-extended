# Cảnh báo góc tay và nghiêng thân

Cập nhật mã nguồn ngày 03/11/2026. Dùng lại MediaPipe Pose Lite, không tải thêm model.

## Góc và điều kiện

- Mỗi tay đo riêng góc giữa đoạn vai–khuỷu và hướng thân xuống dưới, trong mặt phẳng ảnh. Không phân loại bàn tay/ngón tay. Vượt 45 độ gắn cờ; góc đã làm mượt tăng thêm ít nhất 5 độ so với lúc gắn cờ, cách tối thiểu 0,5 giây, thì tạo cảnh báo `arm_raise` và video. Tay giữ nguyên góc không tự tạo video.
- Độ nghiêng thân dùng đường từ tâm hai vai tới tâm hai hông so với phương thẳng đứng ảnh. Từ 30 độ gắn cờ; giữ từ 30 độ ít nhất 2 giây hoặc tăng thêm ít nhất 5 độ sau tối thiểu 0,5 giây tạo `body_lean` và video.
- Nếu không thấy hông đủ rõ, dùng pháp tuyến đường hai vai hướng xuống dưới để ước lượng nghiêng và hướng thân. Dashboard ghi rõ ước lượng từ vai. Đây không phải phép đo trục thân hoàn chỉnh khi mất hông.
- Tọa độ chuyển sang pixel trước khi tính góc để tránh sai do tỷ lệ ảnh. Chỉ dùng điểm hữu hạn, trong ảnh và visibility từ 0,6; đoạn xương quá ngắn bị loại.
- Làm mượt EMA 0,5; hysteresis 5 độ khi xóa cờ. Mỗi đợt chỉ tạo một cảnh báo cho từng tay/thân. Thiếu landmark hoặc gián đoạn quá 2,5 giây reset bộ đếm; đổi nguồn hông/vai cũng reset để tránh tăng góc giả. Khi đổi sang một danh tính khác, trạng thái được xóa cùng tracking.
- Cờ là trạng thái trực tiếp theo track, hiển thị cạnh góc đo trong danh sách thí sinh. Chỉ khi đạt điều kiện video mới tạo bản ghi cảnh báo lâu dài trong SQLite.

## Bằng chứng và giới hạn

Tái sử dụng clip WebM khoảng 10 giây trước và 5 giây sau cảnh báo, không tiếng, tối đa khoảng 5 FPS từ frame phân tích. Clip ngắn hơn khi đầu/cuối phiên thiếu dữ liệu. Lịch sử xem video với nhãn riêng cho góc tay, nghiêng thân và nhổm dậy. Phần khác giữ định dạng cũ, không thay schema SQLite.

Đây là đo hình học 2D phụ thuộc góc đặt camera. Camera phải cố định và thẳng; chưa bù roll camera. Nghiêng người trong ảnh không đủ kết luận ngó bài, nhìn sang bên hoặc gian lận. Tay đưa lên có thể là hành vi bình thường. Giám thị phải xem clip trước khi đánh giá. Chưa có benchmark camera phòng thi thật.

Thay đổi nằm trong mã nguồn; `release/v1` và `release/v2.zip` đã phát hành không được sửa trong lần này.

## Điều chỉnh góc nghiêng và gốc bụng

Ngưỡng nghiêng hiện là 20 độ, thay cho 30 độ mô tả trong phiên bản đầu ở trên. Điều kiện giữ 2 giây hoặc tăng thêm 5 độ và video khoảng 15 giây vẫn giữ nguyên.

Gốc đo đặt gần bụng: khi hông rõ, lấy điểm trên trục vai–hông cách tâm vai 75% chiều dài trục, rồi đo tia từ điểm đó lên tâm vai với phương thẳng đứng hướng lên. Đây là điểm nội suy, không phải landmark bụng riêng của MediaPipe. Chỉ đổi gốc trên cùng trục không tự thay đổi góc; khác biệt quan trọng khi hông bị che là dùng gốc cố định theo hiệu chuẩn thay vì pháp tuyến đường vai.

Khi không đủ visibility ở hông, hiệu chuẩn ngồi lưu gốc bụng ước lượng dưới tâm vai, cách khoảng một bề rộng vai. Các frame sau đo so với gốc này; chưa hiệu chuẩn thì không tính góc nghiêng bằng fallback. Khi camera/người đổi chỗ phải hiệu chuẩn lại. Dashboard vẽ gốc bụng, đường thẳng đứng, đường lên tâm vai và góc so với 20 độ. Phần giơ tay không đổi tham chiếu.
