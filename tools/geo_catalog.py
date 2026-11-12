"""
Herramienta de Catálogo y Metadatos de Escenas Satelitales Reales (Sentinel-2 L2A y Modelos LULC vía STAC)
"""
import json
import datetime
from typing import Dict, Any, List
from services.real_satellite_service import search_real_scenes, discover_available_sources, DEFAULT_BBOX

def get_available_dates_for_roi(bbox: List[float] = None, date_range: str = None) -> List[Dict[str, Any]]:
    """
    Consulta en tiempo real la API STAC de Microsoft Planetary Computer
    para devolver las escenas Sentinel-2 L2A con <10% nubes usando fechas dinámicas.
    """
    target_bbox = bbox or DEFAULT_BBOX
    if not date_range:
        today = datetime.date.today()
        start_dt = (today - datetime.timedelta(days=365)).strftime("%Y-%m-%d")
        end_dt = today.strftime("%Y-%m-%d")
        date_range = f"{start_dt}/{end_dt}"
    scenes = search_real_scenes(bbox=target_bbox, date_range=date_range, max_cloud=10.0, limit=12)
    return scenes

def search_satellite_catalog(tool_input: str) -> str:
    """
    Busca escenas satelitales reales y años disponibles en STAC para una región geográfica o coordenadas.
    Input esperado: zona / departamento / bbox | fecha_inicio | fecha_fin
    """
    parts = [p.strip() for p in tool_input.split("|")]
    zona = parts[0] if len(parts) > 0 and parts[0] else "Copo"
    date_range = None
    if len(parts) >= 3 and parts[1] and parts[2]:
        date_range = f"{parts[1]}/{parts[2]}"
    elif len(parts) == 2 and "/" in parts[1]:
        date_range = parts[1]

    bbox = DEFAULT_BBOX
    if "[" in zona and "]" in zona:
        try:
            bbox = json.loads(zona)
        except Exception:
            bbox = DEFAULT_BBOX

    scenes = get_available_dates_for_roi(bbox, date_range=date_range)
    sources_meta = discover_available_sources(bbox)

    return json.dumps({
        "status": "success",
        "proveedor": "Microsoft Planetary Computer STAC API",
        "region_consultada": zona,
        "fuentes_sincronizadas": {
            "esa_worldcover_years": sources_meta["esa_worldcover"]["years"],
            "io_lulc_annual_years": sources_meta["io_lulc"]["years"],
            "sentinel2_years": sources_meta["sentinel2"]["years"],
            "sentinel2_ultima_escena": sources_meta["sentinel2"]["latest_scene_date"],
        },
        "total_escenas_reales": len(scenes),
        "escenas_disponibles": scenes,
        "resumen": (
            f"Se consultó el catálogo STAC en tiempo real: {len(scenes)} escenas Sentinel-2 L2A de 10m con nubosidad <10% "
            f"(última disponible: {sources_meta['sentinel2']['latest_scene_date']}), "
            f"ESA WorldCover años {sources_meta['esa_worldcover']['years']} y Esri 10m LULC años {sources_meta['io_lulc']['years']}."
        )
    }, indent=2, ensure_ascii=False)
