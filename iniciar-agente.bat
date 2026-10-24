@echo off
REM Inicia o agente do PC (SQLite local). Configure as variaveis antes de rodar.
REM Nunca compartilhe o JULIA_AGENT_TOKEN.
setlocal
if "%JULIA_RELAY_URL%"=="" (
  echo [ERRO] Configure JULIA_RELAY_URL explicitamente para producao ou desenvolvimento.
  exit /b 1
)
if "%JULIA_SQLITE_PATH%"=="" (
  echo [ERRO] Configure JULIA_SQLITE_PATH explicitamente para evitar outro banco.
  exit /b 1
)
if "%JULIA_AGENT_TOKEN%"=="" (
  echo [ERRO] Defina JULIA_AGENT_TOKEN com o mesmo segredo do servidor:
  echo   set JULIA_AGENT_TOKEN=SEU-SEGREDO-AQUI
  pause
  exit /b 1
)
pushd "%~dp0"
python pc_agent.py
set "VEXX_AGENT_EXIT=%errorlevel%"
popd
exit /b %VEXX_AGENT_EXIT%
