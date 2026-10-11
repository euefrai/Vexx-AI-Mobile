@echo off
REM Inicia o relay FastAPI localmente (desenvolvimento). Rode dentro da pasta do projeto.
setlocal
if not exist requirements.txt (
  echo [ERRO] Execute este .bat dentro da pasta julia-mobile-v0.2
  pause
  exit /b 1
)
pip install -r requirements.txt
uvicorn server:app --host 127.0.0.1 --port 8000
