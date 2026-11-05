# Lưu trữ hệ thống cloud trước khi chuyển sang v2

`cloud/` giữ nguyên mã API, Next.js, local-agent, Supabase và tài liệu của commit ff98d2d. Lịch sử Git không bị viết lại. Mã này không tham gia ứng dụng v2 mặc định ở gốc repo; workflow cũ nằm trong cloud/.github nên không được GitHub Actions tự chạy.

README/lệnh cũ giả định thư mục repo trước khi chuyển, do đó chỉ là tham khảo lịch sử, không cam kết chạy nguyên trạng từ vị trí lưu trữ. Muốn phát triển nhánh cloud riêng nên checkout commit trước chuyển đổi vào thư mục khác và chuẩn bị môi trường riêng. Không dùng chung data, virtualenv hoặc cổng với v2.
