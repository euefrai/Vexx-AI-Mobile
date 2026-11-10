@echo off
cd /d "%~dp0"
if exist ".venv\Scripts\pythonw.exe" (
    start "" ".venv\Scripts\pythonw.exe" "vexx_qwen_vl_tray.pyw"
) else (
    where pythonw >nul 2>nul
    if %errorlevel%==0 (
        start "" pythonw "vexx_qwen_vl_tray.pyw"
    ) else (
        start "" python "vexx_qwen_vl_tray.pyw"
    )
)
