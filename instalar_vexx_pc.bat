@echo off
chcp 65001 >nul
title VEXX AI - Qwen 2.5-VL 7B ^& Túnel PC
color 0B

echo.
echo  ==============================================================
echo     ⚡ VEXX AI — SERVIÇO EM SEGUNDO PLANO ^& QWEN 2.5-VL (7B)
echo  ==============================================================
echo.
echo  [*] Verificando ambiente Python e dependências locais...

set "PYTHONW_BIN=C:\Users\efrai\Documents\very\backend\venv\Scripts\pythonw.exe"
set "TRAY_SCRIPT=C:\Users\efrai\Documents\ia-local\vexx_qwen_vl_tray.pyw"

if not exist "%PYTHONW_BIN%" (
    echo  [ERRO] Ambiente Python não encontrado em:
    echo         %PYTHONW_BIN%
    pause
    exit /b 1
)

if not exist "%TRAY_SCRIPT%" (
    echo  [ERRO] Script de bandeja não encontrado em:
    echo         %TRAY_SCRIPT%
    pause
    exit /b 1
)

echo  [*] Configurando inicialização automática com o Windows...
reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v "VexxAI_Agent" /t REG_SZ /d "\"%PYTHONW_BIN%\" \"%TRAY_SCRIPT%\"" /f >nul

echo  [*] Iniciando VEXX AI em segundo plano (modo oculto)...
start "" "%PYTHONW_BIN%" "%TRAY_SCRIPT%"

echo.
echo  ==============================================================
echo    ✓ VEXX AI ATIVADO COM SUCESSO!
echo  ==============================================================
echo.
echo    1. O serviço está rodando em segundo plano de forma oculta.
echo    2. Ele iniciará automaticamente sempre que o Windows abrir.
echo    3. Veja o ícone nos ÍCONES OCULTOS da bandeja (System Tray).
echo    4. O túnel com https://vexx-ai.space está conectado.
echo    5. O modelo Qwen 2.5-VL (7B) está sendo preparado/executado.
echo.
echo    O APK para celular foi gerado em:
echo    C:\Users\efrai\Documents\VexxAI.apk
echo.
echo  ==============================================================
echo  Pressione qualquer tecla para fechar esta janela...
pause >nul
exit /b 0
