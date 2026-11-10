@echo off
chcp 65001 >nul
title Instalador e Configurador Portátil - VEXX AI (PC Agent ^& LLM)
echo ======================================================================
echo           VEXX AI - INSTALADOR UNIVERSAL PARA QUALQUER PC
echo ======================================================================
echo.

cd /d "%~dp0"
set "APP_DIR=%~dp0"
set "VENV_DIR=%APP_DIR%.venv"
set "PYTHON_EXE="

:: 1. Verificar se ja existe venv configurado nesta pasta
if exist "%VENV_DIR%\Scripts\python.exe" (
    echo [OK] Ambiente virtual local (.venv) encontrado!
    set "PYTHON_EXE=%VENV_DIR%\Scripts\python.exe"
    goto INSTALAR_DEPENDENCIAS
)

:: 2. Detectar Python do Sistema (py launcher ou python direto)
echo [*] Detectando instalador Python no sistema...
where py >nul 2>nul
if %errorlevel%==0 (
    for /f "delims=" %%i in ('py -3 -c "import sys; print(sys.executable)" 2^>nul') do set "SYS_PY=%%i"
    if defined SYS_PY (
        echo [OK] Python detectado via py launcher: %SYS_PY%
        goto CRIAR_VENV
    )
)

where python >nul 2>nul
if %errorlevel%==0 (
    for /f "delims=" %%i in ('python -c "import sys; print(sys.executable)" 2^>nul') do set "SYS_PY=%%i"
    if defined SYS_PY (
        echo [OK] Python detectado no PATH: %SYS_PY%
        goto CRIAR_VENV
    )
)

:: 3. Procurar em pastas padroes do Windows
for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python3*") do (
    if exist "%%D\python.exe" (
        set "SYS_PY=%%D\python.exe"
        echo [OK] Python encontrado em %%D
        goto CRIAR_VENV
    )
)

for /d %%D in ("C:\Python3*") do (
    if exist "%%D\python.exe" (
        set "SYS_PY=%%D\python.exe"
        echo [OK] Python encontrado em %%D
        goto CRIAR_VENV
    )
)

:: 4. Se Python nao for encontrado, tenta instalar via Winget automaticamente
echo [!] Python nao localizado. Tentando instalar Python 3.11 automaticamente via Winget...
winget install Python.Python.3.11 --silent --accept-package-agreements --accept-source-agreements
if %errorlevel%==0 (
    echo [OK] Python instalado via Winget! Reiniciando deteccao...
    timeout /t 3 >nul
    for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python3*") do (
        if exist "%%D\python.exe" (
            set "SYS_PY=%%D\python.exe"
            goto CRIAR_VENV
        )
    )
)

echo [ERRO] Python nao encontrado neste computador!
echo Por favor, instale o Python 3.10 ou 3.11 marcando 'Add Python to PATH':
echo https://www.python.org/downloads/
pause
exit /b 1

:CRIAR_VENV
echo.
echo [*] Criando ambiente virtual isolado (.venv)...
"%SYS_PY%" -m venv "%VENV_DIR%"
if not exist "%VENV_DIR%\Scripts\python.exe" (
    echo [ERRO] Falha ao criar ambiente virtual em %VENV_DIR%
    pause
    exit /b 1
)
set "PYTHON_EXE=%VENV_DIR%\Scripts\python.exe"
echo [OK] Ambiente virtual criado com sucesso!

:INSTALAR_DEPENDENCIAS
echo.
echo [*] Instalando dependencias essenciais para o agente e servidor local...
"%PYTHON_EXE%" -m pip install --upgrade pip --quiet
"%PYTHON_EXE%" -m pip install --quiet uvicorn fastapi pystray pillow requests websockets huggingface_hub llama-cpp-python

echo.
echo [*] Configurando inicializacao automatica com o Windows (oculta em segundo plano)...
reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v "VexxAI_Agent" /t REG_SZ /d "\"%VENV_DIR%\Scripts\pythonw.exe\" \"%APP_DIR%vexx_qwen_vl_tray.pyw\"" /f >nul 2>&1
if %errorlevel%==0 (
    echo [OK] Inicializacao automatica ativada no registro do Windows!
) else (
    echo [AVISO] Nao foi possivel gravar no registro; voce pode iniciar manualmente pelo icone.
)

echo.
echo [*] Iniciando servico do VEXX AI agora...
start "" "%VENV_DIR%\Scripts\pythonw.exe" "%APP_DIR%vexx_qwen_vl_tray.pyw"

echo.
echo ======================================================================
echo       TUDO PRONTO! O VEXX AI JA ESTA RODANDO NESTE COMPUTADOR.
echo ======================================================================
echo - O icone do VEXX AI aparecera na bandeja do sistema (proximo ao relogio).
echo - O servidor local estara ativo na porta 8008.
echo - O tunel seguro conectara automaticamente com https://vexx-ai.space.
echo.
timeout /t 5
