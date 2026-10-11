@echo off
REM Inicia o agente do PC (SQLite local). Configure as variaveis antes de rodar.
REM Nunca compartilhe o JULIA_AGENT_TOKEN.
setlocal
if "%JULIA_RELAY_URL%"=="" set JULIA_RELAY_URL=http://127.0.0.1:8000
if "%JULIA_SQLITE_PATH%"=="" set JULIA_SQLITE_PATH=%USERPROFILE%\Documents\JuliaMobile\memory.sqlite3
if "%JULIA_AGENT_TOKEN%"=="" (
  echo [ERRO] Defina JULIA_AGENT_TOKEN com o mesmo segredo do servidor:
  echo   set JULIA_AGENT_TOKEN=SEU-SEGREDO-AQUI
  pause
  exit /b 1
)
python pc_agent.py
