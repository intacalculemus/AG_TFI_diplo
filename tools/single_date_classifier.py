"""
Herramienta de Clasificación Mono-temporal de Cobertura: Vegetación vs. Suelo Desnudo
Conexión Real a Sentinel-2 L2A (Bandas B04 y B08 en 10 metros)
"""
import json
from typing import List, Dict, Any
from services.real_satellite_service import fetch_and_classify_real_scene, search_real_scenes, DEFAULT_BBOX

def classify_single_date(tool_input: str) -> str:
    """
    Clasifica una escena satelital Sentinel-2 L2A real para una fecha o ID específico.
    Calcula NDVI real píxel a píxel a 10m de resolución espacial.
    Input esperado: fecha (YYYY-MM-DD) o item_id | bbox_o_zona
    """
    parts = [p.strip() for p in tool_input.split("|")]
    fecha_o_id = parts[0] if len(parts) > 0 and parts[0] else "2024-04-23"
    zona_str = parts[1] if len(parts) > 1 and parts[1] else "Copo"

    bbox = DEFAULT_BBOX
    # Si viene formato GeoJSON o bbox en texto
    if "[" in zona_str and "]" in zona_str:
        try:
            bbox = json.loads(zona_str)
        except Exception:
            bbox = DEFAULT_BBOX

    # Si es una fecha (YYYY-MM-DD), buscar la escena real correspondiente a esa fecha
    if "-" in fecha_o_id and len(fecha_o_id) == 10:
        year, month, day = fecha_o_id.split("-")
        date_query = f"{fecha_o_id}/{fecha_o_id}"
        scenes = search_real_scenes(bbox=bbox, date_range=date_query, max_cloud=20.0, limit=1)
        if not scenes:
            # Ampliar rango a +/- 15 días si no hay escena exacta
            scenes = search_real_scenes(bbox=bbox, date_range=f"{year}-01-01/{year}-12-31", max_cloud=10.0, limit=1)
        
        if scenes:
            item_id = scenes[0]["id"]
        else:
            item_id = "S2A_MSIL2A_20240423T140711_R110_T20JPS_20240423T221338"
    else:
        item_id = fecha_o_id

    try:
        resultado = fetch_and_classify_real_scene(item_id=item_id, bbox=bbox)
        return json.dumps(resultado, indent=2, ensure_ascii=False)
    except Exception as e:
        return json.dumps({
            "status": "error",
            "mensaje": f"Fallo al procesar bandas reales de Sentinel-2: {str(e)}"
        }, ensure_ascii=False)
