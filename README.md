# RMC Report Assistant — Web Version

## Cấu trúc dự án

```
rmc-assistant/
├── backend/
│   ├── app.py              ← Flask entry point
│   ├── config.py           ← Cấu hình toàn bộ hằng số
│   ├── auth/
│   │   └── azure_auth.py   ← Azure AD / MSAL
│   ├── services/
│   │   ├── onedrive.py     ← OneDrive API
│   │   ├── metadata.py     ← Đồng bộ metadata
│   │   ├── report.py       ← Fill template, đọc report
│   │   └── note.py         ← CRUD Note/Reminder
│   ├── routes/
│   │   ├── auth_routes.py
│   │   ├── report_routes.py
│   │   ├── contact_routes.py
│   │   ├── note_routes.py
│   │   ├── image_routes.py
│   │   └── docs_routes.py
│   └── requirements.txt
│
└── frontend/
    ├── index.html
    └── assets/
        ├── style.css
        └── app.js
```

## Cài đặt

### 1. Tạo môi trường Python

```bash
cd backend
python -m venv venv

# Windows
venv\Scripts\activate

# macOS/Linux
source venv/bin/activate

pip install -r requirements.txt
```

### 2. Cấu hình (tuỳ chọn)

Tạo file `.env` trong thư mục `backend/`:

```env
# Azure AD (mặc định đã có trong config.py)
AZURE_CLIENT_ID=ac4edccf-a8ee-41aa-bcc4-6603c4bebae1
AZURE_TENANT_ID=5983a1d2-f46b-492d-a9b3-7e2f3609d20b

# OAuth cho đăng nhập người dùng (Microsoft / Google)
MS_OAUTH_CLIENT_ID=...
MS_OAUTH_CLIENT_SECRET=...
GOOGLE_OAUTH_CLIENT_ID=...
GOOGLE_OAUTH_CLIENT_SECRET=...

# Secret key cho Flask session
APP_SECRET_KEY=your-random-secret

# Hard admin account(s), phân tách bằng dấu phẩy
ADMIN_EMAILS=dung.ho@aeondelight.biz

# OneDrive share link gốc
BASE_SHARE_LINK=https://aeondelight-my.sharepoint.com/...

# Thư mục lưu trữ local (mặc định D:\RMC_Assistant_ver1.1)
RMC_BASE_DIR=D:\RMC_Assistant_ver1.1
```

### 3. Chạy backend

```bash
cd backend
python app.py
```

Backend sẽ chạy tại: **http://localhost:5000**

### 4. Mở frontend

Mở trình duyệt và truy cập: **http://localhost:5000**

Hoặc mở trực tiếp file `frontend/index.html` (cần CORS cho dev mode).

---

## API Endpoints

| Method | Endpoint | Mô tả |
|--------|----------|-------|
| GET  | `/api/auth/providers` | Danh sách provider đăng nhập đã bật |
| GET  | `/api/auth/me` | Trạng thái phiên user hiện tại |
| GET  | `/api/auth/login/{provider}` | Bắt đầu OAuth login (microsoft/google) |
| GET  | `/api/auth/callback/{provider}` | OAuth callback |
| POST | `/api/auth/logout` | Đăng xuất |
| GET  | `/api/auth/admin/users` | Admin xem danh sách user |
| POST | `/api/auth/admin/users` | Admin thêm user |
| POST | `/api/auth/admin/users/{id}/approve` | Admin phê duyệt user |
| DELETE | `/api/auth/admin/users/{id}` | Admin xóa user |
| POST | `/api/auth/graph/device-flow` | Bắt đầu device flow cho Graph token |
| GET  | `/api/auth/graph/device-flow/poll` | Poll trạng thái Graph login |
| GET  | `/api/sites` | Danh sách sites |
| GET  | `/api/sites/{key}/items` | Items của một site |
| POST | `/api/report/text` | Đọc nội dung report |
| POST | `/api/sync` | Đồng bộ OneDrive |
| POST | `/api/contact` | Fill template Contact |
| POST | `/api/status` | Fill template Status |
| POST | `/api/notification` | Fill template Notification |
| GET  | `/api/notes` | Danh sách notes |
| POST | `/api/notes` | Tạo note mới |
| DELETE | `/api/notes/{stt}` | Xóa note |
| GET  | `/api/notes/pending` | Notifications chờ xử lý |
| GET  | `/api/images/categories` | Danh mục ảnh DAVITEQ |
| GET  | `/api/images/{cat}/{site}` | Danh sách ảnh |
| GET  | `/api/images/file/{cat}/{site}/{name}` | Serve ảnh |
| GET  | `/api/docs` | Danh sách tài liệu |
| POST | `/api/docs/download/{id}` | Tải tài liệu |
| GET  | `/api/docs/file/{id}` | Serve tài liệu |
| POST | `/api/docs/refresh` | Làm mới danh sách |

