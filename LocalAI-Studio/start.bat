@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
set PYTHONUTF8=1
set PYTHONDONTWRITEBYTECODE=1
set "PY=engine\ComfyUI_windows_portable\python_embeded\python.exe"
if not exist "%PY%" (
  echo [!] Engine not found. Run install.bat first.
  pause
  exit /b 1
)
"%PY%" -s hub\hub.py
pause
