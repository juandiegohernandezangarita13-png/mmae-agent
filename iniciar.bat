@echo off
title MMAE // Launcher
cd /d "%~dp0"
set "PYTHONIOENCODING=utf-8"

set "PY_EXE=C:\Users\juand\AppData\Roaming\uv\python\cpython-3.11.16-windows-x86_64-none\python.exe"

if not exist "%PY_EXE%" (
    set "PY_EXE=python.exe"
)

if /i "%~1"=="app" (
    start "" "%PY_EXE%" "%~dp0jev_launcher.py" --classic
    exit /b 0
)

if /i "%~1"=="telegram" (
    "%PY_EXE%" "%~dp0jev\interfaces\telegram_bot.py"
    exit /b %ERRORLEVEL%
)

if not "%~1"=="" (
    "%PY_EXE%" "%~dp0main.py" %*
    exit /b %ERRORLEVEL%
)

taskkill /F /IM python.exe >nul 2>&1
start "" "%PY_EXE%" "%~dp0jev_launcher.py"
exit /b 0
