@echo off
setlocal
title JEV - Isla de escritorio
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
start "" "%~dp0.venv\Scripts\pythonw.exe" "%~dp0jev_launcher.py"
exit /b 0
