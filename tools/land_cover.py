"""
Herramienta de Segmentación y Clasificación de Coberturas con Modelos de IA (ESA WorldCover 10m & Esri/IO Annual LULC 10m)
"""
import json
import re
from services.real_satellite_service import classify_with_esa_worldcover, DEFAULT_BBOX

def classify_land_cover_ai(tool_input: str) -> str:
    """
    Ejecuta la clasificación de coberturas del suelo utilizando modelos de Deep Learning a 10m:
    - ESA WorldCover 10m (esa-worldcover)
    - Esri / Impact Observatory 10m Annual Land Cover (io-lulc-annual-v02, serie anual 2017-2023+)
    Input esperado: año (ej. 2017 a 2024) | bbox_o_zona | coleccion_opcional (esa-worldcover o io-lulc-annual-v02)
    """
    parts = [p.strip() for p in tool_input.split("|")]
    raw_first = parts[0] if len(parts) > 0 else "2021"
    year_match = re.search(r"(20\d{2})", raw_first)
    year = year_match.group(1) if year_match else "2021"
    zona_str = parts[1] if len(parts) > 1 else ""
    collection_id = parts[2] if len(parts) > 2 else "auto"

    if "io-lulc" in raw_first.lower() or "esri" in raw_first.lower():
        collection_id = "io-lulc-annual-v02"
    elif "worldcover" in raw_first.lower() or "esa" in raw_first.lower():
        collection_id = "esa-worldcover"

    bbox = DEFAULT_BBOX
    for p in parts:
        if "[" in p and "]" in p:
            try:
                bbox = json.loads(p)
                break
            except Exception:
                bbox = DEFAULT_BBOX

    try:
        resultado = classify_with_esa_worldcover(bbox=bbox, year=year, collection_id=collection_id)
        return json.dumps(resultado, indent=2, ensure_ascii=False)
    except Exception as e:
        return json.dumps({
            "status": "error",
            "mensaje": f"Error al ejecutar clasificación con Modelo IA: {str(e)}"
        }, ensure_ascii=False)
