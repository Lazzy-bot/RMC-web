@echo off
echo ==========================================
echo  RMC Assistant - Docker Launcher
echo ==========================================

REM Kiểm tra Docker có đang chạy không
docker info >nul 2>&1
if %errorlevel% neq 0 (
    echo [LOI] Docker Desktop chua chay. Mo Docker Desktop truoc roi thu lai.
    pause
    exit /b 1
)

echo [0/3] Dang dung va don dep cac container cu (tranh xung dot ngrok)...
docker-compose down

echo [1/3] Dang build image...
docker-compose build

echo [2/3] Dang khoi dong container...
set "NGROK_REPLICAS=1"
set /p NGROK_REPLICAS="Nhap so luong ban sao (replicas) Ngrok de tu dong can bang tai (Endpoint Pools) [Mac dinh: 1]: "
docker-compose up -d --scale ngrok=%NGROK_REPLICAS%

echo [3/3] Kiem tra trang thai...
timeout /t 3 /nobreak >nul
docker-compose ps

echo.
echo =============================================================
echo  [KHOI CHAY THANH CONG]
echo.
echo  1. Truy cap truc tiep (Local Host):
echo     http://localhost:5000
echo.
echo  2. Truy cap qua Tunnel (Cloudflare Quick Tunnel):
echo     (Dang lay duong dan tu logs...)
docker logs cloudflared-tunnel 2>&1 | findstr "trycloudflare.com"
echo     (Neu khong thay duong dan o tren, hay go: docker logs cloudflared-tunnel)
echo.
echo  3. Truy cap qua Tunnel (Ngrok):
echo     https://balance-rotting-blooming.ngrok-free.dev
echo.
echo  4. Xem trang thai Tunnel (Ngrok Dashboard):
echo     (Da tat port mapping co dinh 4040 de ho tro Scaling/Pooling)
echo =============================================================
echo.
echo De xem log ung dung: docker-compose logs -f rmc-assistant
echo De xem log Cloudflare Tunnel: docker-compose logs -f cloudflare-tunnel
echo De xem log Ngrok Tunnel:      docker-compose logs -f ngrok
echo De dung ung dung:    docker-compose down
echo.
pause
