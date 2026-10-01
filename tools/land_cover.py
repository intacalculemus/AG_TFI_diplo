"""
Herramienta de Segmentación y Clasificación de Coberturas con Modelo de IA (ESA WorldCover 10m)
"""
import json
from services.real_satellite_service import classify_with_esa_worldcover, DEFAULT_BBOX

def classify_land_cover_ai(tool_input: str) -> str:
    """
    Ejecuta la clasificación de coberturas del suelo utilizando el modelo de Deep Learning ESA WorldCover 10m.
    Identifica 8+ clases: Bosque Nativo, Cultivos Agrícolas, Matorral, Pastizales, Suelo Desnudo, Urbano, Agua, Humedales.
    Input esperado: año (2020 o 2021) | bbox_o_zona
    """
    parts = [p.strip() for p in tool_input.split("|")]
    year = parts[0] if len(parts) > 0 and parts[0] in ["2020", "2021"] else "2021"
    zona_str = parts[1] if len(parts) > 1 else ""

    bbox = DEFAULT_BBOX
    if "[" in zona_str and "]" in zona_str:
        try:
            bbox = json.loads(zona_str)
        except Exception:
            bbox = DEFAULT_BBOX

    try:
        resultado = classify_with_esa_worldcover(bbox=bbox, year=year)
        return json.dumps(resultado, indent=2, ensure_ascii=False)
    except Exception as e:
        return json.dumps({
            "status": "error",
            "mensaje": f"Error al ejecutar clasificación ESA WorldCover: {str(e)}"
        }, ensure_ascii=False)
