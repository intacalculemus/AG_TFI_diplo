"""
Módulo de Geocodificación Inversa y Jurisdicción Administrativa para Argentina.
Grupo_6_2026 / ISBIA - Lidesia - FCEFyN (UNC)

Permite determinar la Provincia, Departamento/Partido y Municipio/Localidad
donde se encuentra ubicado un polígono, centroide o Bounding Box en la República Argentina.
"""

import urllib.request
import json
from typing import Dict, Any, Optional, Tuple


def get_administrative_location(
    lat: float, 
    lon: float, 
    timeout: float = 3.5
) -> Dict[str, Any]:
    """
    Obtiene la ubicación administrativa oficial en Argentina para un par de coordenadas (lat, lon).
    
    Prioridad de consulta:
    1. API Georef Oficial del Instituto Geográfico Nacional (IGN) / Datos Abiertos Argentina.
    2. Fallback a Nominatim (OpenStreetMap) en caso de contingencia de red o fuera de cobertura Georef.
    
    Retorna un diccionario con:
      - 'provincia': Nombre de la provincia o Estado
      - 'departamento': Nombre del departamento o partido
      - 'municipio': Nombre del municipio o localidad censal (si aplica)
      - 'texto_formateado': Cadena amigable para mostrar en la interfaz
      - 'fuente': Identificador del servicio utilizado
    """
    # 1. Intentar con API Georef IGN Argentina (Rápido, oficial, sin clave)
    try:
        url_georef = f"https://apis.datos.gob.ar/georef/api/ubicacion?lat={lat:.5f}&lon={lon:.5f}"
        req = urllib.request.Request(
            url_georef, 
            headers={"User-Agent": "TFI-Diplo-ISBIA/1.0 (Argentina Geo-Classifier)"}
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            ub = data.get("ubicacion", {})
            prov = ub.get("provincia", {}).get("nombre")
            dpto = ub.get("departamento", {}).get("nombre")
            muni = ub.get("municipio", {}).get("nombre")

            if prov or dpto:
                parts = []
                if dpto:
                    parts.append(f"Dpto. {dpto}")
                if prov:
                    parts.append(f"Pcia. de {prov}")
                if muni:
                    parts.append(f"Mun. {muni}")
                
                texto = ", ".join(parts) if parts else "Ubicación detectada"
                return {
                    "provincia": prov,
                    "departamento": dpto,
                    "municipio": muni,
                    "texto_formateado": texto,
                    "fuente": "IGN Georef (Argentina)",
                    "ok": True
                }
    except Exception:
        pass

    # 2. Fallback a Nominatim OpenStreetMap
    try:
        url_osm = f"https://nominatim.openstreetmap.org/reverse?lat={lat:.5f}&lon={lon:.5f}&format=json"
        req_osm = urllib.request.Request(
            url_osm, 
            headers={"User-Agent": "TFI-Diplo-ISBIA/1.0 (Argentina Geo-Classifier)"}
        )
        with urllib.request.urlopen(req_osm, timeout=timeout) as resp:
            data_osm = json.loads(resp.read().decode("utf-8"))
            addr = data_osm.get("address", {})
            prov = addr.get("state")
            dpto = addr.get("state_district") or addr.get("county")
            muni = addr.get("city") or addr.get("town") or addr.get("village") or addr.get("municipality")

            parts = []
            if dpto:
                parts.append(str(dpto))
            if prov:
                parts.append(f"Pcia. de {prov}")
            if muni:
                parts.append(str(muni))

            texto = ", ".join(parts) if parts else "Ubicación detectada (OSM)"
            return {
                "provincia": prov,
                "departamento": dpto,
                "municipio": muni,
                "texto_formateado": texto,
                "fuente": "OpenStreetMap Nominatim",
                "ok": True
            }
    except Exception:
        pass

    # 3. Fallback genérico si no hay conexión o está fuera de cobertura
    return {
        "provincia": None,
        "departamento": None,
        "municipio": None,
        "texto_formateado": f"Coordenadas: Lat {lat:.4f}, Lon {lon:.4f}",
        "fuente": "Coordenadas directas",
        "ok": False
    }


def get_location_for_bbox(bbox: list) -> Dict[str, Any]:
    """
    Calcula el centroide de un Bounding Box [min_lon, min_lat, max_lon, max_lat]
    y devuelve la información administrativa del punto medio.
    """
    if not bbox or len(bbox) != 4:
        return {
            "provincia": None,
            "departamento": None,
            "municipio": None,
            "texto_formateado": "Área no especificada",
            "fuente": "None",
            "ok": False
        }
    
    min_lon, min_lat, max_lon, max_lat = bbox
    centroid_lat = (min_lat + max_lat) / 2.0
    centroid_lon = (min_lon + max_lon) / 2.0
    return get_administrative_location(centroid_lat, centroid_lon)
