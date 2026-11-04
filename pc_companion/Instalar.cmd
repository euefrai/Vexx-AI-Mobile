@echo off
setlocal
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0instalar.ps1"
if errorlevel 1 (
  echo.
  echo A instalacao nao foi concluida. Confira a mensagem acima.
  pause
  exit /b 1
)
exit /b 0
