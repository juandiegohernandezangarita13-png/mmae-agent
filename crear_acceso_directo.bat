@echo off
setlocal
title JEV - Crear acceso directo en el escritorio
cd /d "%~dp0"

echo.
echo  Creando el acceso directo de JEV en el escritorio...
echo.

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\install_desktop_shortcut.ps1" %*
set "RC=%ERRORLEVEL%"

echo.
if not "%RC%"=="0" (
    echo  [ERROR] No se pudo crear el acceso directo. Codigo: %RC%
    echo  Revisa los mensajes anteriores.
) else (
    echo  Listo. Ya puedes abrir JEV desde el icono del escritorio.
)
echo.
pause
exit /b %RC%
