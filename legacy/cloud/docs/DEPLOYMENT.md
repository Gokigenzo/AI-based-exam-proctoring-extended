# Triển khai cloud

Supabase đã tạo: `examwatch`, ref `vsjgnaibivncznmpnrzw`, Singapore. Schema đầu tiên và private bucket `evidence` đã áp dụng. Các bảng public bật RLS; trình duyệt không có quyền ghi trực tiếp. Bảng speech/reviews chỉ được đọc qua API để thực thi hết hạn trước khi cleanup chạy.

## 1. Repo mới

Repo được chủ dự án chỉ định: `https://github.com/Gokigenzo/AI-based-exam-proctoring-extended`. Không đẩy `data/`, `models/`, `.env`, `.venv`, `dist` hoặc token. Không sử dụng repo/service cũ `examine-sys`.

## 2. Supabase

- Tạo tài khoản giám thị trong Auth Dashboard; tắt public signup cho demo có quản trị.
- Cấu hình `SITE_URL`/redirect URL theo domain web được chọn.
- Lấy connection string **session pooler** tương thích IPv4 và server secret/service-role key trong Dashboard; điền trực tiếp vào secret env của Render, không đưa vào chat/Git.
- Chạy `scripts/bootstrap_cloud.py --email <email-tài-khoản>` với các secret env có sẵn để tạo phòng và quyền admin. Script không in secret.
- Database driver: URL dạng `postgresql+psycopg://...`; user/password có ký tự đặc biệt phải URL-encode.
- Khi triển khai mới từ đầu, áp dụng migration trong `supabase/migrations/`. Không áp dụng lại migration đã chạy trên project hiện tại.

## 3. Render API

Import `render.yaml` từ repo trên vào workspace đã chọn. Cung cấp:

| Biến | Giá trị |
|---|---|
| `EXAMWATCH_DATABASE_URL` | Connection string Postgres, server-only |
| `EXAMWATCH_SUPABASE_KEY` | Supabase server secret/service role, server-only |
| `EXAMWATCH_ALLOWED_ORIGINS` | JSON array domain Vercel chính xác, ví dụ `["https://examwatch.example"]` |
| `EXAMWATCH_SUPABASE_URL` | Đã đặt URL project trong Blueprint |

`EXAMWATCH_ENV=production` bắt buộc Postgres, HTTPS CORS và cấm demo token. `/healthz` kiểm tra kết nối DB.

Blueprint mặc định free để không tự phát sinh phí. Free instance có thể ngủ: xử lý local vẫn tiếp tục, web đồng bộ chậm khi API thức lại. Cleanup chạy lúc startup và mỗi giờ khi API hoạt động; dùng instance luôn bật hoặc lịch `examwatch-cleanup` để bảo đảm thời gian xóa vật lý. API chặn truy cập ngay khi hết hạn dù file chờ xóa.

## 4. Vercel web

Import cùng repo, Root Directory=`web`, framework Next.js. Điền:

```text
NEXT_PUBLIC_API_URL=https://<render-service>.onrender.com
NEXT_PUBLIC_SUPABASE_URL=https://vsjgnaibivncznmpnrzw.supabase.co
NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY=<publishable key>
NEXT_PUBLIC_DEMO_MODE=false
```

Các biến trên là public. Không đặt khóa đặc quyền trong `NEXT_PUBLIC_*`. Deploy preview, kiểm tra đăng nhập→phòng→phiên→bằng chứng→thẩm tra, rồi promote production đã kiểm thử. Cập nhật CORS backend theo domain web; không dùng `*`.

## 5. Sau triển khai

Đăng nhập admin, đăng ký thiết bị, chép token vào app local. Thu ca thử; kiểm tra source heartbeat, outbox về 0, clip/âm thanh phát được, user phòng khác bị từ chối, token thu hồi không gửi được, bản sửa có audit, URL xem hết hạn sau 5 phút.

Rollback code trên Render/Vercel về release trước. Migration hiện chỉ thêm schema; không rollback bằng cách xóa bảng đang có bằng chứng. Sao lưu trước thay đổi schema sau này.
