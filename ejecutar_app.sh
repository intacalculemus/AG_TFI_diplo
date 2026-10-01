#!/bin/bash

echo "======================================================================"
echo "  🛰️ Iniciando Aplicación de Clasificación Satelital con IA"
echo "  Diplomatura ISBIA - Lidesia - UNC / Grupo_6_2026"
echo "======================================================================"
echo ""

# Verificar si Python3 está instalado
if ! command -v python3 &> /dev/null
then
    echo "[ERROR] No se encontró Python 3 instalado."
    echo "Por favor instalá Python 3.10 o superior."
    exit 1
fi

# Crear entorno virtual si no existe
if [ ! -d "venv" ]; then
    echo "[1/3] Creando entorno virtual aislado 'venv'..."
    python3 -m venv venv
fi

# Activar entorno virtual
echo "[2/3] Verificando dependencias necesarias..."
source venv/bin/activate

# Instalar requerimientos
pip install -r requirements.txt --quiet --disable-pip-version-check

echo "[3/3] Lanzando la aplicación web en tu navegador..."
echo ""
echo "======================================================================"
echo "  La app se abrirá en: http://localhost:8501"
echo "  (Para detener la app, presiona Ctrl + C en esta terminal)"
echo "======================================================================"
echo ""

streamlit run app.py
