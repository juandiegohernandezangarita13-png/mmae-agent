@echo off
setlocal enabledelayedexpansion
title MMAE // Launcher
cd /d "%~dp0"
set "PYTHONIOENCODING=utf-8"

set "PY_EXE=python.exe"
set "PYW_EXE=pythonw.exe"

:: Si se pasa 'app', abrir directamente la aplicación de chat estilo Claude
if /i "%~1"=="app" (
    start "" python.exe "%~dp0app.py"
    exit /b 0
)

:: Si se pasan argumentos desde terminal (ej: iniciar.bat "mi tarea" o -i), ejecutar en modo consola
if not "%~1"=="" (
    python.exe "%~dp0main.py" %*
    exit /b %ERRORLEVEL%
)

:: Cerrar cualquier instancia previa huérfana para asegurar código fresco
taskkill /F /IM pythonw.exe >nul 2>&1

:: Arranque predeterminado: lanzar el Widget Flotante de escritorio directamente
start "" pythonw.exe "%~dp0main.py" --desktop
exit /b 0
