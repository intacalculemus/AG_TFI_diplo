# ==============================================================================
# Dockerfile Endurecido (Hardened) con Sandbox OS para Agente GeoReAct
# Diplomatura Universitaria ISBIA - Lidesia - FCEFyN (UNC) / Grupo_6_2026
# ==============================================================================
FROM python:3.11-slim-bookworm

# Evitar archivos .pyc y habilitar logs en tiempo real
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    STREAMLIT_SERVER_PORT=8501 \
    STREAMLIT_SERVER_ADDRESS=0.0.0.0 \
    STREAMLIT_SERVER_HEADLESS=true \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

# 1. Instalar dependencias de sistema para GDAL, Rasterio y Geoespacial
RUN apt-get update && apt-get install -y --no-install-recommends \
    gdal-bin \
    libgdal-dev \
    libspatialindex-dev \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 2. Crear usuario sin privilegios de root (Sandbox a nivel Sistema Operativo)
RUN groupadd -r appgroup && useradd -r -g appgroup -m -d /home/appuser appuser

WORKDIR /app

# 3. Instalar dependencias de Python en caché
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# 4. Copiar el código fuente de la aplicación y ajustar permisos de directorios permitidos
COPY . .
RUN mkdir -p /app/outputs /app/data /app/rag/data && \
    chown -R appuser:appgroup /app

# 5. Activar Sandbox de Usuario No-Privilegiado (impide escalada de privilegios)
USER appuser

EXPOSE 8501

# 6. Verificación de salud del contenedor
HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD curl --fail http://localhost:8501/_stcore/health || exit 1

CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]
