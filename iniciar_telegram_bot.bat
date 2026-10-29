@echo off
title JEV - Telegram Remote Control Bot
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
echo ========================================================
echo   Iniciando JEV - Telegram Remote Control (Long Polling)
echo   Fast Path + Fallback LLM Activo
echo ========================================================
.\.venv\Scripts\python.exe interfaces/telegram_bot.py
pause
