@echo off
title TFI_Grupo_6_2026 - Clasificacion de Coberturas con IA
cd /d "%~dp0"
echo ======================================================================
echo   Iniciando Aplicacion de Clasificacion Satelital con IA
echo   Diplomatura ISBIA - Lidesia - UNC / Grupo_6_2026
echo   Directorio: %CD%
echo ======================================================================
echo.
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] No se encontro Python instalado en tu sistema.
    pause
    exit /b 1
)
:: Liberar puerto 8501 si quedo una instancia vieja abierta de otra carpeta
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":8501" ^| findstr "LISTENING"') do (
    echo Cerrando instancia previa en puerto 8501 (PID %%a)...
    taskkill /F /PID %%a >nul 2>&1
)
if exist "venv\Scripts\activate.bat" (
    echo Activando entorno virtual venv...
    call venv\Scripts\activate.bat
)
echo Lanzando la aplicacion web en tu navegador (http://localhost:8501)...
echo.
python -m streamlit run app.py --server.port 8501
pause
