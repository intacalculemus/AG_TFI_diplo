"""
Módulo de Geocodificación Inversa y Jurisdicción Administrativa para Argentina.
Grupo_6_2026 / ISBIA - Lidesia - FCEFyN (UNC)

Permite:
1. Determinar la Provincia, Departamento/Partido y Municipio/Localidad para cualquier punto o BBox.
2. Búsqueda toponímica y geoposicionamiento rápido por Localidad, Municipio, Departamento o Paraje (IGN Georef + Nominatim).
"""

import urllib.request
import urllib.parse
import json
from typing import Dict, Any, Optional, Tuple


def search_location_argentina(query: str, timeout: float = 4.0) -> Dict[str, Any]:
    """
    Busca una localidad, departamento, municipio o paraje en Argentina y devuelve sus coordenadas
    geográficas para posicionar el visor satelital.
    
    Admite formatos como:
      - "Pergamino, Buenos Aires"
      - "Bandera, Santiago del Estero"
      - "Río Cuarto"
      - "Colonia Caroya"
      - "Balcarce"
      - "Mar Chiquita, Córdoba"
    
    Prioridad:
    1. API Georef Oficial del Instituto Geográfico Nacional (IGN).
       Consulta secuencialmente: localidades, municipios, departamentos, asentamientos y provincias.
    2. Fallback a Nominatim OpenStreetMap si no se localiza en Georef.
    """
    query = query.strip()
    if not query:
        return {"ok": False, "error": "Consulta de búsqueda vacía."}

    nombre = query
    provincia = None
    if "," in query:
        parts = [p.strip() for p in query.split(",", 1)]
        nombre = parts[0]
        provincia = parts[1]

    # 1. Intentar con endpoints de IGN Georef
    endpoints_georef = [
        ("localidades", 12),
        ("municipios", 12),
        ("departamentos", 10),
        ("asentamientos", 13),
        ("provincias", 7)
    ]

    for ep, zoom in endpoints_georef:
        params = {"nombre": nombre, "max": 3}
        if provincia and ep != "provincias":
            params["provincia"] = provincia

        url = f"https://apis.datos.gob.ar/georef/api/{ep}?" + urllib.parse.urlencode(params)
        try:
            req = urllib.request.Request(
                url, 
                headers={"User-Agent": "TFI-Diplo-ISBIA/1.0 (Argentina Geo-Classifier)"}
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                items = data.get(ep, [])
                if items:
                    item = items[0]
                    centroide = item.get("centroide", {})
                    lat = centroide.get("lat")
                    lon = centroide.get("lon")

                    prov_nom = (
                        item.get("provincia", {}).get("nombre") 
                        if isinstance(item.get("provincia"), dict) 
                        else (item.get("nombre") if ep == "provincias" else None)
                    )
                    dpto_nom = (
                        item.get("departamento", {}).get("nombre") 
                        if isinstance(item.get("departamento"), dict) 
                        else (item.get("nombre") if ep == "departamentos" else None)
                    )
                    muni_nom = (
                        item.get("municipio", {}).get("nombre") 
                        if isinstance(item.get("municipio"), dict) 
                        else (item.get("nombre") if ep == "municipios" else None)
                    )

                    texto_parts = [item.get("nombre", nombre)]
                    if dpto_nom and dpto_nom != item.get("nombre"):
                        texto_parts.append(f"Dpto. {dpto_nom}")
                    if prov_nom:
                        texto_parts.append(f"Pcia. de {prov_nom}")

                    if lat is not None and lon is not None:
                        return {
                            "ok": True,
                            "nombre": item.get("nombre"),
                            "provincia": prov_nom,
                            "departamento": dpto_nom,
                            "municipio": muni_nom,
                            "lat": float(lat),
                            "lon": float(lon),
                            "zoom_sugerido": zoom,
                            "texto_formateado": ", ".join(texto_parts),
                            "fuente": f"IGN Georef ({ep.capitalize()})"
                        }
        except Exception:
            pass

    # 2. Fallback a Nominatim OpenStreetMap
    try:
        osm_query = f"{query}, Argentina" if "argentina" not in query.lower() else query
        url_osm = "https://nominatim.openstreetmap.org/search?" + urllib.parse.urlencode({
            "q": osm_query, 
            "format": "json", 
            "limit": 1
        })
        req_osm = urllib.request.Request(
            url_osm, 
            headers={"User-Agent": "TFI-Diplo-ISBIA/1.0 (Argentina Geo-Classifier)"}
        )
        with urllib.request.urlopen(req_osm, timeout=timeout) as resp:
            data_osm = json.loads(resp.read().decode("utf-8"))
            if data_osm:
                item = data_osm[0]
                lat = float(item["lat"])
                lon = float(item["lon"])
                raw_bbox = item.get("boundingbox")
                f_bounds = None
                if raw_bbox and len(raw_bbox) == 4:
                    # Nominatim boundingbox: [min_lat, max_lat, min_lon, max_lon]
                    f_bounds = [[float(raw_bbox[0]), float(raw_bbox[2])], [float(raw_bbox[1]), float(raw_bbox[3])]]

                return {
                    "ok": True,
                    "nombre": item.get("display_name", query).split(",")[0],
                    "provincia": None,
                    "departamento": None,
                    "municipio": None,
                    "lat": lat,
                    "lon": lon,
                    "zoom_sugerido": 12,
                    "folium_bounds": f_bounds,
                    "texto_formateado": item.get("display_name"),
                    "fuente": "OpenStreetMap Nominatim"
                }
    except Exception:
        pass

    return {
        "ok": False,
        "error": f"No se pudo localizar \"{query}\" en el IGN ni en OpenStreetMap."
    }


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
