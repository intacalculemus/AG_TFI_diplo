"""
Servicio de Análisis Hidrológico y Red de Drenaje Superficial
Calcula a partir de Modelos Digitales de Elevación (Copernicus DEM 30m / NASADEM vía Planetary Computer):
1. Pendientes topográficas (grados y porcentaje) y Desnivel
2. Dirección y orientación del escurrimiento superficial (vectores de flujo D8/gradiente)
3. Líneas de corriente (Streamlines) con intensidad y flechas direccionales
4. Cruce agrohidrológico con coberturas del suelo y evaluación de riesgo de erosión hídrica
"""
import os
import math
from typing import List, Dict, Any, Optional, Tuple
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.colors import Normalize
from PIL import Image

import pystac_client
import planetary_computer
import rasterio
from rasterio.windows import from_bounds, bounds as window_bounds_fn
from rasterio.warp import transform_bounds

from config import OUTPUTS_DIR
from services.geo_admin_service import get_location_for_bbox

STAC_API_URL = "https://planetarycomputer.microsoft.com/api/stac/v1"
DEFAULT_BBOX = [-62.80, -30.70, -62.50, -30.50]

def get_stac_catalog():
    """Inicializa y firma el cliente STAC de Planetary Computer."""
    return pystac_client.Client.open(
        STAC_API_URL,
        modifier=planetary_computer.sign_inplace
    )

def azimuth_to_compass(azimuth_deg: float) -> str:
    """Convierte un ángulo de acimut en grados a rumbo cardinal en español."""
    val = (azimuth_deg % 360.0)
    directions = [
        ("Norte (N)", 0),
        ("Noreste (NE)", 45),
        ("Este (E)", 90),
        ("Sureste (SE)", 135),
        ("Sur (S)", 180),
        ("Suroeste (SO)", 225),
        ("Oeste (O)", 270),
        ("Noroeste (NO)", 315),
        ("Norte (N)", 360)
    ]
    closest_dir = "Norte (N)"
    min_diff = 999.0
    for name, angle in directions:
        diff = abs(val - angle)
        if diff < min_diff:
            min_diff = diff
            closest_dir = name
    return closest_dir

def compute_hillshade(dem_array: np.ndarray, dy_m: float, dx_m: float, azimuth_deg: float = 315.0, altitude_deg: float = 45.0) -> np.ndarray:
    """Calcula el relieve sombreado (Hillshade) a partir de una matriz DEM."""
    gy, gx = np.gradient(dem_array, dy_m, dx_m)
    slope_rad = np.arctan(np.sqrt(gx**2 + gy**2))
    aspect_rad = np.arctan2(-gx, gy)
    
    azimuth_rad = np.radians(azimuth_deg)
    zenith_rad = np.radians(90.0 - altitude_deg)
    
    shaded = np.cos(zenith_rad) * np.cos(slope_rad) + np.sin(zenith_rad) * np.sin(slope_rad) * np.cos(azimuth_rad - aspect_rad)
    shaded = np.clip(shaded, 0, 1)
    return (shaded * 255).astype(np.uint8)

