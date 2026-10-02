"""
Módulo de Configuración Global del Agente Geoespacial ReAct (TFI ISBIA / INTA)
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# Cargar variables de entorno desde .env si existe
load_dotenv()

# Rutas del Proyecto
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
RAG_DATA_DIR = BASE_DIR / "rag" / "data"
OUTPUTS_DIR = BASE_DIR / "outputs"

# Crear directorios si no existen
DATA_DIR.mkdir(parents=True, exist_ok=True)
RAG_DATA_DIR.mkdir(parents=True, exist_ok=True)
OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)

# Configuración del Proveedor LLM
# Soporta tanto HuggingFace Router como OpenAI directo
HF_TOKEN = os.getenv("HF_TOKEN", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
MODEL_ID_ENV = os.getenv("MODEL_ID", "")

# Prioridad de endpoints: HuggingFace Router si hay HF_TOKEN, sino OpenAI
if HF_TOKEN:
    LLM_BASE_URL = "https://router.huggingface.co/v1"
    LLM_API_KEY = HF_TOKEN
    DEFAULT_MODEL = MODEL_ID_ENV or "Qwen/Qwen2.5-72B-Instruct"
else:
    LLM_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    LLM_API_KEY = OPENAI_API_KEY
    DEFAULT_MODEL = MODEL_ID_ENV or "gpt-4o-mini"

# Parámetros del Agente
AGENT_MAX_STEPS = int(os.getenv("AGENT_MAX_STEPS", "7"))
AGENT_TEMPERATURE = float(os.getenv("AGENT_TEMPERATURE", "0.2"))
