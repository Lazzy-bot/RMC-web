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

# FIX #1: Tăng --timeout từ 75 → 300s (OneDrive/Graph API có thể chậm 60-90s)
#         Tăng --threads từ 4 → 8 để xử lý nhiều request đồng thời hơn
#         Thêm --worker-connections để không drop connection khi busy
#         Thêm --log-level info để dễ debug hơn
CMD ["gunicorn", \
     "--bind", "0.0.0.0:5000", \
     "--workers", "1", \
     "--threads", "8", \
     "--worker-class", "gthread", \
     "--timeout", "300", \
     "--keep-alive", "75", \
     "--graceful-timeout", "60", \
     "--log-level", "info", \
     "--access-logfile", "-", \
     "app:wsgi_app"]
