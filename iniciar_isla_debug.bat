@echo off
setlocal
title JEV - Isla (diagnostico)
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
echo Iniciando la isla de JEV en modo visible...
echo Si algo falla, el error se mostrara aqui y en data\logs\jev_launcher.log
echo.
.\.venv\Scripts\python.exe jev_launcher.py
echo.
echo La isla se ha cerrado. Pulsa una tecla para salir.
pause >nul
