@echo off
REM Inicia o relay FastAPI (modo direto com Tailscale ou desenvolvimento local).
REM Uso normal (só neste PC):          iniciar-servidor.bat
REM Modo direto (celular via Tailscale): set FAJULTO_HOST=0.0.0.0 antes, ou:
REM   iniciar-servidor.bat 0.0.0.0
setlocal
if not exist requirements.txt (
  echo [ERRO] Execute este .bat dentro da pasta FAJULTO-mobile-v0.2
  pause
  exit /b 1
)
if "%~1"=="" (
  if "%FAJULTO_HOST%"=="" set FAJULTO_HOST=127.0.0.1
) else (
  set FAJULTO_HOST=%~1
)
pip install -r requirements.txt
echo [INFO] Relay em http://%FAJULTO_HOST%:8000
uvicorn server:app --host %FAJULTO_HOST% --port 8000
