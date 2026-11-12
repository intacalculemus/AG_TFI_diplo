"""
Servicio de Conexión Real a Proveedor Satelital STAC (Microsoft Planetary Computer)
Soporta:
1. Modelo de IA Global: ESA WorldCover (10m de resolución espacial, 8+ clases de cobertura)
2. Procesamiento de Bandas B04/B08 Sentinel-2 L2A en tiempo real
"""
import os
from typing import List, Dict, Any, Optional, Tuple
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap
import matplotlib.patches as mpatches
from PIL import Image

import math
import pystac_client
import planetary_computer
import rasterio
from rasterio.windows import from_bounds, bounds as window_bounds_fn
from rasterio.warp import transform_bounds
from config import OUTPUTS_DIR
from services.geo_admin_service import get_location_for_bbox

STAC_API_URL = "https://planetarycomputer.microsoft.com/api/stac/v1"
# Coordenadas por defecto: Laguna Mar Chiquita (Mar de Ansenuza), Córdoba (~6.4 Mpx / 64.000 ha)
DEFAULT_BBOX = [-62.80, -30.70, -62.50, -30.50]

# Límites de seguridad computacional para procesamiento en tiempo real (10m de resolución)
OPTIMAL_PIXELS_LIMIT = 4_000_000   # ~40.000 ha (procesamiento rápido en 2-8s)
MAX_ALLOWED_PIXELS = 10_000_000    # ~100.000 ha (límite máximo seguro para evitar OOM/congelamiento)

def estimate_bbox_dimensions(bbox: List[float], res_m: float = 10.0) -> Dict[str, Any]:
    """
    Calcula de forma exacta las dimensiones geográficas, métricas, píxeles y superficie
    de un Bounding Box [min_lon, min_lat, max_lon, max_lat] a una resolución dada en metros.
    """
    target_bbox = bbox or DEFAULT_BBOX
    minx, miny, maxx, maxy = target_bbox
    d_lat = max(0.0, maxy - miny)
    d_lon = max(0.0, maxx - minx)
    mid_lat = (miny + maxy) / 2.0
    
    # 1 grado de latitud ~ 111.320 metros
    h_m = d_lat * 111320.0
    # 1 grado de longitud varía con el coseno de la latitud
    w_m = d_lon * 111320.0 * math.cos(math.radians(mid_lat))
    
    w_px = max(1, int(round(w_m / res_m)))
    h_px = max(1, int(round(h_m / res_m)))
    total_px = w_px * h_px
    total_ha = round(total_px * (res_m * res_m / 10000.0), 1)
    total_km2 = round(total_ha / 100.0, 2)
    
    # Evaluación semafórica de carga computacional
    if total_px <= OPTIMAL_PIXELS_LIMIT:
        nivel = "optimo"
        bloqueado = False
        mensaje = "✅ Selección óptima para procesamiento rápido en tiempo real."
    elif total_px <= MAX_ALLOWED_PIXELS:
        nivel = "advertencia"
        bloqueado = False
        mensaje = f"⚠️ Área extensa seleccionada ({total_px:,} px / {total_ha:,.1f} ha). El procesamiento puede demorar unos segundos adicionales."
    else:
        nivel = "exceso"
        bloqueado = True
        mensaje = (
            f"🛑 Área demasiado grande ({total_px:,} píxeles / {total_ha:,.1f} ha). "
            f"El límite máximo seguro para evitar saturar memoria es de {MAX_ALLOWED_PIXELS:,} píxeles (~100.000 ha). "
            f"Por favor delimitá un rectángulo más acotado en el visor satelital."
        )

    return {
        "ancho_m": round(w_m, 1),
        "alto_m": round(h_m, 1),
        "pixeles_ancho": w_px,
        "pixeles_alto": h_px,
        "total_pixeles": total_px,
        "superficie_ha": total_ha,
        "superficie_km2": total_km2,
        "resolucion_m": res_m,
        "nivel": nivel,
        "bloqueado": bloqueado,
        "mensaje": mensaje,
        "limite_max_px": MAX_ALLOWED_PIXELS
    }

