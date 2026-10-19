@echo off
setlocal
cd /d "%~dp0"
if exist "dist\DiskCleanerStudio\DiskCleanerStudio.exe" (
    start "" "dist\DiskCleanerStudio\DiskCleanerStudio.exe" %*
    exit /b
)
if not exist ".venv\Scripts\pythonw.exe" (
    powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup.ps1"
    if errorlevel 1 (
        pause
        exit /b 1
    )
)
start "" ".venv\Scripts\pythonw.exe" "%~dp0run.py" %*
