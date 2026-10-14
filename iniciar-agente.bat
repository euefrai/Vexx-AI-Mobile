@echo off
REM Inicia o agente do PC (SQLite local). Configure as variaveis antes de rodar.
REM Nunca compartilhe o fajulto_AGENT_TOKEN.
setlocal
if "%fajulto_RELAY_URL%"=="" set fajulto_RELAY_URL=http://127.0.0.1:8000
if "%fajulto_SQLITE_PATH%"=="" set fajulto_SQLITE_PATH=%USERPROFILE%\Documents\fajultoMobile\memory.sqlite3
if "%fajulto_AGENT_TOKEN%"=="" (
  echo [ERRO] Defina fajulto_AGENT_TOKEN com o mesmo segredo do servidor:
  echo   set fajulto_AGENT_TOKEN=SEU-SEGREDO-AQUI
  pause
  exit /b 1
)
python pc_agent.py
