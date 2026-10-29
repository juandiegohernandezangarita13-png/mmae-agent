@echo off
title JEV - JARVIS AI Desktop App
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
echo Iniciando JEV - JARVIS Local AI Core...
.\.venv\Scripts\python.exe app.py
pause
