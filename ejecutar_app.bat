@echo off
chcp 65001 > nul
title TFI_Grupo_6_2026: Clasificación de Coberturas del suelo con Agentes IA

echo ======================================================================
echo   🛰️ Iniciando Aplicación de Clasificación Satelital con IA
echo   Diplomatura ISBIA - Lidesia - UNC / Grupo_6_2026
echo ======================================================================
echo.

:: Verificar si Python está instalado
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] No se encontró Python instalado en tu sistema.
    echo Por favor descargá e instalá Python 3.10 o superior desde https://www.python.org/
    echo Asegurate de marcar la casilla "Add Python to PATH" durante la instalación.
    pause
    exit /b 1
)

:: Crear entorno virtual si no existe
if not exist "venv" (
    echo [1/3] Creando entorno virtual aislado 'venv'...
    python -m venv venv
    if %errorlevel% neq 0 (
        echo [ERROR] No se pudo crear el entorno virtual.
        pause
        exit /b 1
    )
)

:: Activar entorno virtual
echo [2/3] Verificando dependencias necesarias...
call venv\Scripts\activate.bat

:: Instalar o actualizar dependencias
pip install -r requirements.txt --quiet --disable-pip-version-check

echo [3/3] Lanzando la aplicación web en tu navegador...
echo.
echo ======================================================================
echo   La app se abrirá automáticamente en: http://localhost:8501
echo   (Para cerrar la aplicación, cerrá esta ventana de consola)
echo ======================================================================
echo.

streamlit run app.py

pause
