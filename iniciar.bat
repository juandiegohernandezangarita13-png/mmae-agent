@echo off
setlocal enabledelayedexpansion
title MMAE // Isla Flotante
cd /d "%~dp0"
set "PYTHONIOENCODING=utf-8"

:: Si existe entorno virtual local, usarlo preferentemente
if exist "%~dp0.venv\Scripts\python.exe" (
    set "PY_EXE=%~dp0.venv\Scripts\python.exe"
    set "PYW_EXE=%~dp0.venv\Scripts\pythonw.exe"
) else (
    set "PY_EXE=python.exe"
    set "PYW_EXE=pythonw.exe"
)

:: Si se pasan argumentos desde terminal (ej: iniciar.bat "mi tarea" o -i), ejecutar en modo consola
if not "%~1"=="" (
    "%PY_EXE%" "%~dp0main.py" %*
    exit /b %ERRORLEVEL%
)

:: Arranque predeterminado: lanzar la Isla Flotante de escritorio directamente
if exist "%PYW_EXE%" (
    start "" "%PYW_EXE%" "%~dp0main.py" --desktop
) else (
    start "" "%PY_EXE%" "%~dp0main.py" --desktop
)
exit /b 0
