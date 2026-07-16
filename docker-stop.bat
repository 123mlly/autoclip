@echo off
setlocal EnableExtensions
cd /d "%~dp0"

rem AutoClip Docker stop script for Windows CMD
rem Mirrors docker-stop.sh: production (default) / gpu / dev

set "MODE=production"
if /I "%~1"=="dev" set "MODE=dev"
if /I "%~1"=="gpu" set "MODE=gpu"
if /I "%~1"=="help" goto :help
if /I "%~1"=="-h" goto :help
if /I "%~1"=="--help" goto :help
if /I "%~1"=="/?" goto :help

echo.
echo [AutoClip] Stopping services - mode: %MODE%
echo.

where docker >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Docker not found.
  exit /b 1
)

if /I "%MODE%"=="dev" (
  docker compose -f docker-compose.dev.yml down
  if errorlevel 1 goto :fail
  goto :done
)

rem Production / gpu: tear down with gpu overlay when present
docker compose -f docker-compose.yml -f docker-compose.gpu.yml down 2>nul
if errorlevel 1 (
  docker compose -f docker-compose.yml down
  if errorlevel 1 goto :fail
)

:done
echo [OK] Services stopped.
exit /b 0

:fail
echo [ERROR] Failed to stop services.
exit /b 1

:help
echo Usage:
echo   docker-stop.bat
echo   docker-stop.bat gpu
echo   docker-stop.bat dev
exit /b 0
