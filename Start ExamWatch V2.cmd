@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
 echo Run: powershell -NoProfile -ExecutionPolicy Bypass -File .\prepare.ps1
 pause
 exit /b 1
)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start.ps1"
if errorlevel 1 pause