# Diccionario oficial de clases de ESA WorldCover 10m
ESA_WORLDCOVER_CLASSES = {
    10: {"name": "Bosque Nativo / Árboles (Tree cover)", "color": "#006400", "rgb": [0, 100, 0]},
    20: {"name": "Matorral / Arbustal (Shrubland)", "color": "#ffbb22", "rgb": [255, 187, 34]},
    30: {"name": "Pastizal / Sabana (Grassland)", "color": "#ffff4c", "rgb": [255, 255, 76]},
    40: {"name": "Cultivos Agrícolas (Cropland)", "color": "#f096ff", "rgb": [240, 150, 255]},
    50: {"name": "Área Urbana / Construida (Built-up)", "color": "#fa0000", "rgb": [250, 0, 0]},
    60: {"name": "Suelo Desnudo / Barbecho (Bare soil)", "color": "#b4b4b4", "rgb": [180, 180, 180]},
    80: {"name": "Cuerpos de Agua (Water bodies)", "color": "#0064c8", "rgb": [0, 100, 200]},
    90: {"name": "Humedales Herbáceos (Wetlands)", "color": "#0096a0", "rgb": [0, 150, 160]},
    95: {"name": "Manglares (Mangroves)", "color": "#00cf75", "rgb": [0, 207, 117]},
    100: {"name": "Musgos y Líquenes (Moss/lichen)", "color": "#fae6a0", "rgb": [250, 230, 160]}
}

# Diccionario oficial de clases de Esri / Impact Observatory 10m Annual LULC (io-lulc-annual-v02)
IO_LULC_CLASSES = {
    1: {"name": "Cuerpos de Agua (Water)", "color": "#1a5bab", "rgb": [26, 91, 171]},
    2: {"name": "Bosque Nativo / Árboles (Trees)", "color": "#358221", "rgb": [53, 130, 33]},
    4: {"name": "Humedales / Veg. Inundable (Flooded veg.)", "color": "#87d19e", "rgb": [135, 209, 158]},
    5: {"name": "Cultivos Agrícolas (Crops)", "color": "#ffdb5c", "rgb": [255, 219, 92]},
    7: {"name": "Área Urbana / Construida (Built area)", "color": "#ed022a", "rgb": [237, 2, 42]},
    8: {"name": "Suelo Desnudo / Barbecho (Bare ground)", "color": "#b4afa8", "rgb": [180, 175, 168]},
    9: {"name": "Nieve y Hielo (Snow/ice)", "color": "#f2faff", "rgb": [242, 250, 255]},
    10: {"name": "Nubes (Clouds)", "color": "#c8c8c8", "rgb": [200, 200, 200]},
    11: {"name": "Pastizal / Monte / Arbustal (Rangeland)", "color": "#dace81", "rgb": [218, 206, 129]}
}

def get_stac_catalog():
    """Inicializa y firma el cliente STAC de Planetary Computer."""
    return pystac_client.Client.open(
        STAC_API_URL,
        modifier=planetary_computer.sign_inplace
    )

