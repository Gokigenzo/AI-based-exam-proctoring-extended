# Tối ưu xử lý camera ngày 03 tháng 11 năm 2026

## Thay đổi

- Các mô hình được tái sử dụng trong bộ nhớ. Tối ưu chính là suy luận từng frame, không phải tải lại model mỗi frame.
- Pose Lite chạy engine một người khi chỉ thấy một người. Engine tối đa ba người được tạo một lần khi cần và tái sử dụng. Khi người thứ hai xuất hiện, chạy multi trên chính frame đó; giữ chế độ multi qua mất mặt ngắn nếu trước đó thấy nhiều người hoặc vẫn thấy nhiều bộ xương.
- Dò mặt YuNet chạy trong một worker song song với Pose Lite. Cả hai dùng chung đúng frame; backend vẫn chỉ xử lý một request camera tại một thời điểm. Không bỏ frame vào hàng đợi suy luận chồng chất.
- SFace theo chu kỳ 2 giây và cảm xúc theo chu kỳ 0,8 giây như trước; không giảm ngưỡng góc tay, nghiêng 20 độ, điều kiện thời gian hay visibility.
- Danh sách embedding lấy một lần khi bắt đầu phiên; đăng ký/xóa danh tính vốn bị khóa khi đang thu. Bỏ việc đọc SQLite/giải mã JSON gallery mỗi frame.
- Trình duyệt chỉ đổi kích thước canvas khi kích thước ảnh thay đổi. Giới hạn gửi ảnh tăng từ 10 lên 20 Hz; vẫn một request đang xử lý. Đây là trần gửi, không cam kết 20 FPS trên mọi máy.
- Camera tiếp tục vẽ ảnh và kết quả thành cặp để tránh lệch bbox. Hiển thị FPS AI đo theo nhịp kết quả, tách với FPS webcam. Giữ giới hạn video bằng chứng khoảng 5 FPS.

## Đối chứng trên máy phát triển

Đo trước/sau tuần tự bằng cùng video màn hình `nghieng.mp4`, crop vùng camera x=371, y=178, w=861, h=646. Lấy 38 frame cách nhau 0,5 giây; bỏ ba lần đầu khi tổng hợp độ trễ. Dùng cùng gallery fixture và mô phỏng hiệu chuẩn ở frame đầu. Đây không phải bản camera gốc, benchmark phòng thi hoặc đo độ chính xác độc lập.

| Chỉ tiêu | Trước | Sau |
|---|---:|---:|
| Trung vị suy luận hình ảnh | 127,0 ms | 55,1 ms |
| P95 | 180,7 ms | 103,3 ms |
| Frame có pose | 38/38 | 38/38 |
| Quan sát nhận đúng danh tính fixture | 30 | 30 |
| Góc nghiêng lớn nhất | 38,19 độ | 39,31 độ |
| Mốc phát cảnh báo trong video mô phỏng | 7,5 giây | 7,5 giây |

Trung vị giảm khoảng 56,6%. Các engine có trạng thái tracking khác nhau nên landmark/góc không giống từng số; trong phép thử này cảnh báo, số frame có pose và số quan sát nhận danh tính được giữ. Không suy rộng rằng mọi cảnh báo trong thực tế đều chính xác hơn.

Trên một ảnh cố định, một lượt đối chứng khác ghi nhận median 85,3 → 34,5 ms và P95 154,5 → 62,4 ms, nhãn danh tính/cảm xúc và việc có pose giữ nguyên. Hai phép đo có điều kiện khác nhau, không ghép thành một con số FPS chung.

Các thời gian trên là phần `Vision.process`, không bao gồm JPEG/HTTP/trình duyệt/ghi video hay chép lời đồng thời. Cần xem FPS AI và độ trễ trên dashboard khi chạy camera thật để đánh giá toàn luồng. Máy yếu hoặc ba người vẫn có thể chậm. Lần đầu chuyển sang multi có thêm chi phí khởi tạo, đồng thời giữ hai engine pose trong bộ nhớ.

## Kiểm chứng

55 test Python và 7 test JavaScript đạt, gồm chuyển multi ngay khi xuất hiện người thứ hai, không nạp lại engine mỗi frame, giữ khả năng nhiều người khi mất mặt ngắn, cache gallery, góc bụng 20 độ, luật tăng góc/giữ góc, encode/decode video và ghép đúng ảnh với kết quả.

Kết quả thô cục bộ: `.tmp/realtime-before.json`, `.tmp/realtime-comparison.json`, `.tmp/realtime-motion-comparison.json`. Nguồn trước thay đổi lưu ở `.tmp/vision_before_realtime.py` để đối chiếu.

Đây là cập nhật mã nguồn. Gói ZIP v2 trước đó chưa được build lại.
