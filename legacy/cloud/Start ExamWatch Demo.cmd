@echo off
setlocal
cd /d "%~dp0"
set "EXAMWATCH_PYTHON=%~dp0.venv\Scripts\python.exe"
if not exist "%EXAMWATCH_PYTHON%" set "EXAMWATCH_PYTHON=%~dp0dist\ExamWatch\runtime\python.exe"
if not exist "%EXAMWATCH_PYTHON%" (
  echo Python runtime not found. See docs\WINDOWS.md for setup.
  pause
  exit /b 1
)
"%EXAMWATCH_PYTHON%" "%~dp0scripts\start_demo.py"
if errorlevel 1 pause
