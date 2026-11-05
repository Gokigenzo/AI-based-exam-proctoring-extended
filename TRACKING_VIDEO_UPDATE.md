# Giữ hiệu chuẩn và video bằng chứng nhổm dậy

Cập nhật ngày 25/10/2026 cho mã nguồn web localhost.

## Theo dõi và hiệu chuẩn

- Giữ track tối đa 8 giây khi mất cả mặt lẫn tín hiệu cơ thể thay vì xóa sau 1 giây.
- Baseline ngồi không bị xóa chỉ vì một frame thiếu mặt hoặc một lần SFace trả chưa xác định.
- Ghép bằng IoU, bổ sung cổng khoảng cách tâm và tỷ lệ bbox cho đầu đang dịch lên. Trường hợp mơ hồ tạo track mới, không tự chuyển baseline.
- Khi không thấy mặt, tiếp tục chạy Pose Lite để ghép đầu/vai với track trước. Chỉ ghép khi đầu/vai đủ visibility, vị trí và tỷ lệ phù hợp, ứng viên không mơ hồ. Quan sát cơ thể mới giữ track tồn tại.
- Baseline của danh tính đã xác nhận được giữ riêng trong bộ nhớ phiên, có thể phục hồi sau khi track hết hạn và nhận diện lại. Danh tính khác phải dùng baseline riêng. Kết thúc hoặc bắt đầu phiên mới xóa bộ nhớ này.
- Không tích lũy thời gian đứng khi không còn quan sát cơ thể hợp lệ. Khi chỉ theo dõi cơ thể, cảm xúc chuyển về chưa rõ và không vẽ lại điểm miệng cũ.

Tracking vẫn dựa trên hình học và không thay thế hệ thống re-identification toàn thân. Người giao nhau, che khuất dài hoặc đổi vị trí có thể mất dấu; hệ thống ưu tiên không gán baseline khi mơ hồ.

## Video bằng chứng

- Cảnh báo `standing` mới lưu WebM VP8 thay cho JPEG. Cảnh báo cảm xúc và ảnh lịch sử cũ vẫn xem như trước.
- Bộ đệm giữ tối đa khoảng 10 giây trước cảnh báo; sau cảnh báo thu thêm 5 giây rồi mã hóa nền. Không ghi liên tục toàn phiên xuống đĩa.
- Mục tiêu khoảng 15 giây. Đầu phiên chưa có đủ pre-roll, camera ngừng hoặc kết thúc phiên sớm thì clip ngắn hơn; không tạo thêm diễn biến giả để đủ thời lượng.
- Video không có âm thanh, dùng các frame nhận được qua API camera, tối đa khoảng 5 khung hình/giây và kích thước vừa trong 640×480. Vì vậy mật độ frame vẫn phụ thuộc tốc độ gửi/xử lý ảnh; không phải bản quay camera gốc tốc độ cao.
- Frame được xuất theo lưới thời gian 5 FPS; khi thiếu frame, giữ frame gần nhất và hiển thị `source age` để thấy độ cũ của nguồn. Thời gian trong overlay là thời gian tương đối, mốc cảnh báo/phiên vẫn lưu trong SQLite.
- JPEG buffer có giới hạn 85 frame; video được mã hóa bằng một worker riêng. File được ghi tạm rồi đổi tên khi hoàn tất để trình duyệt không đọc file đang ghi.
- Dashboard/lịch sử hiển thị đang hoàn tất, xem video hoặc lỗi tạo video. Video có nút điều khiển phát và API `GET /api/alerts/{id}/video`.
- Cột `image` hiện hữu lưu tên tệp bằng chứng kể cả WebM để tương thích dữ liệu cũ; API thêm `evidence_type` và `evidence_status`. Không thay schema SQLite.
- Clip nằm trong thư mục `data/evidence` của môi trường đang chạy. Không kèm audio STT vào clip.

## Kiểm chứng

Các test bao gồm mất mặt nhưng còn đầu/vai, giữ bộ đếm đứng, khôi phục track sau dịch chuyển lên, giữ baseline, ghép mơ hồ, cache theo phiên, encode/decode WebM thật, thời lượng khoảng 15 giây và flush clip ngắn khi dừng. Các test dùng đầu vào tổng hợp/fixture; chưa thay thế thử nghiệm camera thật tại phòng thi.

Thay đổi áp dụng cho mã nguồn hiện tại. Thư mục và ZIP `release/v1` đã phát hành chưa được build lại trong lần cập nhật này.
