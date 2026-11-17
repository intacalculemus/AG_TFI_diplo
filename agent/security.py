"""
Módulo de Ciberseguridad (Guardrails) y Sandbox de Aplicación para el Agente GeoReAct
Mitiga riesgos del estándar OWASP Top 10 for LLM Applications:
- LLM01: Prompt Injection / Jailbreak
- LLM02: Insecure Output Handling & Secret Leakage
- LLM04: Model / Resource Denial of Service (Sandbox Spatial Quota)
- LLM07: Insecure Tool / Plugin Input Validation (Path Traversal & Coordenadas)
"""
import re
import json
from typing import Tuple, Optional, List, Dict, Any

# Límite máximo de superficie en el Sandbox para procesamiento satelital en vivo (hectáreas)
# Evita que una consulta maliciosa o alucinación descargue un continente entero y agote la RAM del contenedor
SANDBOX_MAX_AREA_HA = 100000.0  # 100.000 ha (10.000.000 píxeles a 10m)
SANDBOX_MAX_USER_CHARS = 4000
SANDBOX_MAX_QUERY_CHARS = 32000

# Patrones de ataques de Prompt Injection / Jailbreak / Exfiltración de Prompts o Secretos
PROMPT_INJECTION_PATTERNS = [
    r"ignora\s+(todas\s+)?las\s+instrucciones",
    r"ignor[aá]\s+tu\s+rol",
    r"ignore\s+(all\s+)?(previous|prior)\s+instructions",
    r"disregard\s+(all\s+)?(previous|prior)\s+instructions",
    r"system\s*prompt",
    r"revel[aá]\s+(tu|el)\s+prompt",
    r"mostr[aá](me)?\s+(tus|las)\s+(claves|api\s*keys|tokens|secretos|credenciales)",
    r"print\s+environ",
    r"os\.environ",
    r"st\.secrets",
    r"olvida\s+todo\s+lo\s+anterior",
    r"actu[aá]\s+como\s+un\s+hacker",
    r"dan\s+mode",
    r"jailbreak",
]

# Patrones de Path Traversal o comandos peligrosos en entradas de herramientas
PATH_TRAVERSAL_PATTERNS = [
    r"\.\./",
    r"\.\.\\",
    r"/etc/passwd",
    r"c:\\windows",
    r"cmd\.exe",
    r"/bin/sh",
    r"/bin/bash",
]

# Patrones de claves de API para enmascaramiento automático en salidas (Output Guardrail)
SECRET_PATTERNS = [
    (re.compile(r"gsk_[A-Za-z0-9]{15,}"), "gsk_[REDACTED_SECRET]"),
    (re.compile(r"hf_[A-Za-z0-9]{15,}"), "hf_[REDACTED_SECRET]"),
    (re.compile(r"sk-[A-Za-z0-9\-_]{15,}"), "sk-[REDACTED_SECRET]"),
]


def validate_user_input(query: str) -> Tuple[bool, str]:
    """
    Input Guardrail: Analiza la consulta del usuario antes de ingresarla al bucle ReAct.
    Separa el texto escrito por el usuario de los metadatos internos adjuntos por la app.
    Retorna (es_seguro, mensaje_o_motivo_bloqueo).
    """
    if not query or not query.strip():
        return False, "La consulta está vacía."

    if len(query) > SANDBOX_MAX_QUERY_CHARS:
        return (
            False,
            f"🛡️ **Bloqueo de Seguridad (Input Guardrail):** La consulta excede el límite máximo permitido de caracteres ({SANDBOX_MAX_QUERY_CHARS})."
        )

    # Extraer únicamente la parte escrita por el usuario (antes de los corchetes de contexto de la app)
    user_text_only = query.split("[BBox activo:")[0].strip()
    user_text_lower = user_text_only.lower()

    if len(user_text_only) > SANDBOX_MAX_USER_CHARS:
        return (
            False,
            f"🛡️ **Bloqueo de Seguridad (Input Guardrail):** El texto ingresado excede el límite máximo permitido de caracteres ({SANDBOX_MAX_USER_CHARS})."
        )

    # 1. Detectar intentos de inyección de delimitadores falsos del protocolo ReAct
    if "observation:" in user_text_lower or "action:" in user_text_lower:
        return (
            False,
            "🛡️ **Bloqueo de Ciberseguridad (OWASP LLM01 - Prompt Injection):** "
            "Se detectó un intento de inyectar delimitadores internos del protocolo ReAct (`Action:` / `Observation:`) en la entrada del usuario."
        )

    # 2. Detectar patrones de Jailbreak / Exfiltración de System Prompt o Credenciales
    for pattern in PROMPT_INJECTION_PATTERNS:
        if re.search(pattern, user_text_lower, re.IGNORECASE):
            return (
                False,
                "🛡️ **Bloqueo de Ciberseguridad (OWASP LLM01 - Prompt Injection / Exfiltración):** "
                "La solicitud contiene instrucciones orientadas a vulnerar las directivas del sistema o exfiltrar credenciales/prompts internos. "
                "Este asistente opera exclusivamente para consultas técnicas agroambientales, geoespaciales y de arquitectura del proyecto."
            )

    return True, query