def discover_available_sources(bbox: List[float] = None) -> Dict[str, Any]:
    """
    Consulta en vivo el catálogo STAC de Microsoft Planetary Computer para descubrir
    dinámicamente qué colecciones, años y rangos de fechas están disponibles para el BBox.
    """
    import datetime
    import re

    target_bbox = bbox or DEFAULT_BBOX
    now = datetime.datetime.now()
    current_year = now.year

    # Valores por defecto seguros en caso de caída temporal de red
    wc_years: List[str] = []
    io_years: List[str] = []
    s2_latest_date = now.strftime("%Y-%m-%d")
    stac_online = False

    try:
        catalog = get_stac_catalog()

        # 1. Descubrir años disponibles en ESA WorldCover (esa-worldcover)
        wc_search = catalog.search(
            collections=["esa-worldcover"],
            bbox=target_bbox,
            max_items=20
        )
        for it in wc_search.items():
            start_dt = str(it.properties.get("start_datetime") or "")
            m = re.search(r"(20\d{2})", start_dt) or re.search(r"_(20\d{2})_", it.id)
            if m:
                yr = m.group(1)
                if yr not in wc_years:
                    wc_years.append(yr)

        # 2. Descubrir años disponibles en Esri 10m Annual LULC (io-lulc-annual-v02)
        io_search = catalog.search(
            collections=["io-lulc-annual-v02"],
            bbox=target_bbox,
            max_items=30
        )
        for it in io_search.items():
            start_dt = str(it.properties.get("start_datetime") or "")
            m = re.search(r"(20\d{2})", start_dt) or re.search(r"-(20\d{2})$", it.id)
            if m:
                yr = m.group(1)
                if yr not in io_years:
                    io_years.append(yr)

        # 3. Verificar última fecha real disponible de Sentinel-2 L2A (ventana reciente de 60 días para respuesta instantánea)
        recent_start = (now.date() - datetime.timedelta(days=60)).strftime("%Y-%m-%d")
        recent_end = now.date().strftime("%Y-%m-%d")
        s2_recent = catalog.search(
            collections=["sentinel-2-l2a"],
            bbox=target_bbox,
            datetime=f"{recent_start}/{recent_end}",
            max_items=1
        )
        recent_items = list(s2_recent.items())
        if recent_items and recent_items[0].datetime:
            s2_latest_date = recent_items[0].datetime.strftime("%Y-%m-%d")

        stac_online = True
    except Exception as e:
        print(f"Aviso en discover_available_sources: {e}")

    wc_years = sorted(wc_years, reverse=True) if wc_years else ["2021", "2020"]
    io_years = sorted(io_years, reverse=True) if io_years else ["2023", "2022", "2021", "2020", "2019", "2018", "2017"]

    # Serie dinámica de años para Sentinel-2 L2A (desde 2017 hasta el año calendario actual)
    s2_years = [str(y) for y in range(current_year, 2016, -1)]

    return {
        "stac_online": stac_online,
        "synced_at": now.strftime("%d/%m/%Y %H:%M:%S"),
        "esa_worldcover": {
            "collection_id": "esa-worldcover",
            "nombre": "ESA WorldCover 10m (ESA/VITO - 11 clases)",
            "years": wc_years,
        },
        "io_lulc": {
            "collection_id": "io-lulc-annual-v02",
            "nombre": "Esri / Impact Observatory 10m Annual LULC (Serie Anual - 9 clases)",
            "years": io_years,
        },
        "sentinel2": {
            "collection_id": "sentinel-2-l2a",
            "years": s2_years,
            "min_date": "2017-01-01",
            "max_date": now.date().strftime("%Y-%m-%d"),
            "latest_scene_date": s2_latest_date,
        }
    }

def search_real_scenes(
    bbox: List[float] = None,
    date_range: str = None,
    max_cloud: float = 10.0,
    limit: int = 10
) -> List[Dict[str, Any]]:
    """Busca escenas Sentinel-2 L2A en STAC."""
    import datetime
    target_bbox = bbox or DEFAULT_BBOX
    if not date_range:
        curr_yr = datetime.date.today().year
        date_range = f"{curr_yr - 1}-01-01/{curr_yr}-12-31"
    try:
        catalog = get_stac_catalog()
        search = catalog.search(
            collections=["sentinel-2-l2a"],
            bbox=target_bbox,
            datetime=date_range,
            query={"eo:cloud_cover": {"lt": max_cloud}},
            max_items=limit
        )

        items = list(search.items())
        scenes = []
        for item in items:
            dt = item.datetime.strftime("%Y-%m-%d")
            cloud = round(item.properties.get("eo:cloud_cover", 0.0), 1)
            sat = item.properties.get("platform", "Sentinel-2")
            scenes.append({
                "id": item.id,
                "fecha": dt,
                "satelite": sat,
                "cobertura_nubes_pct": cloud,
                "resolucion_m": 10,
                "sensor": "MSI (Multispectral Instrument)",
                "estado": "Disponible L2A (Reflectancia de Superficie Real)"
            })
        return scenes
    except Exception as e:
        print(f"Error al buscar escenas en STAC: {e}")
        return []

