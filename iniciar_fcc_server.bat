@echo off
title Free Claude Code - Proxy Server (JEV Local Integration)
cd /d "%~dp0"
echo =====================================================================
echo INICIANDO SERVIDOR LOCAL FREE-CLAUDE-CODE (FCC-SERVER)
echo Proxy Anthropic Messages API -> OpenRouter / Free Models
echo Endpoint: http://127.0.0.1:8082
echo =====================================================================

if not exist "tools\free-claude-code\.venv\Scripts\fcc-server.exe" (
    echo [ERROR] No se encontro el binario fcc-server.exe en tools\free-claude-code\.venv\Scripts\
    pause
    exit /b 1
)

set FCC_OPEN_BROWSER=false
tools\free-claude-code\.venv\Scripts\fcc-server.exe
pause
