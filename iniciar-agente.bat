@echo off
REM Inicia o agente do PC (SQLite local). Configure as variaveis antes de rodar.
REM Nunca compartilhe o FAJULTO_AGENT_TOKEN.
setlocal
if "%FAJULTO_RELAY_URL%"=="" set FAJULTO_RELAY_URL=http://127.0.0.1:8000
if "%FAJULTO_SQLITE_PATH%"=="" set FAJULTO_SQLITE_PATH=%USERPROFILE%\Documents\FAJULTOMobile\memory.sqlite3
if "%FAJULTO_AGENT_TOKEN%"=="" (
  echo [ERRO] Defina FAJULTO_AGENT_TOKEN com o mesmo segredo do servidor:
  echo   set FAJULTO_AGENT_TOKEN=SEU-SEGREDO-AQUI
  pause
  exit /b 1
)
python pc_agent.py
