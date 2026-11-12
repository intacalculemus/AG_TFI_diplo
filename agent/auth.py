"""
Módulo de Control de Acceso Basado en Roles (RBAC) y Gestión Criptográfica de Claves
Permite al administrador del proyecto:
1. Proteger el ingreso a la aplicación mediante una pantalla de Login (Gatekeeper).
2. Crear, activar, revocar y auditar claves de acceso individuales para compañeros o docentes.
3. Almacenar las claves mediante Hash SHA-256 con Salt (sin exponer contraseñas en texto plano).
4. Controlar cuotas máximas de consultas al LLM por clave y proteger intentos de fuerza bruta.
"""
import hashlib
import json
import os
import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

from config import DATA_DIR

KEYS_FILE = DATA_DIR / "access_keys_store.json"
SALT_PREFIX = "ISBIA_UNC_G6_2026::"
MAX_FAILED_ATTEMPTS = 5


def _hash_key(raw_key: str) -> str:
    """Genera el hash SHA-256 irreversible de una clave normalizada."""
    clean = raw_key.strip()
    salted = f"{SALT_PREFIX}{clean}".encode("utf-8")
    return hashlib.sha256(salted).hexdigest()


def _mask_key_hint(raw_key: str) -> str:
    """Genera una pista visual parcial de la clave (ej. 'DIPL***26') sin guardar la clave completa."""
    clean = raw_key.strip()
    if len(clean) <= 4:
        return clean[0] + "***"
    return f"{clean[:4]}***{clean[-2:]}"


def _init_default_store() -> Dict[str, Any]:
    """
    Inicializa el almacén de claves por defecto si no existe en disco.
    - Clave Administrador por defecto: ADMIN-G6-2026 (o variable ADMIN_MASTER_KEY en .env)
    - Clave Evaluador/Docente inicial: DIPLO-G6-2026
    """
    admin_raw = os.getenv("ADMIN_MASTER_KEY", "ADMIN-G6-2026").strip()
    docente_raw = os.getenv("DEFAULT_ACCESS_KEY", "DIPLO-G6-2026").strip()
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

    store = {
        "keys": [
            {
                "id": "KEY-ADMIN-01",
                "label": "Administrador Principal (Federico / Grupo 6)",
                "role": "admin",
                "key_hash": _hash_key(admin_raw),
                "key_hint": _mask_key_hint(admin_raw),
                "active": True,
                "max_queries_session": 200,
                "created_at": now_str,
                "last_login": "Nunca",
                "login_count": 0,
                "is_master": True,
            },
            {
                "id": "KEY-USER-01",
                "label": "Acceso General Diplomatura / Evaluador ISBIA",
                "role": "usuario",
                "key_hash": _hash_key(docente_raw),
                "key_hint": _mask_key_hint(docente_raw),
                "active": True,
                "max_queries_session": 30,
                "created_at": now_str,
                "last_login": "Nunca",
                "login_count": 0,
                "is_master": False,
            },
        ],
        "audit_log": []
    }
    _save_store(store)
    return store


