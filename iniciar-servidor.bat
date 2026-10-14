@echo off
REM Inicia o relay FastAPI (modo direto com Tailscale ou desenvolvimento local).
REM Uso normal (só neste PC):          iniciar-servidor.bat
REM Modo direto (celular via Tailscale): set JULIA_HOST=0.0.0.0 antes, ou:
REM   iniciar-servidor.bat 0.0.0.0
setlocal
if not exist requirements.txt (
  echo [ERRO] Execute este .bat dentro da pasta julia-mobile-v0.2
  pause
  exit /b 1
)
if "%~1"=="" (
  if "%JULIA_HOST%"=="" set JULIA_HOST=127.0.0.1
) else (
  set JULIA_HOST=%~1
)
pip install -r requirements.txt
echo [INFO] Relay em http://%JULIA_HOST%:8000
uvicorn server:app --host %JULIA_HOST% --port 8000