def analyze_drainage_and_slope(
    bbox: List[float] = None,
    classification_context: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Descarga el Modelo Digital de Elevación (DEM 30m) para el Bounding Box solicitado,
    calcula la red de líneas de drenaje superficial, pendiente, dirección de flujo y cruza
    con los sectores de uso de suelo clasificados.
    """
    target_bbox = bbox or DEFAULT_BBOX
    min_lon, min_lat, max_lon, max_lat = target_bbox

    catalog = get_stac_catalog()

    # Búsqueda en colecciones DEM (Copernicus DEM 30m o NASADEM como alternativa)
    search = catalog.search(
        collections=["cop-dem-glo-30"],
        bbox=target_bbox,
        max_items=4
    )
    items = list(search.items())
    if not items:
        search = catalog.search(
            collections=["nasadem"],
            bbox=target_bbox,
            max_items=4
        )
        items = list(search.items())
        if not items:
            raise ValueError(f"No se encontró cobertura DEM en el catálogo para el área {target_bbox}.")

    selected_item = items[0]
    dem_asset_key = "data" if "data" in selected_item.assets else list(selected_item.assets.keys())[0]
    dem_url = selected_item.assets[dem_asset_key].href

    raster_env = rasterio.Env(
        GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR",
        CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif",
        VSI_CACHE=True
    )

    with raster_env:
        with rasterio.open(dem_url) as src:
            native_bounds = transform_bounds("EPSG:4326", src.crs, *target_bbox)
            raw_window = from_bounds(*native_bounds, transform=src.transform)
            img_window = rasterio.windows.Window(0, 0, src.width, src.height)
            valid_window = raw_window.intersection(img_window).round_lengths().round_offsets()

            if valid_window.width <= 0 or valid_window.height <= 0:
                raise ValueError("El recuadro seleccionado queda fuera de los límites del DEM.")

            dem = src.read(1, window=valid_window).astype("float32")
            
            # Límites geográficos reales leídos
            w_native_bounds = window_bounds_fn(valid_window, src.transform)
            real_geo_bounds = transform_bounds(src.crs, "EPSG:4326", *w_native_bounds)
            
            folium_bounds = [
                [real_geo_bounds[1], real_geo_bounds[0]], # South, West
                [real_geo_bounds[3], real_geo_bounds[2]]  # North, East
            ]

    # Reemplazar valores no válidos (NoData) si existiesen
    dem = np.where((dem < -500) | (dem > 9000), np.nan, dem)
    if np.isnan(dem).all():
        raise ValueError("El DEM obtenido contiene únicamente valores nulos.")
    
    # Rellenar NaNs con interpolación o mediana
    if np.isnan(dem).any():
        med_val = float(np.nanmedian(dem))
        dem = np.nan_to_num(dem, nan=med_val)

    h, w = dem.shape
    r_min_lon, r_min_lat, r_max_lon, r_max_lat = real_geo_bounds
    mid_lat = (r_min_lat + r_max_lat) / 2.0

    # Dimensiones métricas de las celdas
    dy_m = max(1.0, ((r_max_lat - r_min_lat) / h) * 111320.0)
    dx_m = max(1.0, ((r_max_lon - r_min_lon) / w) * 111320.0 * math.cos(math.radians(mid_lat)))

    # Coordenadas cartesianas: invertir eje Y para que el índice 0 sea el Sur (min_lat)
    dem_cart = np.flipud(dem)
    gy, gx = np.gradient(dem_cart, dy_m, dx_m)

    # Pendiente en porcentaje (%) y en grados (°)
    slope_pct = np.sqrt(gx**2 + gy**2) * 100.0
    slope_deg = np.degrees(np.arctan(slope_pct / 100.0))

    # Vectores de escurrimiento superficial hacia abajo del gradiente
    # En plano cartesiano (X=Este, Y=Norte): el agua desciende por la máxima pendiente
    u_flow = -gx
    v_flow = -gy

    # Orientación / Acimut del flujo (0° = Norte, 90° = Este, 180° = Sur, 270° = Oeste)
    aspect_rad = np.arctan2(u_flow, v_flow)
    aspect_deg = (np.degrees(aspect_rad) + 360.0) % 360.0

    # Estadísticas Topográficas
    elev_min = round(float(np.min(dem)), 1)
    elev_max = round(float(np.max(dem)), 1)
    elev_mean = round(float(np.mean(dem)), 1)
    desnivel_m = round(elev_max - elev_min, 1)

    slope_mean = round(float(np.mean(slope_pct)), 2)
    slope_max = round(float(np.max(slope_pct)), 2)
    slope_median = round(float(np.median(slope_pct)), 2)

    # Dirección media ponderada por la pendiente
    mean_u = float(np.mean(u_flow))
    mean_v = float(np.mean(v_flow))
    mean_azimuth = (math.degrees(math.atan2(mean_u, mean_v)) + 360.0) % 360.0
    rumbo_predominante = azimuth_to_compass(mean_azimuth)

    # Distribución de rangos de pendiente
    total_cells = dem.size
    cell_ha = (dy_m * dx_m) / 10000.0
    total_ha = round(total_cells * cell_ha, 1)

    mask_plana = slope_pct < 1.0
    mask_suave = (slope_pct >= 1.0) & (slope_pct < 3.0)
    mask_moderada = (slope_pct >= 3.0) & (slope_pct < 8.0)
    mask_fuerte = (slope_pct >= 8.0) & (slope_pct < 15.0)
    mask_muy_fuerte = slope_pct >= 15.0

    distribucion_pendientes = {
        "plana_menor_1pct": {
            "nombre": "Plano (< 1%)",
            "descripcion": "Escurrimiento muy lento / Posible anegamiento",
            "porcentaje": round((np.sum(mask_plana) / total_cells) * 100, 1),
            "hectareas": round(np.sum(mask_plana) * cell_ha, 1)
        },
        "suave_1_a_3pct": {
            "nombre": "Suave (1% - 3%)",
            "descripcion": "Drenaje adecuado para agricultura con bajo riesgo",
            "porcentaje": round((np.sum(mask_suave) / total_cells) * 100, 1),
            "hectareas": round(np.sum(mask_suave) * cell_ha, 1)
        },
        "moderada_3_a_8pct": {
            "nombre": "Moderado (3% - 8%)",
            "descripcion": "Riesgo moderado de erosión hídrica en surcos",
            "porcentaje": round((np.sum(mask_moderada) / total_cells) * 100, 1),
            "hectareas": round(np.sum(mask_moderada) * cell_ha, 1)
        },
        "fuerte_8_a_15pct": {
            "nombre": "Fuerte (8% - 15%)",
            "descripcion": "Riesgo alto de cárcavas / Requiere manejo conservacionista",
            "porcentaje": round((np.sum(mask_fuerte) / total_cells) * 100, 1),
            "hectareas": round(np.sum(mask_fuerte) * cell_ha, 1)
        },
        "muy_fuerte_mayor_15pct": {
            "nombre": "Muy Fuerte (> 15%)",
            "descripcion": "Zonas de ladera / Aporte hídrico torrencial",
            "porcentaje": round((np.sum(mask_muy_fuerte) / total_cells) * 100, 1),
            "hectareas": round(np.sum(mask_muy_fuerte) * cell_ha, 1)
        }
    }

    # Cruce con Coberturas de Suelo si están disponibles en el contexto
    analisis_agrohidrologico = {}
    riesgo_erosion_cultivos = "Bajo"
    if classification_context and "coberturas" in classification_context:
        cobs = classification_context["coberturas"]
        # Evaluar riesgo en cultivos agrícolas o suelo desnudo
        if slope_mean > 5.0 or np.sum(mask_fuerte) / total_cells > 0.10:
            riesgo_erosion_cultivos = "Alto a Severo (Formación de cárcavas y pérdida de suelo fértil)"
            recomendacion = "Implementar siembra en contorno, terrazas de absorción/desagüe y franjas de amortiguación."
        elif slope_mean > 2.5 or np.sum(mask_moderada) / total_cells > 0.20:
            riesgo_erosion_cultivos = "Moderado (Escurrimiento concentrado en sectores agrícolas)"
            recomendacion = "Monitorear huellas de escurrimiento, mantener rastrojo y cobertura vegetal continua."
        else:
            riesgo_erosion_cultivos = "Bajo (Relieve predominantemente llano o suave)"
            recomendacion = "Buenas condiciones para laboreo; vigilar drenaje natural en eventos extraordinarios."
        
        analisis_agrohidrologico = {
            "riesgo_erosion_hidrica": riesgo_erosion_cultivos,
            "recomendacion_conservacion": recomendacion
        }

    # Relieve sombreado para fondo
    hillshade = compute_hillshade(dem, dy_m, dx_m)

    # Submuestreo adaptativo para graficación de líneas de corriente (Streamplot)
    target_pts = 70
    step_x = max(1, w // target_pts)
    step_y = max(1, h // target_pts)

    x_grid = np.linspace(r_min_lon, r_max_lon, w)[::step_x]
    y_grid = np.linspace(r_min_lat, r_max_lat, h)[::step_y]

    u_sub = u_flow[::step_y, ::step_x]
    v_sub = v_flow[::step_y, ::step_x]
    slope_sub = slope_pct[::step_y, ::step_x]

    # Prevenir vectores idénticos a cero para streamplot
    mag = np.sqrt(u_sub**2 + v_sub**2)
    if np.max(mag) < 1e-7:
        # Relieve prácticamente nulo: agregar gradiente ínfimo para graficar
        u_sub += 1e-6

    # -------------------------------------------------------------
    # 1. MAPA TEMÁTICO DE ALTA RESOLUCIÓN (PNG)
    # -------------------------------------------------------------
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 7.2), dpi=150, gridspec_kw={"width_ratios": [1.2, 1]})
    
    # Subplot 1: Topografía + Sombreado 3D + Líneas de Drenaje Hídrico
    ax1.imshow(hillshade, extent=[r_min_lon, r_max_lon, r_min_lat, r_max_lat], cmap="gray", origin="upper", alpha=0.6)
    im_elev = ax1.imshow(dem, extent=[r_min_lon, r_max_lon, r_min_lat, r_max_lat], cmap="terrain", origin="upper", alpha=0.65)
    
    strm = ax1.streamplot(
        x_grid, y_grid, u_sub, v_sub,
        color=slope_sub,
        cmap="plasma",
        density=1.4,
        linewidth=1.5,
        arrowsize=1.3,
        arrowstyle="->",
        norm=Normalize(vmin=0, vmax=max(5.0, float(np.percentile(slope_pct, 95))))
    )
    
    cbar1 = fig.colorbar(strm.lines, ax=ax1, fraction=0.046, pad=0.04)
    cbar1.set_label("Intensidad / Pendiente de Flujo (%)", fontsize=9, fontweight="bold")
    
    cbar_elev = fig.colorbar(im_elev, ax=ax1, fraction=0.046, pad=0.08)
    cbar_elev.set_label("Elevación (m.s.n.m.)", fontsize=9)

    ax1.set_title(
        f"Red de Drenaje Hídrico Superficial y Dirección de Flujo\n"
        f"Rumbo Predominante: {rumbo_predominante} ({round(mean_azimuth, 1)}°) | Desnivel: {desnivel_m} m",
        fontsize=10,
        fontweight="bold"
    )
    ax1.set_xlabel("Longitud (°)")
    ax1.set_ylabel("Latitud (°)")

    # Subplot 2: Mapa de Clasificación de Pendientes y Riesgo
    slope_img = np.zeros(dem.shape, dtype=np.uint8)
    slope_img[mask_plana] = 0
    slope_img[mask_suave] = 1
    slope_img[mask_moderada] = 2
    slope_img[mask_fuerte] = 3
    slope_img[mask_muy_fuerte] = 4

    cmap_slopes = matplotlib.colors.ListedColormap(["#2b83ba", "#abdda4", "#ffffbf", "#fdae61", "#d7191c"])
    ax2.imshow(slope_img, extent=[r_min_lon, r_max_lon, r_min_lat, r_max_lat], cmap=cmap_slopes, origin="upper", alpha=0.9)
    
    legend_patches = [
        mpatches.Patch(color="#2b83ba", label=f"< 1% Plano ({distribucion_pendientes['plana_menor_1pct']['porcentaje']}%)"),
        mpatches.Patch(color="#abdda4", label=f"1-3% Suave ({distribucion_pendientes['suave_1_a_3pct']['porcentaje']}%)"),
        mpatches.Patch(color="#ffffbf", label=f"3-8% Moderado ({distribucion_pendientes['moderada_3_a_8pct']['porcentaje']}%)"),
        mpatches.Patch(color="#fdae61", label=f"8-15% Fuerte ({distribucion_pendientes['fuerte_8_a_15pct']['porcentaje']}%)"),
        mpatches.Patch(color="#d7191c", label=f"> 15% Muy Fuerte ({distribucion_pendientes['muy_fuerte_mayor_15pct']['porcentaje']}%)")
    ]
    ax2.legend(handles=legend_patches, loc="upper right", framealpha=0.92, fontsize=8.5, title="Rangos de Pendiente")
    ax2.set_title(
        f"Zonificación de Pendientes y Riesgo Agroambiental\n"
        f"Pendiente Media: {slope_mean}% | Máxima: {slope_max}%",
        fontsize=10,
        fontweight="bold"
    )
    ax2.set_xlabel("Longitud (°)")
    ax2.set_ylabel("Latitud (°)")

    plt.tight_layout()
    output_filename = f"mapa_drenaje_hidrico_{abs(int(target_bbox[0]*100))}_{abs(int(target_bbox[1]*100))}.png"
    output_path = OUTPUTS_DIR / output_filename
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close()

    # -------------------------------------------------------------
    # 2. OVERLAY TRANSPARENTE PARA FOLIUM (LÍNEAS DE DRENAJE)
    # -------------------------------------------------------------
    fig_ov = plt.figure(figsize=(10, 10), dpi=150)
    ax_ov = fig_ov.add_axes([0, 0, 1, 1])
    ax_ov.axis("off")
    ax_ov.patch.set_alpha(0.0)

    # Streamplot en canvas transparente
    ax_ov.streamplot(
        x_grid, y_grid, u_sub, v_sub,
        color=slope_sub,
        cmap="autumn",
        density=1.6,
        linewidth=2.0,
        arrowsize=1.5,
        arrowstyle="->",
        norm=Normalize(vmin=0, vmax=max(4.0, float(np.percentile(slope_pct, 95))))
    )
    ax_ov.set_xlim(r_min_lon, r_max_lon)
    ax_ov.set_ylim(r_min_lat, r_max_lat)

    overlay_filename = f"overlay_drenaje_hidrico_{abs(int(target_bbox[0]*100))}_{abs(int(target_bbox[1]*100))}.png"
    overlay_path = OUTPUTS_DIR / overlay_filename
    fig_ov.savefig(overlay_path, transparent=True, dpi=150)
    plt.close()

    # Resumen Ejecutivo
    resumen_text = (
        f"🌊 **Diagnóstico Hidrológico y Red de Drenaje Superficial:**\n"
        f"• **Modelo de Elevación:** Copernicus DEM 30m (ESA/Planetary Computer)\n"
        f"• **Superficie Analizada:** {total_ha:,.1f} ha | **Desnivel Topográfico:** {desnivel_m} m (Cotas: {elev_min} m a {elev_max} m.s.n.m.)\n"
        f"• **Pendiente:** Media {slope_mean}% | Máxima {slope_max}% | Mediana {slope_median}%\n"
        f"• **Dirección Predominante de Escurrimiento:** {rumbo_predominante} (Acimut: {round(mean_azimuth, 1)}°)\n"
        f"• **Distribución de Relieve:**\n"
        f"  - Plano (< 1%): {distribucion_pendientes['plana_menor_1pct']['porcentaje']}% ({distribucion_pendientes['plana_menor_1pct']['hectareas']:,.1f} ha)\n"
        f"  - Suave (1-3%): {distribucion_pendientes['suave_1_a_3pct']['porcentaje']}% ({distribucion_pendientes['suave_1_a_3pct']['hectareas']:,.1f} ha)\n"
        f"  - Moderado (3-8%): {distribucion_pendientes['moderada_3_a_8pct']['porcentaje']}% ({distribucion_pendientes['moderada_3_a_8pct']['hectareas']:,.1f} ha)\n"
        f"  - Fuerte / Ladera (> 8%): {distribucion_pendientes['fuerte_8_a_15pct']['porcentaje'] + distribucion_pendientes['muy_fuerte_mayor_15pct']['porcentaje']:.1f}%\n"
        f"• **Evaluación de Riesgo de Erosión Hídrica:** {riesgo_erosion_cultivos}"
    )

    return {
        "status": "success",
        "tipo_analisis": "Red de Drenaje Hídrico Superficial y Pendientes",
        "fuente_dem": "Copernicus DEM 30m GLO-30 (ESA / Microsoft Planetary Computer)",
        "superficie_total_ha": total_ha,
        "elevacion": {
            "minima_msnm": elev_min,
            "maxima_msnm": elev_max,
            "media_msnm": elev_mean,
            "desnivel_m": desnivel_m
        },
        "pendientes": {
            "media_pct": slope_mean,
            "maxima_pct": slope_max,
            "mediana_pct": slope_median,
            "distribucion": distribucion_pendientes
        },
        "direccion_flujo": {
            "acimut_grados": round(mean_azimuth, 1),
            "rumbo_cardinal": rumbo_predominante,
            "componentes": {"u_mean": round(mean_u, 4), "v_mean": round(mean_v, 4)}
        },
        "analisis_agrohidrologico": analisis_agrohidrologico,
        "mapa_generado": str(output_path),
        "overlay_generado": str(overlay_path),
        "folium_bounds": folium_bounds,
        "ubicacion_administrativa": get_location_for_bbox(target_bbox),
        "resumen_ejecutivo": resumen_text
    }
