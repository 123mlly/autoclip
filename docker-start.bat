@echo off
setlocal EnableExtensions
cd /d "%~dp0"

rem AutoClip Docker start script for Windows CMD
rem Mirrors docker-start.sh: production (default) / gpu / dev

set "MODE=production"
if /I "%~1"=="dev" set "MODE=dev"
if /I "%~1"=="gpu" set "MODE=gpu"
if /I "%~1"=="help" goto :help
if /I "%~1"=="-h" goto :help
if /I "%~1"=="--help" goto :help
if /I "%~1"=="/?" goto :help

echo.
echo ========================================
echo  AutoClip Docker start - mode: %MODE%
echo ========================================
echo.

where docker >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Docker not found. Install Docker Desktop and ensure docker is in PATH.
  exit /b 1
)

docker compose version >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Docker Compose not available. Update Docker Desktop.
  exit /b 1
)

docker info >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Docker is not running. Start Docker Desktop first.
  exit /b 1
)

echo [OK] Docker is ready.

if not exist ".env" (
  if exist "env.example" (
    copy /Y "env.example" ".env" >nul
    echo [WARN] Created .env from env.example. Fill in API keys before using AI.
  ) else (
    echo [ERROR] Neither .env nor env.example found.
    exit /b 1
  )
) else (
  echo [OK] .env exists.
)

findstr /R /C:"^API_DASHSCOPE_API_KEY=.\+" ".env" >nul 2>&1
if errorlevel 1 (
  echo [WARN] API_DASHSCOPE_API_KEY looks empty. AI features may not work.
)

echo.
echo [INFO] Building and starting services...
echo.

if /I "%MODE%"=="dev" (
  docker compose -f docker-compose.dev.yml up -d --build
  if errorlevel 1 goto :fail
  timeout /t 10 /nobreak >nul
  echo.
  echo Container status:
  docker compose -f docker-compose.dev.yml ps
  echo.
  echo Frontend: http://localhost:3000
  echo API:      http://localhost:8000
  echo Docs:     http://localhost:8000/docs
  echo.
  echo Logs:  docker compose -f docker-compose.dev.yml logs -f
  echo Stop:  docker compose -f docker-compose.dev.yml down
  goto :done
)

if /I "%MODE%"=="gpu" (
  where nvidia-smi >nul 2>&1
  if errorlevel 1 (
    echo [WARN] nvidia-smi not found. GPU overlay may fail without NVIDIA driver/toolkit.
  ) else (
    echo [OK] nvidia-smi detected.
    nvidia-smi -L 2>nul
  )
  docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d --build
  if errorlevel 1 goto :fail
  timeout /t 10 /nobreak >nul
  echo.
  echo Container status:
  docker compose -f docker-compose.yml -f docker-compose.gpu.yml ps
  echo.
  echo App:  http://localhost:8000
  echo Docs: http://localhost:8000/docs
  echo.
  echo Logs:  docker compose -f docker-compose.yml -f docker-compose.gpu.yml logs -f
  echo Stop:  docker compose -f docker-compose.yml -f docker-compose.gpu.yml down
  goto :done
)

docker compose up -d --build
if errorlevel 1 goto :fail
timeout /t 10 /nobreak >nul
echo.
echo Container status:
docker compose ps
echo.
echo App:  http://localhost:8000
echo API:  http://localhost:8000/api/v1
echo Docs: http://localhost:8000/docs
echo.
echo Logs:  docker compose logs -f
echo Stop:  docker compose down
echo GPU:   docker-start.bat gpu
goto :done

:fail
echo.
echo [ERROR] Failed to start services.
echo Check logs with: docker compose logs
exit /b 1

:done
echo.
echo Done. First build may take several minutes.
echo Make sure API_DASHSCOPE_API_KEY is set in .env for AI features.
exit /b 0

:help
echo AutoClip Docker start ^(Windows CMD^)
echo.
echo Usage:
echo   docker-start.bat
echo   docker-start.bat gpu
echo   docker-start.bat dev
echo   docker-start.bat help
echo.
echo   ^(none^)  Production CPU ^(default^)
echo   gpu     Production + NVIDIA GPU for Whisper worker
echo   dev     Development stack
exit /b 0
