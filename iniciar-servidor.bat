@echo off
REM Inicia o relay FastAPI (modo direto com Tailscale ou desenvolvimento local).
REM Uso normal (só neste PC):          iniciar-servidor.bat
REM Modo direto (celular via Tailscale): set fajulto_HOST=0.0.0.0 antes, ou:
REM   iniciar-servidor.bat 0.0.0.0
setlocal
if not exist requirements.txt (
  echo [ERRO] Execute este .bat dentro da pasta fajulto-mobile-v0.2
  pause
  exit /b 1
)
if "%~1"=="" (
  if "%fajulto_HOST%"=="" set fajulto_HOST=127.0.0.1
) else (
  set fajulto_HOST=%~1
)
pip install -r requirements.txt
echo [INFO] Relay em http://%fajulto_HOST%:8000
uvicorn server:app --host %fajulto_HOST% --port 8000