def classify_with_esa_worldcover(
    bbox: List[float] = None,
    year: str = "2021",
    collection_id: str = "auto"
) -> Dict[str, Any]:
    """
    Clasifica el recuadro territorial utilizando Modelos de IA Deep Learning a 10m de resolución:
    - 'esa-worldcover': ESA WorldCover 10m (2020, 2021+)
    - 'io-lulc-annual-v02': Esri / Impact Observatory 10m Annual Land Cover (2017-2023+)
    Si collection_id == 'auto', usa ESA WorldCover si el año existe allí (ej. 2020, 2021) y si no,
    consulta automáticamente Esri 10m Annual LULC (io-lulc-annual-v02).
    """
    target_bbox = bbox or DEFAULT_BBOX
    year_str = str(year).strip()

    # Verificar tamaño del BBox antes de abrir STAC para mantener respuesta rápida en Sandbox
    dim_check = estimate_bbox_dimensions(target_bbox, res_m=10.0)
    if dim_check["bloqueado"]:
        raise ValueError(dim_check["mensaje"])

    catalog = get_stac_catalog()

    # Determinar colección a utilizar
    chosen_collection = collection_id
    if chosen_collection in (None, "", "auto"):
        chosen_collection = "esa-worldcover" if year_str in ("2020", "2021") else "io-lulc-annual-v02"

    search = catalog.search(
        collections=[chosen_collection],
        bbox=target_bbox,
        max_items=25
    )
    items = list(search.items())

    # Fallback automático a la otra colección de IA si no se encontró el año en la primera
    if not items or not any(year_str in it.id or year_str in str(it.properties.get("start_datetime", "")) for it in items):
        alt_collection = "io-lulc-annual-v02" if chosen_collection == "esa-worldcover" else "esa-worldcover"
        alt_search = catalog.search(collections=[alt_collection], bbox=target_bbox, max_items=25)
        alt_items = list(alt_search.items())
        if any(year_str in it.id or year_str in str(it.properties.get("start_datetime", "")) for it in alt_items):
            chosen_collection = alt_collection
            items = alt_items

    if not items:
        raise ValueError(f"No se encontró cobertura del modelo IA ({chosen_collection}) para el BBox {target_bbox}.")

    # Seleccionar el item del año solicitado o el primero disponible
    selected_item = items[0]
    for it in items:
        if year_str in it.id or year_str in str(it.properties.get("start_datetime", "")):
            selected_item = it
            break

    is_io_lulc = (chosen_collection == "io-lulc-annual-v02")
    asset_key = "data" if is_io_lulc else "map"
    classes_dict = IO_LULC_CLASSES if is_io_lulc else ESA_WORLDCOVER_CLASSES
    model_label = (
        "Esri / Impact Observatory 10m LULC (Deep Learning)"
        if is_io_lulc
        else "ESA WorldCover 10m (Deep Learning / ESA-VITO)"
    )
    short_tag = "io_lulc" if is_io_lulc else "worldcover"

    map_url = selected_item.assets[asset_key].href

    raster_env = rasterio.Env(
        GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR",
        CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif",
        VSI_CACHE=True
    )

    with raster_env:
        with rasterio.open(map_url) as src:
            native_bounds = transform_bounds("EPSG:4326", src.crs, *target_bbox)
            raw_window = from_bounds(*native_bounds, transform=src.transform)
            img_window = rasterio.windows.Window(0, 0, src.width, src.height)
            valid_window = raw_window.intersection(img_window).round_lengths().round_offsets()

            if valid_window.width <= 0 or valid_window.height <= 0:
                raise ValueError(f"El recuadro seleccionado queda fuera de los límites del tile de {model_label}.")

            requested_pixels = int(valid_window.width * valid_window.height)
            if requested_pixels > MAX_ALLOWED_PIXELS:
                raise ValueError(
                    f"El área seleccionada contiene {requested_pixels:,} píxeles (~{requested_pixels * 0.01:,.1f} ha), "
                    f"superando el límite máximo seguro de {MAX_ALLOWED_PIXELS:,} píxeles (~100.000 ha). "
                    f"Por favor delimitá un área más pequeña."
                )

            # Leer la matriz clasificada
            data = src.read(1, window=valid_window)

            # Calcular límites geográficos en EPSG:4326
            w_native_bounds = window_bounds_fn(valid_window, src.transform)
            real_geo_bounds = transform_bounds(src.crs, "EPSG:4326", *w_native_bounds)
            
            folium_bounds = [
                [real_geo_bounds[1], real_geo_bounds[0]], # South, West
                [real_geo_bounds[3], real_geo_bounds[2]]  # North, East
            ]

    # Estadísticas por clase
    unique_vals, counts = np.unique(data, return_counts=True)
    total_px = data.size

    coberturas_detalle = {}
    legend_patches = []
    
    # Matriz RGBA para overlay en el mapa
    h, w = data.shape
    rgba_grid = np.zeros((h, w, 4), dtype=np.uint8)

    for code_val, count_val in zip(unique_vals, counts):
        code = int(code_val)
        if code == 0:
            continue
        info = classes_dict.get(code, {"name": f"Clase {code}", "color": "#7f7f7f", "rgb": [127, 127, 127]})
        pct = round((count_val / total_px) * 100, 2)
        ha = round(count_val * 0.01, 1)  # 10m x 10m = 0.01 ha

        coberturas_detalle[str(code)] = {
            "codigo": code,
            "nombre": info["name"],
            "porcentaje": pct,
            "hectareas": ha,
            "pixeles": int(count_val),
            "color_hex": info["color"]
        }

        # Asignar color RGBA
        mask = (data == code)
        r, g, b = info["rgb"]
        rgba_grid[mask] = [r, g, b, 200]

        legend_patches.append(
            mpatches.Patch(color=info["color"], label=f"{info['name']} ({pct}% - {ha:,.1f} ha)")
        )

    total_ha = round(total_px * 0.01, 1)

    # Generar visualización con Matplotlib
    fig, ax = plt.subplots(figsize=(9, 7))
    ax.imshow(rgba_grid, origin="upper")
    ax.set_title(
        f"Clasificación Modelo IA: {model_label} ({year_str})\n"
        f"Superficie: {total_ha:,.1f} ha ({total_px:,} píxeles clasificados)",
        fontsize=11,
        fontweight="bold"
    )
    ax.set_xlabel("Píxeles Este (10m/px)")
    ax.set_ylabel("Píxeles Norte (10m/px)")
    ax.legend(handles=legend_patches, loc="upper right", bbox_to_anchor=(1.35, 1.0), framealpha=0.92, fontsize=9)
    plt.tight_layout()

    output_filename = f"clasificacion_ia_{short_tag}_{year_str}_{abs(int(target_bbox[0]*100))}.png"
    output_path = OUTPUTS_DIR / output_filename
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close()

    # Guardar overlay RGBA para Folium
    overlay_filename = f"overlay_ia_{short_tag}_{year_str}_{abs(int(target_bbox[0]*100))}.png"
    overlay_path = OUTPUTS_DIR / overlay_filename
    img_overlay = Image.fromarray(rgba_grid, mode="RGBA")
    img_overlay.save(overlay_path)

    # Construir resumen textual
    resumen_lines = [
        f"Clasificación realizada con el modelo de IA Deep Learning {model_label} ({year_str}):",
        f"• Superficie Total: {total_ha:,.1f} ha ({total_px:,} píxeles analizados)"
    ]
    for c in sorted(coberturas_detalle.values(), key=lambda x: x["hectareas"], reverse=True):
        resumen_lines.append(f"• {c['nombre']}: {c['porcentaje']}% ({c['hectareas']:,.1f} ha)")

    return {
        "status": "success",
        "modelo": model_label,
        "coleccion_stac": chosen_collection,
        "año_referencia": year_str,
        "superficie_total_ha": total_ha,
        "total_pixeles_10m": total_px,
        "dimensiones_pixeles": [h, w],
        "coberturas": coberturas_detalle,
        "folium_bounds": folium_bounds,
        "mapa_generado": str(output_path),
        "overlay_generado": str(overlay_path),
        "coordenadas_exactas_raster": {
            "bbox_solicitado": target_bbox,
            "geo_bounds_reales": real_geo_bounds,
            "folium_bounds": folium_bounds
        },
        "ubicacion_administrativa": get_location_for_bbox(target_bbox),
        "resumen_ejecutivo": "\n".join(resumen_lines)
    }

