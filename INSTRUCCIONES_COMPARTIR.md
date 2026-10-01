# 🚀 Guía para Compartir y Ejecutar la Aplicación

**Proyecto:** "TFI_Grupo_6_2026: Clasificación de Coberturas del suelo con Agentes IA"  
**Ámbito:** Diplomatura Universitaria ISBIA - Lidesia - FCEFyN (UNC) | **Grupo_6_2026**

---

## 📦 1. Cómo preparar los archivos para Google Drive

Para compartir la aplicación de forma limpia y liviana con tus compañeros:

1. **Qué incluir (esencial):**
   - 📄 `app.py` *(Código principal de la aplicación Streamlit)*
   - 📄 `config.py` y `requirements.txt` *(Configuración y librerías)*
   - 📄 `ejecutar_app.bat` *(Iniciador en 1 clic para Windows)*
   - 📄 `ejecutar_app.sh` *(Iniciador para Mac/Linux)*
   - 📁 `agent/` *(Lógica del Agente ReAct y prompts)*
   - 📁 `services/` *(Conexión a STAC Planetary Computer y Geocodificación IGN)*
   - 📁 `tools/` *(Herramientas satelitales y RAG)*
   - 📁 `rag/` *(Base de conocimiento con manuales y comparativas)*
   - 📁 `outputs/` *(Carpeta para guardar mapas y clasificaciones)*
   - 📁 `data/` *(Datos auxiliares)*

2. **Qué NO subir a Google Drive (carpetas pesadas o temporales):**
   - ❌ Carpetas `venv/` o `.venv/` *(cada compañero generará su propio entorno limpio al ejecutar)*.
   - ❌ Carpetas `__pycache__/` *(archivos temporales de compilación)*.

> **💡 Consejo práctico:** Comprimí toda la carpeta del proyecto en un archivo **`.zip`** (por ejemplo `App_Grupo_6_2026.zip`) y subilo a la carpeta compartida de Google Drive.

---

## 💻 2. Instrucciones para tus Compañeros

Copiá y pegales este texto a tus compañeros para que puedan ejecutar la app fácilmente:

---

### 🟢 Opción A: Ejecución Rápida en 1 Clic (Recomendada para Windows)

1. Descargá y descomprimí la carpeta del proyecto desde el Google Drive.
2. Asegurate de tener instalado **Python 3.10 o superior** (al instalarlo en Windows, tildá la casilla *"Add Python to PATH"*).
3. Hacé **doble clic en el archivo `ejecutar_app.bat`**.
4. El script automáticamente:
   - Creará el entorno virtual (`venv`).
   - Instalará todas las librerías necesarias (`requirements.txt`).
   - Abrirá la aplicación en tu navegador web en `http://localhost:8501`.

---

### 🍏 Opción B: Ejecución en Mac o Linux

1. Abrí la Terminal en la carpeta del proyecto.
2. Dale permisos de ejecución al script:
   ```bash
   chmod +x ejecutar_app.sh
   ./ejecutar_app.sh
   ```
3. La aplicación se abrirá en `http://localhost:8501`.

---

### ⚙️ Opción C: Ejecución Manual Paso a Paso (Terminal / VS Code)

Si prefieren ejecutarlo manualmente por línea de comandos:

1. **Abrir una terminal** en la raíz del proyecto.
2. **Crear y activar un entorno virtual:**
   - **En Windows:**
     ```bash
     python -m venv venv
     venv\Scripts\activate
     ```
   - **En Mac / Linux:**
     ```bash
     python3 -m venv venv
     source venv/bin/activate
     ```
3. **Instalar las dependencias:**
   ```bash
   pip install -r requirements.txt
   ```
4. **Iniciar la aplicación:**
   ```bash
   streamlit run app.py
   ```

---

### 🐍 Opción D: Si utilizan Anaconda / Conda / Miniforge

1. Abrir **Anaconda Prompt** o la terminal con Conda.
2. Crear y activar un entorno:
   ```bash
   conda create -n geo_app python=3.10 -y
   conda activate geo_app
   ```
3. Instalar librerías:
   ```bash
   pip install -r requirements.txt
   ```
4. Ejecutar:
   ```bash
   streamlit run app.py
   ```

---

## 🛠️ ¿Qué funcionalidades van a encontrar tus compañeros?

- **Visor Satelital Multicapa:** Google Satélite Híbrido, Google Maps Calles, Google Terreno, Google Satélite Puro, OpenStreetMap y Esri Satélite.
- **Geocodificación Argentina Automática:** Muestra la Provincia, Departamento y Municipio oficial (IGN Georef) del área seleccionada.
- **Doble Motor de Clasificación:**
  1. **Modelo IA ESA WorldCover (10m):** Mosaico anual multitemporal (Sentinel-2 + Sentinel-1 SAR) en 8+ clases taxonómicas.
  2. **Umbralización NDVI Sentinel-2 L2A:** Búsqueda histórica de escenas (2020–2024) y cálculo multiespectral a 10m.
- **Asistente ReAct y RAG:** Razonamiento sobre métricas cuantitativas reales y consultas sobre la arquitectura del código.
