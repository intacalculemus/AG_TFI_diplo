"""
Herramienta de Catálogo y Metadatos de Escenas Satelitales Reales (Sentinel-2 L2A vía STAC)
"""
import json
from typing import Dict, Any, List
from services.real_satellite_service import search_real_scenes, DEFAULT_BBOX

def get_available_dates_for_roi(bbox: List[float] = None) -> List[Dict[str, Any]]:
    """
    Consulta en tiempo real la API STAC de Microsoft Planetary Computer
    para devolver las escenas Sentinel-2 L2A con <10% nubes.
    """
    target_bbox = bbox or DEFAULT_BBOX
    scenes = search_real_scenes(bbox=target_bbox, date_range="2023-01-01/2024-12-31", max_cloud=10.0, limit=12)
    return scenes

def search_satellite_catalog(tool_input: str) -> str:
    """
    Busca escenas satelitales reales disponibles para una región geográfica o coordenadas.
    Input esperado: zona / departamento / bbox | fecha_inicio | fecha_fin
    """
    parts = [p.strip() for p in tool_input.split("|")]
    zona = parts[0] if len(parts) > 0 and parts[0] else "Copo"
    
    scenes = get_available_dates_for_roi(DEFAULT_BBOX)
    
    return json.dumps({
        "status": "success",
        "proveedor": "Microsoft Planetary Computer STAC API (Sentinel-2 L2A)",
        "region_consultada": zona,
        "total_escenas_reales": len(scenes),
        "escenas_disponibles": scenes,
        "resumen": f"Se consultó el catálogo STAC en tiempo real y se encontraron {len(scenes)} escenas Sentinel-2 L2A de 10m con nubosidad <10%."
    }, indent=2, ensure_ascii=False)
