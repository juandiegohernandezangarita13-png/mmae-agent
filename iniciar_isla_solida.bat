@echo off
setlocal
title JEV - Isla (fondo solido)
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
set JEV_ISLAND_OPAQUE=1
start "" "%~dp0.venv\Scripts\pythonw.exe" "%~dp0jev_launcher.py"
exit /b 0