def fetch_and_classify_real_scene(
    item_id: str,
    bbox: List[float] = None,
    ndvi_threshold: float = 0.35
) -> Dict[str, Any]:
    """Descarga y clasifica bandas Sentinel-2 L2A en Vegetación, Suelo Desnudo y Agua."""
    target_bbox = bbox or DEFAULT_BBOX
    catalog = get_stac_catalog()
    
    search = catalog.search(collections=["sentinel-2-l2a"], ids=[item_id])
    items = list(search.items())
    if not items:
        search = catalog.search(collections=["sentinel-2-l2a"], bbox=target_bbox, max_items=1)
        items = list(search.items())
        if not items:
            raise ValueError(f"No se encontró la escena '{item_id}' en el catálogo.")

    item = items[0]
    fecha_str = item.datetime.strftime("%Y-%m-%d")
    
    b04_url = item.assets["B04"].href
    b08_url = item.assets["B08"].href

    raster_env = rasterio.Env(
        GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR",
        CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif",
        VSI_CACHE=True
    )

    with raster_env:
        with rasterio.open(b04_url) as src_red:
            native_bounds = transform_bounds("EPSG:4326", src_red.crs, *target_bbox)
            raw_window = from_bounds(*native_bounds, transform=src_red.transform)
            img_window = rasterio.windows.Window(0, 0, src_red.width, src_red.height)
            valid_window = raw_window.intersection(img_window).round_lengths().round_offsets()
            if valid_window.width <= 0 or valid_window.height <= 0:
                raise ValueError("El recuadro seleccionado no se superpone con la escena satelital seleccionada.")

            requested_pixels = int(valid_window.width * valid_window.height)
            if requested_pixels > MAX_ALLOWED_PIXELS:
                raise ValueError(
                    f"El área seleccionada contiene {requested_pixels:,} píxeles (~{requested_pixels * 0.01:,.1f} ha), "
                    f"superando el límite máximo seguro de {MAX_ALLOWED_PIXELS:,} píxeles (~100.000 ha). "
                    f"Por favor delimitá un área más pequeña."
                )

            red = src_red.read(1, window=valid_window).astype("float32")

            w_native_bounds = window_bounds_fn(valid_window, src_red.transform)
            real_geo_bounds = transform_bounds(src_red.crs, "EPSG:4326", *w_native_bounds)
            
            folium_bounds = [
                [real_geo_bounds[1], real_geo_bounds[0]],
                [real_geo_bounds[3], real_geo_bounds[2]]
            ]

        with rasterio.open(b08_url) as src_nir:
            nir = src_nir.read(1, window=valid_window).astype("float32")

    min_h = min(red.shape[0], nir.shape[0])
    min_w = min(red.shape[1], nir.shape[1])
    
    if min_h == 0 or min_w == 0:
        raise ValueError("El recuadro solicitado no se superpone con la escena satelital seleccionada.")

    red = red[:min_h, :min_w]
    nir = nir[:min_h, :min_w]

    denom = nir + red
    ndvi = np.where(denom > 0, (nir - red) / (denom + 1e-6), 0.0)

    veg_mask = ndvi >= ndvi_threshold
    suelo_mask = (ndvi < ndvi_threshold) & (ndvi >= 0.05)
    agua_mask = ndvi < 0.05

    total_px = ndvi.size
    veg_px = int(np.sum(veg_mask))
    suelo_px = int(np.sum(suelo_mask))
    agua_px = int(np.sum(agua_mask))

    veg_pct = round((veg_px / total_px) * 100, 2)
    suelo_pct = round((suelo_px / total_px) * 100, 2)
    agua_pct = round((agua_px / total_px) * 100, 2)

    ha_por_pixel = 0.01
    total_ha = round(total_px * ha_por_pixel, 1)
    veg_ha = round(veg_px * ha_por_pixel, 1)
    suelo_ha = round(suelo_px * ha_por_pixel, 1)
    agua_ha = round(agua_px * ha_por_pixel, 1)

    grid = np.zeros(ndvi.shape, dtype=int)
    grid[veg_mask] = 1
    grid[agua_mask] = 2

    cmap = ListedColormap(["#c29b61", "#2e7d32", "#1976d2"])
    fig, ax = plt.subplots(figsize=(8, 6.5))
    im = ax.imshow(grid, cmap=cmap, origin="upper")

    ax.set_title(
        f"Clasificación Radiométrica (NDVI Sentinel-2 L2A) - Fecha: {fecha_str}\n"
        f"Resolución: 10m | Extensión: {total_ha:,.1f} ha ({total_px:,} píxeles)",
        fontsize=10,
        fontweight="bold"
    )
    ax.set_xlabel("Píxeles Este (10m/px)")
    ax.set_ylabel("Píxeles Norte (10m/px)")

    patch_veg = mpatches.Patch(color="#2e7d32", label=f"Vegetación ({veg_pct}% - {veg_ha:,.1f} ha)")
    patch_suelo = mpatches.Patch(color="#c29b61", label=f"Suelo Desnudo ({suelo_pct}% - {suelo_ha:,.1f} ha)")
    patch_agua = mpatches.Patch(color="#1976d2", label=f"Agua / Sombras ({agua_pct}% - {agua_ha:,.1f} ha)")
    ax.legend(handles=[patch_veg, patch_suelo, patch_agua], loc="lower right", framealpha=0.92)

    plt.tight_layout()
    output_filename = f"clasificacion_real_{fecha_str.replace('-', '')}_{item_id[:15]}.png"
    output_path = OUTPUTS_DIR / output_filename
    plt.savefig(output_path, dpi=150)
    plt.close()

    rgba_grid = np.zeros((ndvi.shape[0], ndvi.shape[1], 4), dtype=np.uint8)
    rgba_grid[veg_mask] = [46, 125, 50, 180]
    rgba_grid[suelo_mask] = [194, 155, 97, 180]
    rgba_grid[agua_mask] = [25, 118, 210, 180]

    overlay_filename = f"overlay_geo_{fecha_str.replace('-', '')}_{item_id[:15]}.png"
    overlay_path = OUTPUTS_DIR / overlay_filename
    img_overlay = Image.fromarray(rgba_grid, mode="RGBA")
    img_overlay.save(overlay_path)

    resumen_text = (
        f"Para la escena Sentinel-2 ({fecha_str}), sobre una superficie total de {total_ha:,.1f} ha ({total_px:,} px a 10m), se identificaron:\n"
        f"• Vegetación (NDVI ≥ {ndvi_threshold}): {veg_pct}% ({veg_ha:,.1f} ha)\n"
        f"• Suelo Desnudo / Barbecho (0.05 ≤ NDVI < {ndvi_threshold}): {suelo_pct}% ({suelo_ha:,.1f} ha)\n"
        f"• Agua / Sombras / Nubes bajas (NDVI < 0.05): {agua_pct}% ({agua_ha:,.1f} ha)"
    )

    return {
        "status": "success",
        "modelo": "Umbralización Radiométrica NDVI (Sentinel-2 L2A)",
        "escena_id": item_id,
        "satelite": "Sentinel-2 (L2A - Reflectancia de Superficie)",
        "fecha_analizada": fecha_str,
        "proveedor": "Microsoft Planetary Computer STAC API (ESA Copernicus)",
        "superficie_total_ha": total_ha,
        "total_pixeles_10m": total_px,
        "dimensiones_pixeles": [min_h, min_w],
        "coordenadas_exactas_raster": {
            "bbox_solicitado": target_bbox,
            "geo_bounds_reales": real_geo_bounds,
            "folium_bounds": folium_bounds
        },
        "ndvi_estadisticas": {
            "media": round(float(np.nanmean(ndvi)), 3),
            "minimo": round(float(np.nanmin(ndvi)), 3),
            "maximo": round(float(np.nanmax(ndvi)), 3)
        },
        "coberturas": {
            "vegetacion": {
                "porcentaje": veg_pct,
                "hectareas": veg_ha,
                "pixeles": veg_px,
                "nombre": f"Vegetación (NDVI ≥ {ndvi_threshold})"
            },
            "suelo_desnudo": {
                "porcentaje": suelo_pct,
                "hectareas": suelo_ha,
                "pixeles": suelo_px,
                "nombre": "Suelo Desnudo / Barbecho"
            },
            "cuerpos_de_agua": {
                "porcentaje": agua_pct,
                "hectareas": agua_ha,
                "pixeles": agua_px,
                "nombre": "Agua / Sombras / Humedales"
            }
        },
        "mapa_generado": str(output_path),
        "overlay_generado": str(overlay_path),
        "folium_bounds": folium_bounds,
        "ubicacion_administrativa": get_location_for_bbox(target_bbox),
        "resumen_ejecutivo": resumen_text
    }
