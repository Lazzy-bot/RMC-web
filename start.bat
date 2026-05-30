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

echo [1/3] Dang build image...
docker-compose build

echo [2/3] Dang khoi dong container...
docker-compose up -d

echo [3/3] Kiem tra trang thai...
timeout /t 3 /nobreak >nul
docker-compose ps

echo.
echo ==========================================
echo  App dang chay tai: http://localhost:5000
echo  Mo trinh duyet va truy cap dia chi tren
echo ==========================================
echo.
echo De dung app:  docker-compose down
echo De xem log:   docker-compose logs -f
echo.
pause
