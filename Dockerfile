FROM python:3.11-slim

WORKDIR /app

# Cài dependencies
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source
COPY backend/ ./backend/
COPY frontend/ ./frontend/

# Tạo thư mục data mặc định (bị mount đè khi chạy thật)
RUN mkdir -p /data/Cache \
             /data/Report_Form_Cache \
             /data/NOTE \
             /data/IMAGE/LAYOUT \
             /data/IMAGE/GATEWAY \
             /data/IMAGE/SENSOR \
             /data/IMAGE/ALARMPOINT \
             /data/DOCUMENTARY \
             /data/METADATA

EXPOSE 5000

WORKDIR /app/backend

# Dùng gunicorn thay flask dev server
# --threads 8: đủ thread để xử lý nhiều request khi OneDrive chậm
# --timeout 75: giới hạn thời gian mỗi request, không để treo quá lâu
# --keepalive 5: giữ kết nối sống 5s giữa các request
# --graceful-timeout 30: cho phép request đang xử lý hoàn thành trước khi restart
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "1", "--threads", "8", "--worker-class", "gthread", "--timeout", "75", "--keep-alive", "5", "--log-level", "warning", "app:wsgi_app"]
