@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo.
echo  Local AI Studio - installer
echo  (Korean messages are shown by the PowerShell step below)
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\install.ps1"
echo.
pause