---

## Lưu ý quan trọng

- **Token cache**: File `token_cache.bin` lưu ở `CACHE_DIR`. Lần đầu cần đăng nhập, các lần sau tự động refresh.
- **User approval**: User đăng nhập lần đầu sẽ ở trạng thái `pending`; chỉ truy cập được khi admin phê duyệt.
- **User DB**: Danh sách user lưu tại `METADATA/users.json`.
- **Reminder notifications**: Backend chạy schedule. Frontend poll `/api/notes/pending` mỗi 30 giây bằng cơ chế Polling thông minh (tự động dừng khi ẩn tab / `document.hidden` để tối ưu tài nguyên máy chủ và tránh nghẽn luồng, tự động kích hoạt lại sau khi tab được mở với độ trễ an toàn 1 giây). Trình duyệt sẽ yêu cầu quyền `Notification` khi khởi động.
- **CORS**: Đã cấu hình `flask-cors`. Nếu serve frontend từ domain khác cần cập nhật `origins` trong `app.py`.
- **Tkinter đã bỏ hoàn toàn**: Không cần `tkinter`, `tkcalendar`, `pyperclip`, `PIL` nữa.

---

## Cân bằng tải với Ngrok Endpoint Pools

Khi ứng dụng gặp lượng truy cập lớn, việc sử dụng duy nhất một cổng kết nối (endpoint) có thể gây gián đoạn hoặc chậm dịch vụ. Dự án đã tích hợp tính năng **Ngrok Endpoint Pools** cho phép chạy nhiều bản sao (replicas) của đường truyền Ngrok để tự động cân bằng tải (load balance).

### Cách hoạt động
Khi tính năng này được kích hoạt, bạn có thể chạy nhiều container Ngrok cùng lúc kết nối đến cùng một URL tĩnh (`https://balance-rotting-blooming.ngrok-free.dev`). Các yêu cầu từ người dùng gửi đến URL này sẽ tự động được phân phối đều giữa các container Ngrok đang hoạt động.

### Hướng dẫn sử dụng

1. **Khởi chạy thông qua `start.bat`**:
   * Khi khởi chạy bằng `start.bat`, script sẽ hỏi bạn số lượng bản sao (replicas) muốn chạy.
   * Nhập số lượng mong muốn (ví dụ: `2` hoặc `3`) và nhấn Enter.

2. **Chạy bằng dòng lệnh**:
   * Khởi động Docker Compose với số lượng bản sao mong muốn bằng tham số `--scale`:
     ```bash
     docker-compose up -d --scale ngrok=2
     ```
     *(Lưu ý: Bạn có thể thay đổi số lượng replicas động bất cứ lúc nào bằng cách chạy lại lệnh trên với số lượng mới)*

### Lợi ích
* **Tăng khả năng xử lý**: Giúp hệ thống chịu được lượng truy cập cao hơn.
* **Linh hoạt**: Dễ dàng thêm hoặc bớt các bản sao mà không cần đăng ký lại tên miền.
* **Độ tin cậy cao**: Nếu một trong các bản sao gặp sự cố, các bản sao còn lại vẫn tiếp tục duy trì hoạt động bình thường.