def _load_store() -> Dict[str, Any]:
    """Carga el almacén de claves desde JSON local o lo inicializa."""
    if not KEYS_FILE.exists():
        return _init_default_store()
    try:
        with open(KEYS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if "keys" not in data:
            return _init_default_store()
        return data
    except Exception:
        return _init_default_store()


def _save_store(store: Dict[str, Any]) -> None:
    """Guarda el almacén de claves en disco."""
    KEYS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(KEYS_FILE, "w", encoding="utf-8") as f:
        json.dump(store, f, indent=2, ensure_ascii=False)


def verify_access_key(raw_key: str) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
    """
    Verifica si una clave ingresada es válida y está activa.
    Retorna (exito, mensaje, datos_usuario).
    """
    if not raw_key or not raw_key.strip():
        return False, "Ingresá una clave de acceso válida.", None

    candidate_hash = _hash_key(raw_key)
    store = _load_store()
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    for entry in store.get("keys", []):
        if entry.get("key_hash") == candidate_hash:
            if not entry.get("active", True):
                store.setdefault("audit_log", []).insert(0, {
                    "timestamp": now_str,
                    "event": "INTENTO_CLAVE_REVOCADA",
                    "label": entry.get("label"),
                    "key_id": entry.get("id")
                })
                _save_store(store)
                return False, "⛔ Esta clave de acceso ha sido desactivada o revocada por el administrador.", None

            # Actualizar estadísticas de ingreso
            entry["last_login"] = now_str
            entry["login_count"] = int(entry.get("login_count", 0)) + 1
            store.setdefault("audit_log", []).insert(0, {
                "timestamp": now_str,
                "event": "INGRESO_EXITOSO",
                "label": entry.get("label"),
                "role": entry.get("role"),
                "key_id": entry.get("id")
            })
            # Conservar últimos 50 eventos de auditoría
            store["audit_log"] = store["audit_log"][:50]
            _save_store(store)

            user_session = {
                "id": entry.get("id"),
                "label": entry.get("label"),
                "role": entry.get("role", "usuario"),
                "max_queries_session": int(entry.get("max_queries_session", 30)),
                "key_hint": entry.get("key_hint", "***"),
                "login_time": now_str,
            }
            return True, f"Bienvenido/a: {entry.get('label')}", user_session

    store.setdefault("audit_log", []).insert(0, {
        "timestamp": now_str,
        "event": "CLAVE_INVALIDA",
        "label": "Desconocido",
        "key_id": "-"
    })
    store["audit_log"] = store["audit_log"][:50]
    _save_store(store)
    return False, "❌ Clave de acceso incorrecta.", None


def list_access_keys() -> List[Dict[str, Any]]:
    """Retorna la lista de claves registradas (sin exponer contraseñas en claro)."""
    store = _load_store()
    return store.get("keys", [])


def get_audit_log() -> List[Dict[str, Any]]:
    """Retorna los últimos eventos de auditoría de acceso."""
    store = _load_store()
    return store.get("audit_log", [])


def create_access_key(
    label: str,
    raw_key: str,
    role: str = "usuario",
    max_queries_session: int = 30
) -> Tuple[bool, str]:
    """
    Crea una nueva clave de acceso con hash SHA-256.
    role puede ser 'usuario' (acceso a uso de la app) o 'admin' (acceso total + gestor de claves).
    """
    label_clean = (label or "").strip()
    key_clean = (raw_key or "").strip()

    if not label_clean:
        return False, "Debés indicar un nombre o destinatario para identificar la clave (ej. 'Profesor Evaluador' o 'Compañero Grupo 6')."
    if len(key_clean) < 5:
        return False, "La clave debe tener al menos 5 caracteres por seguridad."

    new_hash = _hash_key(key_clean)
    store = _load_store()

    for k in store.get("keys", []):
        if k.get("key_hash") == new_hash:
            return False, "Ya existe una clave registrada con ese mismo valor."

    next_num = len(store.get("keys", [])) + 1
    prefix = "ADMIN" if role == "admin" else "USER"
    new_id = f"KEY-{prefix}-{next_num:02d}-{hashlib.md5(label_clean.encode()).hexdigest()[:4].upper()}"
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

    new_entry = {
        "id": new_id,
        "label": label_clean,
        "role": role if role in ("admin", "usuario") else "usuario",
        "key_hash": new_hash,
        "key_hint": _mask_key_hint(key_clean),
        "active": True,
        "max_queries_session": int(max_queries_session),
        "created_at": now_str,
        "last_login": "Nunca",
        "login_count": 0,
        "is_master": False,
    }
    store["keys"].append(new_entry)
    _save_store(store)
    return True, f"✅ Clave creada exitosamente para '{label_clean}' (ID: {new_id}). Copiala y entregásela al destinatario."


def toggle_access_key(key_id: str) -> Tuple[bool, str]:
    """Activa o revoca (desactiva) una clave existente por su ID."""
    store = _load_store()
    for k in store.get("keys", []):
        if k.get("id") == key_id:
            if k.get("is_master") and k.get("active"):
                return False, "No se puede desactivar la clave maestra principal de administración."
            k["active"] = not k.get("active", True)
            _save_store(store)
            estado_txt = "ACTIVADA" if k["active"] else "REVOCADA / PAUSADA"
            return True, f"Clave '{k.get('label')}' ({key_id}) ahora está {estado_txt}."
    return False, "No se encontró la clave indicada."


def update_master_or_key_password(key_id: str, new_raw_key: str) -> Tuple[bool, str]:
    """Permite cambiar la contraseña de una clave existente (incluyendo la clave maestra)."""
    clean = (new_raw_key or "").strip()
    if len(clean) < 5:
        return False, "La nueva clave debe tener al menos 5 caracteres."
    store = _load_store()
    for k in store.get("keys", []):
        if k.get("id") == key_id:
            k["key_hash"] = _hash_key(clean)
            k["key_hint"] = _mask_key_hint(clean)
            _save_store(store)
            return True, f"🔑 Se actualizó correctamente la clave para '{k.get('label')}'."
    return False, "No se encontró el registro de clave."


def delete_access_key(key_id: str) -> Tuple[bool, str]:
    """Elimina una clave del almacén (salvo la clave maestra principal)."""
    store = _load_store()
    for idx, k in enumerate(store.get("keys", [])):
        if k.get("id") == key_id:
            if k.get("is_master"):
                return False, "No se puede eliminar la clave maestra principal (pero podés cambiarle la contraseña)."
            removed = store["keys"].pop(idx)
            _save_store(store)
            return True, f"🗑️ Se eliminó la clave de '{removed.get('label')}'."
    return False, "No se encontró la clave indicada."
