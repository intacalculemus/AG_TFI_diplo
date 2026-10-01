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

__all__ = [
    "search_real_scenes",
    "fetch_and_classify_real_scene",
    "classify_with_esa_worldcover",
    "DEFAULT_BBOX",
    "ESA_WORLDCOVER_CLASSES"
]
