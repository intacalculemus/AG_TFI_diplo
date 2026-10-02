"""
Módulo de Servicios Externos del Agente GeoReAct
"""
from .real_satellite_service import (
    search_real_scenes,
    fetch_and_classify_real_scene,
    classify_with_esa_worldcover,
    DEFAULT_BBOX,
    ESA_WORLDCOVER_CLASSES
)
from .drainage_service import analyze_drainage_and_slope
from .geo_admin_service import get_location_for_bbox, search_location_argentina

__all__ = [
    "search_real_scenes",
    "fetch_and_classify_real_scene",
    "classify_with_esa_worldcover",
    "analyze_drainage_and_slope",
    "get_location_for_bbox",
    "search_location_argentina",
    "DEFAULT_BBOX",
    "ESA_WORLDCOVER_CLASSES"
]

