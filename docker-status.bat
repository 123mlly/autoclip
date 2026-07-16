@echo off
setlocal EnableExtensions
cd /d "%~dp0"

rem AutoClip Docker status script for Windows CMD

set "MODE=production"
if /I "%~1"=="dev" set "MODE=dev"
if /I "%~1"=="gpu" set "MODE=gpu"
if /I "%~1"=="help" goto :help
if /I "%~1"=="-h" goto :help
if /I "%~1"=="--help" goto :help
if /I "%~1"=="/?" goto :help

echo.
echo [AutoClip] Service status - mode: %MODE%
echo.

where docker >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Docker not found.
  exit /b 1
)

docker info >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Docker is not running. Start Docker Desktop first.
  exit /b 1
)

if /I "%MODE%"=="dev" (
  docker compose -f docker-compose.dev.yml ps
  echo.
  echo Frontend: http://localhost:3000
  echo API:      http://localhost:8000
  echo Docs:     http://localhost:8000/docs
  exit /b 0
)

if /I "%MODE%"=="gpu" (
  docker compose -f docker-compose.yml -f docker-compose.gpu.yml ps
) else (
  docker compose ps
)

echo.
echo App:  http://localhost:8000
echo API:  http://localhost:8000/api/v1
echo Docs: http://localhost:8000/docs
echo.
echo Logs: docker compose logs -f
exit /b 0

:help
echo Usage:
echo   docker-status.bat
echo   docker-status.bat gpu
echo   docker-status.bat dev
exit /b 0
