"""
Herramienta de Análisis Hidrológico, Red de Drenaje Superficial y Pendientes
"""
import json
from services.drainage_service import analyze_drainage_and_slope, DEFAULT_BBOX

def analyze_drainage_network(tool_input: str) -> str:
    """
    Calcula la red de líneas de drenaje hídrico superficial, pendientes (%), orientación y dirección de flujo,
    y evaluación de riesgo de erosión hídrica a partir de Copernicus DEM 30m.
    Input esperado: bbox en formato JSON o coordenadas [min_lon, min_lat, max_lon, max_lat]
    Ejemplo: Action: red_drenaje_hidrico | [-62.8, -30.7, -62.5, -30.5]
    """
    tool_input = tool_input.strip()
    bbox = DEFAULT_BBOX

    if "[" in tool_input and "]" in tool_input:
        try:
            # Extraer la subcadena que contiene la lista JSON
            start = tool_input.index("[")
            end = tool_input.rindex("]") + 1
            bbox = json.loads(tool_input[start:end])
        except Exception:
            bbox = DEFAULT_BBOX

    try:
        resultado = analyze_drainage_and_slope(bbox=bbox)
        return json.dumps(resultado, indent=2, ensure_ascii=False)
    except Exception as e:
        return json.dumps({
            "status": "error",
            "mensaje": f"Error al calcular la red de drenaje superficial: {str(e)}"
        }, ensure_ascii=False)