def _estimate_bbox_area_ha(bbox: List[float]) -> float:
    """Calcula una estimación rápida de la superficie en hectáreas de un BBox [min_lon, min_lat, max_lon, max_lat]."""
    import math
    min_lon, min_lat, max_lon, max_lat = bbox
    lat_mean_rad = math.radians((min_lat + max_lat) / 2.0)
    width_km = abs(max_lon - min_lon) * 111.32 * math.cos(lat_mean_rad)
    height_km = abs(max_lat - min_lat) * 110.57
    area_km2 = width_km * height_km
    return area_km2 * 100.0  # 1 km2 = 100 ha


def validate_tool_execution(
    tool_name: str,
    tool_input: str,
    max_area_ha: float = SANDBOX_MAX_AREA_HA
) -> Tuple[bool, str]:
    """
    Sandbox & Tool Guardrail (OWASP LLM04 & LLM07):
    Valida los parámetros que el LLM envía a una herramienta antes de su ejecución.
    Verifica:
    1. Ausencia de Path Traversal o inyección de rutas.
    2. Validez geométrica de coordenadas si incluye un Bounding Box.
    3. Cumplimiento de la cuota máxima de superficie (hectáreas) en el Sandbox.
    """
    raw_input = str(tool_input or "").strip()

    # 1. Prevención de Path Traversal
    for pat in PATH_TRAVERSAL_PATTERNS:
        if re.search(pat, raw_input, re.IGNORECASE):
            return (
                False,
                json.dumps({
                    "status": "sandbox_blocked",
                    "tipo_bloqueo": "Filesystem Jail / Path Traversal (OWASP LLM07)",
                    "mensaje": f"El Sandbox bloqueó la ejecución de '{tool_name}': se detectó una ruta de archivo no autorizada fuera del directorio aislado."
                }, ensure_ascii=False)
            )

    # 2. Si el parámetro incluye una lista de coordenadas [min_lon, min_lat, max_lon, max_lat], validarla
    if "[" in raw_input and "]" in raw_input:
        try:
            start = raw_input.index("[")
            end = raw_input.rindex("]") + 1
            candidate = json.loads(raw_input[start:end])
            if isinstance(candidate, list) and len(candidate) == 4 and all(isinstance(x, (int, float)) for x in candidate):
                min_lon, min_lat, max_lon, max_lat = [float(x) for x in candidate]

                # Validar rangos geográficos terrestres
                if not (-180.0 <= min_lon <= 180.0 and -180.0 <= max_lon <= 180.0 and -90.0 <= min_lat <= 90.0 and -90.0 <= max_lat <= 90.0):
                    return (
                        False,
                        json.dumps({
                            "status": "sandbox_blocked",
                            "tipo_bloqueo": "Coordenadas Inválidas",
                            "mensaje": f"El Sandbox bloqueó '{tool_name}': las coordenadas [{min_lon}, {min_lat}, {max_lon}, {max_lat}] están fuera del rango terrestre EPSG:4326."
                        }, ensure_ascii=False)
                    )

                if min_lon >= max_lon or min_lat >= max_lat:
                    return (
                        False,
                        json.dumps({
                            "status": "sandbox_blocked",
                            "tipo_bloqueo": "Geometría BBox Invertida",
                            "mensaje": f"El Sandbox bloqueó '{tool_name}': min_lon/min_lat deben ser menores que max_lon/max_lat."
                        }, ensure_ascii=False)
                    )

                # Validar cuota máxima de área para proteger la memoria RAM del contenedor
                area_ha = _estimate_bbox_area_ha([min_lon, min_lat, max_lon, max_lat])
                if area_ha > max_area_ha:
                    return (
                        False,
                        json.dumps({
                            "status": "sandbox_blocked",
                            "tipo_bloqueo": "Cuota de Memoria del Sandbox Excedida (OWASP LLM04)",
                            "area_solicitada_ha": round(area_ha, 1),
                            "cuota_maxima_sandbox_ha": max_area_ha,
                            "mensaje": (
                                f"El Sandbox detuvo preventivamente '{tool_name}': el área solicitada ({area_ha:,.1f} ha) "
                                f"supera la cuota máxima segura del contenedor ({max_area_ha:,.0f} ha) para proteger la memoria RAM."
                            )
                        }, ensure_ascii=False)
                    )
        except Exception:
            pass

    return True, raw_input


def sanitize_output(text: str) -> str:
    """
    Output Guardrail (OWASP LLM02):
    Enmascara cualquier token o credencial sensible que pudiera haberse filtrado en un texto o mensaje de error.
    """
    if not text:
        return ""
    sanitized = str(text)
    for regex, replacement in SECRET_PATTERNS:
        sanitized = regex.sub(replacement, sanitized)
    return sanitized


def get_security_and_sandbox_status() -> Dict[str, Any]:
    """Retorna el resumen de configuración activa de Ciberseguridad y Sandbox para auditoría."""
    return {
        "input_guardrail": "Activo (Filtro OWASP LLM01 Prompt Injection & Delimitadores ReAct)",
        "output_guardrail": "Activo (Enmascaramiento de Secretos OWASP LLM02: gsk_*, hf_*, sk-*)",
        "tool_sandbox": "Activo (Validación de Coordenadas EPSG:4326, Timeout y Filesystem Jail en /outputs)",
        "sandbox_max_area_ha": SANDBOX_MAX_AREA_HA,
        "patrones_injection_monitoreados": len(PROMPT_INJECTION_PATTERNS),
    }
