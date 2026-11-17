"""
Servicio de Análisis Hidrológico, Red de Drenaje Superficial y Cruce Espacial Cobertura x Pendiente
Calcula a partir de Modelos Digitales de Elevación (Copernicus DEM 30m / NASADEM vía Planetary Computer):
1. Pendientes topográficas (grados y porcentaje) en 6 rangos y Desnivel
2. Dirección y orientación del escurrimiento superficial (vectores de gradiente)
3. Líneas de corriente (Streamlines) con intensidad y flechas direccionales
4. Cruce espacial píxel a píxel (Cobertura del Suelo x Pendiente) con enmascaramiento de cuerpos de agua
5. Clasificación de Régimen Territorial y Diagnóstico Multi-Dominio (Agronómico, Cuencas/Bosque Nativo, Urbano e IUF)
"""
import os
import math
import hashlib
from typing import List, Dict, Any, Optional, Tuple
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.colors import Normalize

import pystac_client
import planetary_computer
import rasterio
from rasterio.windows import from_bounds, bounds as window_bounds_fn, transform as window_transform_fn
from rasterio.warp import transform_bounds, reproject, Resampling
from rasterio.transform import Affine

from config import OUTPUTS_DIR
from services.geo_admin_service import get_location_for_bbox
from services.real_satellite_service import (
    MACRO_CLASS_META,
    MACRO_ID_TO_KEY,
    map_code_grid_to_macro_ids,
    fetch_landcover_reference_for_bbox,
)

STAC_API_URL = "https://planetarycomputer.microsoft.com/api/stac/v1"
DEFAULT_BBOX = [-62.80, -30.70, -62.50, -30.50]

# Rangos de pendiente adaptados tanto a relieve llano/agrícola como a cuencas serranas y de montaña
SLOPE_BINS: List[Tuple[str, str, str, str, float, float, str]] = [
    (
        "plana_menor_1pct",
        "Plano (< 1%)",
        "< 1% Plano",
        "#74add1",
        0.0,
        1.0,
        "Escurrimiento muy lento / Planicie aluvial o posible anegamiento",
    ),
    (
        "suave_1_a_3pct",
        "Suave (1% - 3%)",
        "1-3% Suave",
        "#abdda4",
        1.0,
        3.0,
        "Escurrimiento laminar lento / Bajo potencial erosivo",
    ),
    (
        "moderada_3_a_8pct",
        "Moderado (3% - 8%)",
        "3-8% Moderado",
        "#ffffbf",
        3.0,
        8.0,
        "Escurrimiento moderado / Sensible ante suelo sin cobertura",
    ),
    (
        "fuerte_8_a_15pct",
        "Fuerte (8% - 15%)",
        "8-15% Fuerte",
        "#fdae61",
        8.0,
        15.0,
        "Escurrimiento rápido / Restricción agrícola y protección de ladera",
    ),
    (
        "muy_fuerte_15_a_30pct",
        "Muy Fuerte (15% - 30%)",
        "15-30% Muy Fuerte",
        "#d7191c",
        15.0,
        30.0,
        "Ladera escarpada / Aporte hídrico rápido y rol protector forestal",
    ),
    (
        "extrema_mayor_30pct",
        "Extremo (> 30%)",
        "> 30% Extremo",
        "#7f0000",
        30.0,
        float("inf"),
        "Escarpe montañoso / Escorrentía torrencial y riesgo geotécnico",
    ),
]


def _bbox_tag(bbox: List[float]) -> str:
    norm = ",".join(f"{float(v):.4f}" for v in bbox)
    return hashlib.sha1(norm.encode("utf-8")).hexdigest()[:8]


def get_stac_catalog():
    """Inicializa y firma el cliente STAC de Planetary Computer."""
    return pystac_client.Client.open(
        STAC_API_URL,
        modifier=planetary_computer.sign_inplace,
    )


def azimuth_to_compass(azimuth_deg: float) -> str:
    """Convierte un ángulo de acimut en grados a rumbo cardinal en español."""
    val = azimuth_deg % 360.0
    directions = [
        ("Norte (N)", 0),
        ("Noreste (NE)", 45),
        ("Este (E)", 90),
        ("Sureste (SE)", 135),
        ("Sur (S)", 180),
        ("Suroeste (SO)", 225),
        ("Oeste (O)", 270),
        ("Noroeste (NO)", 315),
        ("Norte (N)", 360),
    ]
    closest_dir = "Norte (N)"
    min_diff = 999.0
    for name, angle in directions:
        diff = abs(val - angle)
        if diff < min_diff:
            min_diff = diff
            closest_dir = name
    return closest_dir


def compute_hillshade(
    dem_array: np.ndarray,
    dy_m: float,
    dx_m: float,
    azimuth_deg: float = 315.0,
    altitude_deg: float = 45.0,
) -> np.ndarray:
    """Calcula el relieve sombreado (Hillshade) a partir de una matriz DEM."""
    gy, gx = np.gradient(dem_array, dy_m, dx_m)
    slope_rad = np.arctan(np.sqrt(gx**2 + gy**2))
    aspect_rad = np.arctan2(-gx, gy)

    azimuth_rad = np.radians(azimuth_deg)
    zenith_rad = np.radians(90.0 - altitude_deg)

    shaded = (
        np.cos(zenith_rad) * np.cos(slope_rad)
        + np.sin(zenith_rad) * np.sin(slope_rad) * np.cos(azimuth_rad - aspect_rad)
    )
    shaded = np.clip(shaded, 0, 1)
    return (shaded * 255).astype(np.uint8)


def _binary_dilation_2d(mask: np.ndarray, radius_px: int = 5) -> np.ndarray:
    """Dilatación morfológica binaria 2D con elemento estructurante circular usando NumPy puro."""
    if not mask.any() or radius_px <= 0:
        return mask.copy()
    h, w = mask.shape
    padded = np.pad(mask, radius_px, mode="constant", constant_values=False)
    out = np.zeros_like(mask, dtype=bool)
    r2 = radius_px * radius_px
    for dy in range(-radius_px, radius_px + 1):
        for dx in range(-radius_px, radius_px + 1):
            if dy * dy + dx * dx <= r2:
                y0 = radius_px + dy
                x0 = radius_px + dx
                out |= padded[y0 : y0 + h, x0 : x0 + w]
    return out


def _infer_schema_from_context(ctx: Dict[str, Any]) -> str:
    """Deduce el esquema de clases de cobertura a partir de los metadatos de clasificación."""
    explicit = ctx.get("raster_schema") or ctx.get("coleccion_stac")
    if explicit in ("esa-worldcover", "io-lulc-annual-v02", "sentinel2-ndvi"):
        return explicit
    modelo = str(ctx.get("modelo", "")).lower()
    if "lulc" in modelo or "esri" in modelo:
        return "io-lulc-annual-v02"
    if "ndvi" in modelo or "radiom" in modelo:
        return "sentinel2-ndvi"
    return "esa-worldcover"


def _resolve_landcover_for_cross(
    bbox: List[float],
    classification_context: Optional[Dict[str, Any]],
    auto_fetch_landcover: bool,
) -> Tuple[Optional[Dict[str, Any]], str]:
    """
    Obtiene el contexto de cobertura con caché matricial (.npz) para realizar el cruce espacial:
    1. Si classification_context trae un raster_cache_path válido, lo reutiliza sin red.
    2. Si no trae caché o es None y auto_fetch_landcover=True, descarga referencia ESA WorldCover / IO-LULC.
    """
    if classification_context and isinstance(classification_context, dict):
        cache_path = classification_context.get("raster_cache_path")
        if cache_path and os.path.exists(cache_path):
            fecha_lbl = (
                classification_context.get("año_referencia")
                or classification_context.get("fecha_analizada")
                or ""
            )
            modelo_lbl = classification_context.get("modelo", "Clasificación Activa")
            label = f"{modelo_lbl} ({fecha_lbl}) — Clasificación activa".strip()
            return classification_context, label

    if auto_fetch_landcover:
        ref = fetch_landcover_reference_for_bbox(bbox)
        if ref and ref.get("raster_cache_path") and os.path.exists(ref["raster_cache_path"]):
            fecha_lbl = ref.get("año_referencia") or "2021"
            label = f"{ref.get('modelo', 'ESA WorldCover 10m')} ({fecha_lbl}) — Referencia automática"
            return ref, label

    if classification_context and isinstance(classification_context, dict):
        return classification_context, f"{classification_context.get('modelo', 'Clasificación')} (solo resumen global)"

    return None, "Sin cobertura disponible"


def _align_landcover_to_dem(
    raster_cache_path: str,
    schema: str,
    dem_shape: Tuple[int, int],
    dem_transform: Affine,
    dem_crs: Any,
) -> Optional[np.ndarray]:
    """
    Reproyecta el ráster clasificado (10m UTM/WGS84) a la grilla exacta del DEM (30m)
    mediante vecino más cercano (Resampling.nearest), preservando orientación Norte-arriba.
    """
    try:
        with np.load(raster_cache_path, allow_pickle=False) as npz:
            lc_grid = npz["grid"].astype(np.uint8)
            tf_vals = npz["transform"]
            crs_raw = npz["crs"]
            lc_crs_str = str(crs_raw.item() if crs_raw.ndim == 0 else crs_raw)

        src_transform = Affine(*[float(x) for x in tf_vals[:6]])
        macro_src = map_code_grid_to_macro_ids(lc_grid, schema)

        dst_macro = np.zeros(dem_shape, dtype=np.uint8)
        reproject(
            source=macro_src,
            destination=dst_macro,
            src_transform=src_transform,
            src_crs=lc_crs_str,
            dst_transform=dem_transform,
            dst_crs=dem_crs,
            resampling=Resampling.nearest,
            src_nodata=0,
            dst_nodata=0,
        )
        return dst_macro
    except Exception as e:
        print(f"Aviso en alineación espacial Cobertura x DEM: {e}")
        return None


def _compute_slope_distribution(
    slope_north_up: np.ndarray,
    terrestrial_mask: np.ndarray,
    cell_ha: float,
) -> Dict[str, Dict[str, Any]]:
    """Calcula la distribución cuantitativa de pendientes sobre celdas terrestres."""
    terr_count = int(np.sum(terrestrial_mask))
    denom = max(1, terr_count)
    dist: Dict[str, Dict[str, Any]] = {}

    for key, nombre, _short, _color, low, high, desc in SLOPE_BINS:
        if math.isinf(high):
            bin_mask = terrestrial_mask & (slope_north_up >= low)
        else:
            bin_mask = terrestrial_mask & (slope_north_up >= low) & (slope_north_up < high)
        cnt = int(np.sum(bin_mask))
        dist[key] = {
            "nombre": nombre,
            "descripcion": desc,
            "porcentaje": round((cnt / denom) * 100.0, 1),
            "hectareas": round(cnt * cell_ha, 1),
        }
    return dist


def _compute_spatial_crosstabs(
    macro_grid: np.ndarray,
    slope_north_up: np.ndarray,
    dem: np.ndarray,
    cell_ha: float,
    schema: str,
    lc_source_label: str,
) -> Dict[str, Any]:
    """
    Construye la matriz de tabulación cruzada Cobertura x Pendiente (píxel a píxel)
    e indicadores espaciales de exposición agronómica, forestal, urbana e interfaz (IUF).
    """
    total_cells = macro_grid.size
    sin_datos_id = MACRO_CLASS_META["sin_datos"]["id"]
    agua_id = MACRO_CLASS_META["agua"]["id"]
    bosque_id = MACRO_CLASS_META["bosque"]["id"]
    matorral_id = MACRO_CLASS_META["matorral"]["id"]
    pastizal_id = MACRO_CLASS_META["pastizal"]["id"]
    cultivo_id = MACRO_CLASS_META["cultivo"]["id"]
    urbano_id = MACRO_CLASS_META["urbano"]["id"]
    suelo_id = MACRO_CLASS_META["suelo_desnudo"]["id"]
    humedal_id = MACRO_CLASS_META["humedal"]["id"]
    nieve_id = MACRO_CLASS_META["nieve_hielo"]["id"]
    veg_ndvi_id = MACRO_CLASS_META["vegetacion_indiferenciada"]["id"]

    valid_mask = macro_grid != sin_datos_id
    water_mask = macro_grid == agua_id
    terrestrial_mask = valid_mask & (~water_mask)

    valid_count = int(np.sum(valid_mask))
    water_count = int(np.sum(water_mask))
    terr_count = int(np.sum(terrestrial_mask))

    water_ha = round(water_count * cell_ha, 1)
    terr_ha = round(terr_count * cell_ha, 1)
    valid_ha = round(max(1, valid_count) * cell_ha, 1)

    matriz: Dict[str, Dict[str, Any]] = {}
    unique_ids = [int(v) for v in np.unique(macro_grid) if int(v) != sin_datos_id]

    for m_id in unique_ids:
        m_key = MACRO_ID_TO_KEY.get(m_id)
        if not m_key:
            continue
        meta = MACRO_CLASS_META[m_key]
        class_mask = macro_grid == m_id
        cnt = int(np.sum(class_mask))
        ha_cls = round(cnt * cell_ha, 1)
        pct_area = round((cnt / max(1, valid_count)) * 100.0, 2)
        pct_terr = round((cnt / max(1, terr_count)) * 100.0, 2) if m_id != agua_id and terr_count > 0 else 0.0

        por_rango: Dict[str, Dict[str, Any]] = {}
        if m_id == agua_id:
            slope_mean_cls = 0.0
            slope_max_cls = 0.0
            ha_baja = ha_cls
            ha_mod_mas = 0.0
            ha_fuerte_mas = 0.0
            ha_muy_fuerte_mas = 0.0
            ha_extrema = 0.0
        else:
            s_vals = slope_north_up[class_mask]
            slope_mean_cls = round(float(np.mean(s_vals)), 2) if s_vals.size else 0.0
            slope_max_cls = round(float(np.max(s_vals)), 2) if s_vals.size else 0.0
            for b_key, b_nombre, _b_short, _b_col, low, high, _desc in SLOPE_BINS:
                if math.isinf(high):
                    b_mask = class_mask & (slope_north_up >= low)
                else:
                    b_mask = class_mask & (slope_north_up >= low) & (slope_north_up < high)
                b_cnt = int(np.sum(b_mask))
                por_rango[b_key] = {
                    "nombre": b_nombre,
                    "hectareas": round(b_cnt * cell_ha, 1),
                    "porcentaje_clase": round((b_cnt / max(1, cnt)) * 100.0, 1),
                    "porcentaje_area": round((b_cnt / max(1, valid_count)) * 100.0, 2),
                }
            ha_baja = round(int(np.sum(class_mask & (slope_north_up < 3.0))) * cell_ha, 1)
            ha_mod_mas = round(int(np.sum(class_mask & (slope_north_up >= 3.0))) * cell_ha, 1)
            ha_fuerte_mas = round(int(np.sum(class_mask & (slope_north_up >= 8.0))) * cell_ha, 1)
            ha_muy_fuerte_mas = round(int(np.sum(class_mask & (slope_north_up >= 15.0))) * cell_ha, 1)
            ha_extrema = round(int(np.sum(class_mask & (slope_north_up >= 30.0))) * cell_ha, 1)

        matriz[m_key] = {
            "macro_clase": m_key,
            "nombre": meta["nombre"],
            "color_hex": meta["color"],
            "hectareas": ha_cls,
            "porcentaje_area": pct_area,
            "porcentaje_terrestre": pct_terr,
            "pendiente_media_pct": slope_mean_cls,
            "pendiente_max_pct": slope_max_cls,
            "ha_pendiente_baja_menor_3pct": ha_baja,
            "ha_pendiente_moderada_mas_3pct": ha_mod_mas,
            "ha_pendiente_fuerte_mas_8pct": ha_fuerte_mas,
            "ha_pendiente_muy_fuerte_mas_15pct": ha_muy_fuerte_mas,
            "ha_pendiente_extrema_30pct": ha_extrema,
            "por_rango_pendiente": por_rango,
        }

    def _get_ha(k: str, field: str = "hectareas") -> float:
        return float(matriz.get(k, {}).get(field, 0.0))

    # Indicadores espaciales compuestos y acoplamiento Urbano-Forestal (IUF)
    urbano_mask = macro_grid == urbano_id
    bosque_mat_fuerte_mask = ((macro_grid == bosque_id) | (macro_grid == matorral_id)) & (slope_north_up >= 8.0)
    bosque_mat_muy_fuerte_mask = ((macro_grid == bosque_id) | (macro_grid == matorral_id)) & (slope_north_up >= 15.0)

    interfaz_urbano_forestal_ha = 0.0
    elev_media_urbano = None
    elev_media_bosque_pendiente = None
    urbano_aguas_abajo_de_laderas = False

    if urbano_mask.any():
        elev_media_urbano = round(float(np.mean(dem[urbano_mask])), 1)
    if bosque_mat_muy_fuerte_mask.any():
        elev_media_bosque_pendiente = round(float(np.mean(dem[bosque_mat_muy_fuerte_mask])), 1)

    if urbano_mask.any() and bosque_mat_fuerte_mask.any():
        near_urbano = _binary_dilation_2d(urbano_mask, radius_px=5)  # ~150 m alrededor de la trama urbana
        near_forest_slope = _binary_dilation_2d(bosque_mat_fuerte_mask, radius_px=5)
        iuf_forest = bosque_mat_fuerte_mask & near_urbano
        iuf_urbano = urbano_mask & near_forest_slope
        interfaz_urbano_forestal_ha = round(int(np.sum(iuf_forest) + np.sum(iuf_urbano)) * cell_ha, 1)

    if elev_media_urbano is not None and elev_media_bosque_pendiente is not None:
        urbano_aguas_abajo_de_laderas = elev_media_bosque_pendiente > (elev_media_urbano + 10.0)
    elif urbano_mask.any() and int(np.sum(terrestrial_mask & (slope_north_up >= 15.0))) > 0:
        steep_mask = terrestrial_mask & (slope_north_up >= 15.0)
        elev_steep = float(np.mean(dem[steep_mask]))
        urbano_aguas_abajo_de_laderas = elev_steep > (float(np.mean(dem[urbano_mask])) + 10.0)

    urbano_ha = _get_ha("urbano")
    urbano_ladera_ha = _get_ha("urbano", "ha_pendiente_fuerte_mas_8pct")
    urbano_critica_ha = _get_ha("urbano", "ha_pendiente_muy_fuerte_mas_15pct")
    urbano_valle_ha = round(max(0.0, urbano_ha - urbano_ladera_ha), 1)

    indicadores = {
        "superficie_terrestre_ha": terr_ha,
        "agua_enmascarada_ha": water_ha,
        "agua_enmascarada_pct": round((water_count / max(1, total_cells)) * 100.0, 2),
        "bosque_total_ha": _get_ha("bosque"),
        "matorral_total_ha": _get_ha("matorral"),
        "pastizal_total_ha": _get_ha("pastizal"),
        "cultivo_total_ha": _get_ha("cultivo"),
        "urbano_total_ha": urbano_ha,
        "suelo_desnudo_total_ha": _get_ha("suelo_desnudo"),
        "humedal_total_ha": _get_ha("humedal"),
        "nieve_hielo_total_ha": _get_ha("nieve_hielo"),
        "vegetacion_ndvi_total_ha": _get_ha("vegetacion_indiferenciada"),
        "cultivo_en_pendiente_moderada_mas_ha": _get_ha("cultivo", "ha_pendiente_moderada_mas_3pct"),
        "cultivo_en_pendiente_fuerte_mas_ha": _get_ha("cultivo", "ha_pendiente_fuerte_mas_8pct"),
        "suelo_desnudo_en_pendiente_fuerte_ha": _get_ha("suelo_desnudo", "ha_pendiente_fuerte_mas_8pct"),
        "bosque_en_pendiente_fuerte_ha": _get_ha("bosque", "ha_pendiente_fuerte_mas_8pct"),
        "bosque_en_pendiente_muy_fuerte_ha": _get_ha("bosque", "ha_pendiente_muy_fuerte_mas_15pct"),
        "bosque_en_escarpe_ha": _get_ha("bosque", "ha_pendiente_extrema_30pct"),
        "bosque_y_matorral_en_pendiente_fuerte_ha": round(
            _get_ha("bosque", "ha_pendiente_fuerte_mas_8pct") + _get_ha("matorral", "ha_pendiente_fuerte_mas_8pct"), 1
        ),
        "bosque_y_matorral_en_pendiente_muy_fuerte_ha": round(
            _get_ha("bosque", "ha_pendiente_muy_fuerte_mas_15pct")
            + _get_ha("matorral", "ha_pendiente_muy_fuerte_mas_15pct"),
            1,
        ),
        "urbano_en_valle_ha": urbano_valle_ha,
        "urbano_en_ladera_fuerte_ha": urbano_ladera_ha,
        "urbano_en_pendiente_critica_ha": urbano_critica_ha,
        "elev_media_urbano_msnm": elev_media_urbano,
        "elev_media_bosque_pendiente_msnm": elev_media_bosque_pendiente,
        "urbano_aguas_abajo_de_laderas": urbano_aguas_abajo_de_laderas,
        "interfaz_urbano_forestal_ha": interfaz_urbano_forestal_ha,
    }

    return {
        "disponible": True,
        "fuente_cobertura": lc_source_label,
        "esquema_semantico": schema,
        "superficie_valida_ha": valid_ha,
        "superficie_terrestre_ha": terr_ha,
        "agua_enmascarada_ha": water_ha,
        "agua_enmascarada_pct": indicadores["agua_enmascarada_pct"],
        "matriz_cobertura_pendiente": matriz,
        "indicadores_cruce": indicadores,
    }


def _build_territorial_diagnosis(
    cruce: Dict[str, Any],
    distribucion_pendientes: Dict[str, Dict[str, Any]],
    slope_mean_terr: float,
    rumbo_predominante: str,
) -> Dict[str, Any]:
    """
    Determina el Régimen Territorial dominante a partir del cruce Cobertura x Pendiente
    y construye módulos de diagnóstico y recomendaciones pertinentes por dominio.
    """
    nota_legal = (
        "Tamizaje geoespacial orientativo (coberturas satelitales globales 10m + DEM 30m). "
        "Para zonificación legal vinculante contrastar con el Ordenamiento Territorial de Bosques Nativos (OTBN - Ley 26.331), "
        "jurisdicción de Parques Nacionales y códigos de planeamiento urbano municipales."
    )

    if not cruce.get("disponible"):
        fuerte_mas = (
            distribucion_pendientes["fuerte_8_a_15pct"]["porcentaje"]
            + distribucion_pendientes["muy_fuerte_15_a_30pct"]["porcentaje"]
            + distribucion_pendientes["extrema_mayor_30pct"]["porcentaje"]
        )
        return {
            "regimen_territorial": "Diagnóstico Topográfico Sin Cobertura Semántica",
            "codigo_regimen": "sin_cobertura",
            "etiqueta_riesgo_principal": "Energía Potencial de Escurrimiento Topográfico",
            "nivel_riesgo_principal": "Alto" if (slope_mean_terr > 8.0 or fuerte_mas > 15.0) else "Moderado a Bajo",
            "resumen_diagnostico": (
                f"Pendiente media de {slope_mean_terr}% ({fuerte_mas:.1f}% en laderas > 8%). "
                "No se dispuso de capa de uso del suelo para discriminar si la pendiente corresponde a bosque protector, sector urbano o cultivo."
            ),
            "modulos_activos": [
                {
                    "dominio": "Requerimiento de Clasificación de Cobertura",
                    "nivel": "Informativo",
                    "color": "#475569",
                    "hallazgo": "El relieve muestra gradiente topográfico, pero las recomendaciones de manejo dependen de la cobertura real del suelo.",
                    "recomendaciones": "Ejecutá primero 'Clasificar Coberturas' (ESA WorldCover o Esri LULC) para activar el cruce espacial y recomendaciones territoriales específicas.",
                }
            ],
            "nota_alcance_regulatorio": nota_legal,
        }

    ind = cruce["indicadores_cruce"]
    schema = cruce.get("esquema_semantico", "esa-worldcover")
    terr_ha = max(0.1, float(ind["superficie_terrestre_ha"]))

    # Caso especial: clasificación por umbralización NDVI (solo Vegetación / Suelo / Agua)
    if schema == "sentinel2-ndvi":
        veg_ha = ind["vegetacion_ndvi_total_ha"]
        suelo_ha = ind["suelo_desnudo_total_ha"]
        suelo_fuerte_ha = ind["suelo_desnudo_en_pendiente_fuerte_ha"]
        ladera_fuerte_pct = (
            distribucion_pendientes["fuerte_8_a_15pct"]["porcentaje"]
            + distribucion_pendientes["muy_fuerte_15_a_30pct"]["porcentaje"]
            + distribucion_pendientes["extrema_mayor_30pct"]["porcentaje"]
        )
        nivel = "Alto" if (suelo_fuerte_ha >= 5.0 or (slope_mean_terr > 12.0 and suelo_ha > 0.1 * terr_ha)) else (
            "Moderado" if slope_mean_terr > 3.0 else "Bajo"
        )
        return {
            "regimen_territorial": "Cruce Biofísico NDVI × Pendiente (Sin desagregación semántica)",
            "codigo_regimen": "ndvi_sin_semantica",
            "etiqueta_riesgo_principal": "Exposición de Suelo Sin Vigor Vegetativo vs. Relieve",
            "nivel_riesgo_principal": nivel,
            "resumen_diagnostico": (
                f"La umbralización NDVI identifica {veg_ha:,.1f} ha con vegetación activa y {suelo_ha:,.1f} ha de suelo desnudo/superficie no vegetada "
                f"({suelo_fuerte_ha:,.1f} ha en pendiente ≥ 8%). Dado que NDVI no distingue bosque nativo de cultivos ni área urbana de roca/barbecho, "
                "no se emiten prescripciones agronómicas automáticas sobre laderas."
            ),
            "modulos_activos": [
                {
                    "dominio": "Análisis Biofísico Preliminar (NDVI × Pendiente)",
                    "nivel": nivel,
                    "color": "#0284c7",
                    "hallazgo": (
                        f"Suelo/superficie no vegetada en laderas ≥ 8%: {suelo_fuerte_ha:,.1f} ha. "
                        f"Sectores con pendiente > 8%: {ladera_fuerte_pct:.1f}% del área terrestre."
                    ),
                    "recomendaciones": (
                        "Ejecutá ESA WorldCover 10m o Esri Annual LULC para separar bosque nativo, trama urbana y lotes agrícolas "
                        "antes de definir prácticas de manejo agronómico, forestal o de drenaje urbano."
                    ),
                }
            ],
            "nota_alcance_regulatorio": nota_legal,
        }

    # Porcentajes sobre superficie terrestre (excluye cuerpos de agua)
    bosque_ha = ind["bosque_total_ha"]
    matorral_ha = ind["matorral_total_ha"]
    lenoso_ha = bosque_ha + matorral_ha
    pastizal_ha = ind["pastizal_total_ha"]
    cultivo_ha = ind["cultivo_total_ha"]
    urbano_ha = ind["urbano_total_ha"]
    suelo_ha = ind["suelo_desnudo_total_ha"]
    humedal_ha = ind["humedal_total_ha"]
    nieve_ha = ind["nieve_hielo_total_ha"]

    pct_lenoso = (lenoso_ha / terr_ha) * 100.0
    pct_cultivo = (cultivo_ha / terr_ha) * 100.0
    pct_urbano = (urbano_ha / terr_ha) * 100.0
    pct_pastizal = (pastizal_ha / terr_ha) * 100.0
    pct_humedal = (humedal_ha / terr_ha) * 100.0
    pct_suelo = (suelo_ha / terr_ha) * 100.0
    pct_nieve = (nieve_ha / terr_ha) * 100.0

    pct_ladera_fuerte = (
        distribucion_pendientes["fuerte_8_a_15pct"]["porcentaje"]
        + distribucion_pendientes["muy_fuerte_15_a_30pct"]["porcentaje"]
        + distribucion_pendientes["extrema_mayor_30pct"]["porcentaje"]
    )
    pct_ladera_muy_fuerte = (
        distribucion_pendientes["muy_fuerte_15_a_30pct"]["porcentaje"]
        + distribucion_pendientes["extrema_mayor_30pct"]["porcentaje"]
    )

    # 1. Clasificación del Régimen Territorial
    if pct_cultivo >= 15.0 and pct_lenoso < 20.0 and pct_urbano < 10.0:
        codigo_regimen = "agropecuario"
        regimen_territorial = "Matriz Agropecuaria"
    elif (pct_cultivo + pct_pastizal) >= 55.0 and pct_cultivo >= 10.0 and pct_lenoso < 20.0 and pct_urbano < 10.0:
        codigo_regimen = "agropecuario"
        regimen_territorial = "Matriz Agropecuaria Mixta (Cultivos y Pastizales)"
    elif pct_cultivo >= 5.0 and (pct_lenoso >= 15.0 or pct_urbano >= 5.0 or pct_ladera_muy_fuerte >= 20.0):
        codigo_regimen = "mixto_agro_territorial"
        regimen_territorial = "Paisaje Mixto (Uso Agrícola, Forestal y/o Periurbano)"
    elif pct_lenoso >= 25.0 and (pct_urbano >= 2.0 or urbano_ha >= 5.0) and (pct_ladera_fuerte >= 20.0 or slope_mean_terr >= 8.0):
        codigo_regimen = "forestal_iuf_montana"
        regimen_territorial = "Cuenca Forestal de Montaña e Interfaz Urbano-Forestal"
    elif pct_lenoso >= 25.0 and (pct_ladera_fuerte >= 20.0 or slope_mean_terr >= 8.0):
        codigo_regimen = "forestal_cuenca"
        regimen_territorial = "Cuenca Forestal de Ladera / Protección Hídrica"
    elif pct_lenoso >= 25.0:
        codigo_regimen = "forestal_llanura"
        regimen_territorial = "Matriz Forestal de Llanura / Monte Nativo"
    elif pct_urbano >= 10.0:
        codigo_regimen = "urbano_piedemonte"
        regimen_territorial = (
            "Área Urbana / Periurbana en Pie de Monte o Ladera"
            if (pct_ladera_fuerte >= 15.0 or slope_mean_terr >= 5.0)
            else "Área Urbana / Periurbana en Planicie"
        )
    elif pct_humedal >= 25.0 or (ind["agua_enmascarada_pct"] >= 40.0 and slope_mean_terr < 3.0):
        codigo_regimen = "humedal_planicie"
        regimen_territorial = "Sistema Hídrico / Humedal y Planicie Fluvial"
    else:
        codigo_regimen = "estepario_montana"
        regimen_territorial = (
            "Estepa / Matorral de Ladera o Alta Montaña"
            if (pct_ladera_fuerte >= 20.0 or slope_mean_terr >= 8.0 or pct_nieve > 1.0)
            else "Pastizal Natural / Estepa de Relieve Suave"
        )

    # 2. Activación de Módulos de Diagnóstico pertinentes por dominio
    modulos: List[Dict[str, Any]] = []

    # Módulo A: Protección de Cuencas y Bosque Nativo
    if lenoso_ha >= 5.0 or pct_lenoso >= 10.0:
        lenoso_fuerte = ind["bosque_y_matorral_en_pendiente_fuerte_ha"]
        lenoso_muy_fuerte = ind["bosque_y_matorral_en_pendiente_muy_fuerte_ha"]
        bosque_escarpe = ind["bosque_en_escarpe_ha"]

        if lenoso_muy_fuerte >= 5.0 or lenoso_fuerte >= 10.0:
            nivel_b = "Estratégico (Prioridad de Conservación)"
            hallazgo_b = (
                f"Se registran {lenoso_ha:,.1f} ha de cobertura leñosa/arbórea ({pct_lenoso:.1f}% terrestre), de las cuales "
                f"{lenoso_fuerte:,.1f} ha se emplazan en pendientes ≥ 8% y {lenoso_muy_fuerte:,.1f} ha en laderas escarpadas ≥ 15% "
                f"({bosque_escarpe:,.1f} ha en escarpes > 30%)."
            )
            recom_b = (
                "Preservar la continuidad del dosel boscoso como infraestructura verde protectora de cabecera de cuenca y reguladora de crecidas. "
                "La combinación de bosque nativo con fuertes pendientes y aporte hídrico coincide con criterios de alto valor de conservación de la Ley N.° 26.331 (OTBN — Categorías I Rojo / II Amarillo), "
                "por lo que no corresponde remoción de cobertura ni laboreo agrícola."
            )
        else:
            nivel_b = "Conservación de Cobertura Nativa"
            hallazgo_b = (
                f"Masa forestal/arbustiva de {lenoso_ha:,.1f} ha ({pct_lenoso:.1f}% terrestre) sobre relieve predominantemente plano a suave "
                f"(pendiente media terrestre {slope_mean_terr}%)."
            )
            recom_b = (
                "Mantener la conectividad del bosque nativo y su rol en la infiltración pluvial y control freático bajo lineamientos del OTBN (Ley N.° 26.331); "
                "vigilar anegamientos temporales en bajos (< 1%) y evitar fragmentación en fajas de drenaje natural."
            )

        modulos.append({
            "dominio": "Protección de Cuencas y Bosques Nativos",
            "nivel": nivel_b,
            "color": "#15803d",
            "hallazgo": hallazgo_b,
            "recomendaciones": recom_b,
        })

    # Módulo B: Riesgo Hídrico Urbano / Aluvional y Pie de Monte
    if urbano_ha >= 2.0 or pct_urbano >= 2.0:
        urb_valle = ind["urbano_en_valle_ha"]
        urb_ladera = ind["urbano_en_ladera_fuerte_ha"]
        urb_critica = ind["urbano_en_pendiente_critica_ha"]
        aguas_abajo = ind["urbano_aguas_abajo_de_laderas"]

        if aguas_abajo or urb_critica >= 2.0 or urb_ladera >= 10.0:
            nivel_u = "Alto"
        elif urb_ladera >= 2.0 or pct_ladera_fuerte >= 15.0:
            nivel_u = "Moderado"
        else:
            nivel_u = "Bajo a Moderado"

        detalles_u = [
            f"Área urbana/construida total: {urbano_ha:,.1f} ha ({pct_urbano:.1f}% terrestre), con {urb_valle:,.1f} ha en fondo de valle/pendiente < 8%"
        ]
        if urb_ladera > 0:
            detalles_u.append(f"{urb_ladera:,.1f} ha sobre laderas fuertes ≥ 8% ({urb_critica:,.1f} ha en ≥ 15%)")
        if aguas_abajo and ind["elev_media_urbano_msnm"] is not None and ind["elev_media_bosque_pendiente_msnm"] is not None:
            detalles_u.append(
                f"emplazada aguas abajo (cota media urbana {ind['elev_media_urbano_msnm']} msnm frente a {ind['elev_media_bosque_pendiente_msnm']} msnm en laderas ≥ 15%)"
            )

        recom_u = (
            "Dimensionar drenajes pluviales e infraestructura verde (parques de retención, pavimentos permeables, resguardo de cauces y conos aluviales) "
            f"considerando el escurrimiento convergente con rumbo {rumbo_predominante}. "
            "Restringir urbanización sobre laderas > 15%, estabilizar taludes viales y mantener el bosque aguas arriba para amortiguar aluviones y sedimentación hacia cuerpos de agua."
            if (aguas_abajo or urb_ladera > 0 or pct_ladera_fuerte >= 15.0)
            else "Controlar escurrimiento pluvial urbano, preservar áreas verdes absorbentes y evitar ocupación de bajos anegables (< 1%)."
        )

        modulos.append({
            "dominio": "Riesgo Hídrico Urbano, Pluvial y Aluvional",
            "nivel": nivel_u,
            "color": "#dc2626" if nivel_u == "Alto" else "#d97706",
            "hallazgo": ", ".join(detalles_u) + ".",
            "recomendaciones": recom_u,
        })

    # Módulo C: Interfaz Urbano-Forestal (IUF) — requiere contacto real significativo con laderas leñosas
    iuf_ha = ind["interfaz_urbano_forestal_ha"]
    if (
        (iuf_ha >= 5.0 and (ind["bosque_y_matorral_en_pendiente_muy_fuerte_ha"] >= 5.0 or ind["bosque_y_matorral_en_pendiente_fuerte_ha"] >= 15.0))
        or (urbano_ha >= 5.0 and ind["bosque_y_matorral_en_pendiente_muy_fuerte_ha"] >= 15.0)
    ):
        nivel_iuf = "Alto" if ind["bosque_y_matorral_en_pendiente_muy_fuerte_ha"] >= 10.0 else "Moderado"
        modulos.append({
            "dominio": "Interfaz Urbano-Forestal (IUF) y Riesgo Post-Incendio",
            "nivel": nivel_iuf,
            "color": "#b45309",
            "hallazgo": (
                f"Zona de contacto directo entre trama construida y laderas boscosas/arbustivas (≥ 8%): ~{iuf_ha:,.1f} ha de interfaz activa "
                f"(con {ind['bosque_y_matorral_en_pendiente_muy_fuerte_ha']:,.1f} ha de masa leñosa en pendientes ≥ 15%)."
            ),
            "recomendaciones": (
                "Priorizar planes de prevención de incendios en interfaz urbano-forestal (Ley N.° 26.815), fajas cortafuego y manejo de combustible: "
                "el fuego asciende aceleradamente en laderas fuertes y la pérdida post-incendio de cobertura vegetal dispara escorrentía torrencial y deslizamientos sobre el área urbana."
            ),
        })

    # Módulo D: Manejo Conservacionista Agrícola (SOLO si existen cultivos reales o barbecho cultivable)
    cult_mod = ind["cultivo_en_pendiente_moderada_mas_ha"]
    cult_fuerte = ind["cultivo_en_pendiente_fuerte_mas_ha"]
    if cultivo_ha >= 2.0 or pct_cultivo >= 2.0:
        pct_cult_en_mod = (cult_mod / max(0.1, cultivo_ha)) * 100.0
        pct_cult_en_fuerte = (cult_fuerte / max(0.1, cultivo_ha)) * 100.0
        if cult_fuerte >= 5.0 or pct_cult_en_fuerte >= 10.0:
            nivel_a = "Alto a Severo (en superficie cultivada)"
            recom_a = (
                "En las parcelas cultivadas sobre pendiente (≥ 8%), reconvertir a pasturas permanentes o agroforestería, "
                "e implementar en lotes de 3–8% siembra en contorno, terrazas de absorción/desagüe y fajas de amortiguación."
            )
        elif cult_mod >= 5.0 or pct_cult_en_mod >= 15.0:
            nivel_a = "Moderado (en superficie cultivada)"
            recom_a = (
                "Implementar siembra directa, cobertura continua de rastrojos, rotación con gramíneas y orientación de surcos perpendicular a la pendiente en el sector agrícola."
            )
        else:
            nivel_a = "Bajo (Cultivos en relieve plano a suave)"
            recom_a = (
                "Los sectores agrícolas se ubican sobre pendientes < 3%; mantener cobertura de rastrojos y vigilar drenaje superficial en bajos (< 1%)."
            )

        modulos.append({
            "dominio": "Manejo Conservacionista Agrícola (Cultivos × Pendiente)",
            "nivel": nivel_a,
            "color": "#2563eb",
            "hallazgo": (
                f"Superficie cultivada: {cultivo_ha:,.1f} ha ({pct_cultivo:.1f}% terrestre), de las cuales "
                f"{cult_mod:,.1f} ha ({pct_cult_en_mod:.1f}% del cultivo) presentan pendiente ≥ 3% y "
                f"{cult_fuerte:,.1f} ha ({pct_cult_en_fuerte:.1f}%) superan el 8%."
            ),
            "recomendaciones": recom_a,
        })

    # Módulo E: Fragilidad de Estepa / Pastizal / Alta Montaña (cuando no es agrícola intensivo ni bosque cerrado)
    if (
        (pct_pastizal + pct_suelo + pct_nieve) >= 20.0
        and pct_cultivo < 10.0
        and (pct_ladera_fuerte >= 15.0 or codigo_regimen == "estepario_montana")
    ):
        suelo_fuerte = ind["suelo_desnudo_en_pendiente_fuerte_ha"]
        nivel_e = "Alto" if (suelo_fuerte >= 10.0 or pct_ladera_muy_fuerte >= 25.0) else "Moderado"
        modulos.append({
            "dominio": "Fragilidad de Estepa, Pastizal y Laderas Desnudas",
            "nivel": nivel_e,
            "color": "#78716c",
            "hallazgo": (
                f"Pastizal/estepa: {pastizal_ha:,.1f} ha | Suelo desnudo/roca: {suelo_ha:,.1f} ha "
                f"({suelo_fuerte:,.1f} ha en pendiente ≥ 8%)"
                + (f" | Nieve/hielo: {nieve_ha:,.1f} ha." if nieve_ha > 0 else ".")
            ),
            "recomendaciones": (
                "Ajustar carga animal/pastoreo para sostener cobertura herbácea y arbustiva protectora en laderas, "
                "evitar apertura de picadas sin desagües transversales y controlar inicio de cárcavas en suelos frágiles de piedemonte o deshielo."
            ),
        })

    # Módulo F: Humedales / Planicie
    if humedal_ha >= 5.0 or pct_humedal >= 10.0:
        modulos.append({
            "dominio": "Humedales y Regulación Hidrológica de Planicie",
            "nivel": "Estratégico",
            "color": "#0891b2",
            "hallazgo": f"Se identifican {humedal_ha:,.1f} ha de humedales/vegetación inundable ({pct_humedal:.1f}% terrestre) y {ind['agua_enmascarada_ha']:,.1f} ha de cuerpos de agua.",
            "recomendaciones": "Preservar la dinámica natural de pulso hídrico y evitar canalizaciones o rellenos que reduzcan la capacidad de laminación de crecidas.",
        })

    # Fallback defensivo si ningún módulo superó umbrales mínimos
    if not modulos:
        modulos.append({
            "dominio": "Diagnóstico Hidro-Territorial General",
            "nivel": "Bajo a Moderado",
            "color": "#2563eb",
            "hallazgo": f"Pendiente media terrestre de {slope_mean_terr}% sobre matriz mixta sin predominio crítico de un único uso.",
            "recomendaciones": "Mantener cobertura vegetal en sectores con pendiente ≥ 3% y resguardar vías de escurrimiento natural.",
        })

    # Determinar etiqueta y nivel principal del diagnóstico según el régimen
    etiqueta_map = {
        "forestal_iuf_montana": "Susceptibilidad Hidrológica en Cuenca de Montaña e Interfaz Urbano-Forestal",
        "forestal_cuenca": "Rol Protector de Bosques y Regulación Hidrológica de Cuenca",
        "forestal_llanura": "Dinámica Hídrica en Matriz Forestal de Llanura (Monte Nativo)",
        "urbano_piedemonte": "Riesgo Hídrico-Aluvional y Pluvial en Área Urbana / Periurbana",
        "agropecuario": "Evaluación de Riesgo de Erosión Hídrica en Sectores Productivos",
        "mixto_agro_territorial": "Riesgo Hidro-Territorial Diferenciado (Agrícola / Forestal / Urbano)",
        "humedal_planicie": "Dinámica de Humedales y Anegamiento en Planicie Hídrica",
        "estepario_montana": "Susceptibilidad Torrencial y Degradación en Estepa / Montaña",
    }
    etiqueta_principal = etiqueta_map.get(codigo_regimen, "Evaluación de Riesgo Hidro-Territorial")

    # Nivel principal coherente con los módulos activos
    niveles = [m["nivel"] for m in modulos]
    if any("Alto" in n or "Severo" in n for n in niveles):
        nivel_principal = "Alto (ver desglose por uso del suelo)"
    elif any("Estratégico" in n for n in niveles):
        nivel_principal = "Estratégico — Protección de Cuencas y Cobertura Nativa"
    elif any("Moderado" in n for n in niveles):
        nivel_principal = "Moderado (condicionado por uso y pendiente)"
    else:
        nivel_principal = "Bajo"

    resumen_diag = (
        f"Régimen detectado: {regimen_territorial}. "
        + " ".join(m["hallazgo"] for m in modulos[:2])
    )

    return {
        "regimen_territorial": regimen_territorial,
        "codigo_regimen": codigo_regimen,
        "etiqueta_riesgo_principal": etiqueta_principal,
        "nivel_riesgo_principal": nivel_principal,
        "resumen_diagnostico": resumen_diag,
        "modulos_activos": modulos,
        "nota_alcance_regulatorio": nota_legal,
    }


def _generate_spatial_cross_figure(
    macro_grid: np.ndarray,
    slope_north_up: np.ndarray,
    cruce: Dict[str, Any],
    real_geo_bounds: Tuple[float, float, float, float],
    target_bbox: List[float],
) -> Optional[str]:
    """
    Genera una cartografía temática dual del cruce espacial:
    - Panel izquierdo: Zonificación Funcional Hidro-Territorial (Cobertura x Pendiente).
    - Panel derecho: Barras horizontales apiladas de superficie (ha) por Cobertura y Rango de Pendiente.
    """
    if not cruce.get("disponible"):
        return None

    r_min_lon, r_min_lat, r_max_lon, r_max_lat = real_geo_bounds
    h, w = macro_grid.shape

    sin_datos_id = MACRO_CLASS_META["sin_datos"]["id"]
    agua_id = MACRO_CLASS_META["agua"]["id"]
    humedal_id = MACRO_CLASS_META["humedal"]["id"]
    bosque_id = MACRO_CLASS_META["bosque"]["id"]
    matorral_id = MACRO_CLASS_META["matorral"]["id"]
    urbano_id = MACRO_CLASS_META["urbano"]["id"]
    cultivo_id = MACRO_CLASS_META["cultivo"]["id"]
    suelo_id = MACRO_CLASS_META["suelo_desnudo"]["id"]
    veg_ndvi_id = MACRO_CLASS_META["vegetacion_indiferenciada"]["id"]

    # Categorías funcionales para el mapa izquierdo
    # 0: Otras coberturas / relieve bajo-moderado (<8%)
    # 1: Bosque / Matorral Protector en Ladera (>=15%)
    # 2: Bosque / Matorral en Pendiente Moderada/Baja (<15%)
    # 3: Área Urbana en Valle / Pendiente Baja (<8%)
    # 4: Área Urbana en Ladera Fuerte (>=8%)
    # 5: Cultivos en Pendiente Erosiva (>=3%)
    # 6: Cultivos en Relieve Plano/Suave (<3%)
    # 7: Suelo Desnudo / Roca en Ladera (>=8%)
    # 8: Cuerpos de Agua / Humedales
    # 9: Vegetación Activa (NDVI) en Ladera (>=8%)
    func_grid = np.zeros((h, w), dtype=np.uint8)
    woody_mask = (macro_grid == bosque_id) | (macro_grid == matorral_id)
    func_grid[woody_mask & (slope_north_up < 15.0)] = 2
    func_grid[woody_mask & (slope_north_up >= 15.0)] = 1
    func_grid[(macro_grid == veg_ndvi_id) & (slope_north_up < 8.0)] = 2
    func_grid[(macro_grid == veg_ndvi_id) & (slope_north_up >= 8.0)] = 9
    func_grid[(macro_grid == urbano_id) & (slope_north_up < 8.0)] = 3
    func_grid[(macro_grid == urbano_id) & (slope_north_up >= 8.0)] = 4
    func_grid[(macro_grid == cultivo_id) & (slope_north_up < 3.0)] = 6
    func_grid[(macro_grid == cultivo_id) & (slope_north_up >= 3.0)] = 5
    func_grid[(macro_grid == suelo_id) & (slope_north_up >= 8.0)] = 7
    func_grid[(macro_grid == agua_id) | (macro_grid == humedal_id)] = 8
    func_grid[macro_grid == sin_datos_id] = 0

    func_palette = {
        0: ("Pastizal / Estepa / Otras (< 8%)", "#e2e8f0"),
        1: ("Bosque / Matorral Protector (Pend. ≥ 15%)", "#14532d"),
        2: ("Bosque / Veg. en Pendiente < 15%", "#4ade80"),
        3: ("Área Urbana en Valle / Pend. < 8%", "#f97316"),
        4: ("Área Urbana en Ladera Fuerte (≥ 8%)", "#991b1b"),
        5: ("Cultivos en Pendiente Erosiva (≥ 3%)", "#9333ea"),
        6: ("Cultivos en Relieve Plano/Suave (< 3%)", "#f0abfc"),
        7: ("Suelo Desnudo / Pastizal en Ladera (≥ 8%)", "#78716c"),
        8: ("Cuerpos de Agua / Humedales", "#1d4ed8"),
        9: ("Vegetación NDVI en Ladera (≥ 8%)", "#15803d"),
    }
    pastizal_id = MACRO_CLASS_META["pastizal"]["id"]
    func_grid[(macro_grid == pastizal_id) & (slope_north_up >= 8.0)] = 7

    colors_list = [func_palette[i][1] for i in range(10)]
    cmap_func = matplotlib.colors.ListedColormap(colors_list)
    norm_func = matplotlib.colors.BoundaryNorm([i - 0.5 for i in range(11)], cmap_func.N)

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 6.6), dpi=150, gridspec_kw={"width_ratios": [1.15, 1.0]})

    ax1.imshow(
        func_grid,
        extent=[r_min_lon, r_max_lon, r_min_lat, r_max_lat],
        cmap=cmap_func,
        norm=norm_func,
        origin="upper",
        interpolation="nearest",
    )
    present_ids = [int(v) for v in np.unique(func_grid)]
    patches = [
        mpatches.Patch(color=func_palette[idx][1], label=func_palette[idx][0])
        for idx in [1, 2, 9, 3, 4, 5, 6, 7, 8, 0]
        if idx in present_ids
    ]
    ax1.legend(handles=patches, loc="upper right", framealpha=0.92, fontsize=7.8, title="Zonificación Funcional")
    ax1.set_title(
        "Cruce Espacial: Zonificación Funcional Hidro-Territorial\n"
        f"Fuente: {cruce.get('fuente_cobertura', 'Cobertura 10m')}",
        fontsize=9.8,
        fontweight="bold",
    )
    ax1.set_xlabel("Longitud (°)")
    ax1.set_ylabel("Latitud (°)")

    # Panel derecho: Barras apiladas Cobertura x Rango de Pendiente (ha)
    matriz = cruce.get("matriz_cobertura_pendiente", {})
    sorted_classes = sorted(matriz.values(), key=lambda x: x["hectareas"], reverse=True)
    # Limitar a clases con >= 0.5 ha o top 8 para claridad visual
    plot_classes = [c for c in sorted_classes if c["hectareas"] >= 0.1][:8]

    if plot_classes:
        y_labels = [c["nombre"].split("(")[0].strip() for c in plot_classes][::-1]
        y_pos = np.arange(len(y_labels))
        left_acc = np.zeros(len(y_labels))

        for b_key, _b_nom, b_short, b_color, _l, _h, _d in SLOPE_BINS:
            vals = np.array([
                c["por_rango_pendiente"].get(b_key, {}).get("hectareas", 0.0)
                for c in reversed(plot_classes)
            ])
            if np.any(vals > 0):
                ax2.barh(y_pos, vals, left=left_acc, color=b_color, edgecolor="#334155", linewidth=0.35, label=b_short)
                left_acc += vals

        # Agua (sin rango de pendiente terrestre)
        water_vals = np.array([
            c["hectareas"] if c["macro_clase"] == "agua" else 0.0
            for c in reversed(plot_classes)
        ])
        if np.any(water_vals > 0):
            ax2.barh(y_pos, water_vals, left=left_acc, color="#1e40af", edgecolor="#334155", linewidth=0.35, label="Cuerpo de Agua")
            left_acc += water_vals

        for idx_bar, total_bar in enumerate(left_acc):
            ax2.text(
                total_bar + max(left_acc) * 0.015,
                idx_bar,
                f"{total_bar:,.1f} ha",
                va="center",
                fontsize=8,
                color="#1e293b",
                fontweight="bold",
            )

        ax2.set_yticks(y_pos)
        ax2.set_yticklabels(y_labels, fontsize=8.8)
        ax2.set_xlim(0, max(left_acc) * 1.18 if max(left_acc) > 0 else 10)
        ax2.set_xlabel("Superficie (hectáreas)")
        ax2.set_title(
            "Distribución de Superficie por Cobertura y Rango de Pendiente",
            fontsize=9.8,
            fontweight="bold",
        )
        ax2.legend(loc="lower right", framealpha=0.92, fontsize=8, title="Pendiente / Agua")
        ax2.grid(axis="x", linestyle="--", alpha=0.4)
    else:
        ax2.text(0.5, 0.5, "Sin clases suficientes para graficar", ha="center", va="center")
        ax2.axis("off")

    plt.tight_layout()
    tag = _bbox_tag(target_bbox)
    cross_filename = f"mapa_cruce_territorial_{tag}.png"
    cross_path = OUTPUTS_DIR / cross_filename
    plt.savefig(cross_path, dpi=150, bbox_inches="tight")
    plt.close()
    return str(cross_path)


def analyze_drainage_and_slope(
    bbox: List[float] = None,
    classification_context: Optional[Dict[str, Any]] = None,
    auto_fetch_landcover: bool = True,
) -> Dict[str, Any]:
    """
    Descarga el Modelo Digital de Elevación (DEM 30m) para el Bounding Box solicitado,
    calcula la red de líneas de drenaje superficial, pendiente, dirección de flujo y ejecuta
    el cruce espacial píxel a píxel con la cobertura del suelo (enmascarando cuerpos de agua)
    para emitir un diagnóstico territorial multi-dominio.
    """
    target_bbox = bbox or DEFAULT_BBOX
    catalog = get_stac_catalog()

    # Búsqueda en colecciones DEM (Copernicus DEM 30m o NASADEM como alternativa)
    search = catalog.search(
        collections=["cop-dem-glo-30"],
        bbox=target_bbox,
        max_items=6,
    )
    items = list(search.items())
    if not items:
        search = catalog.search(
            collections=["nasadem"],
            bbox=target_bbox,
            max_items=6,
        )
        items = list(search.items())
        if not items:
            raise ValueError(f"No se encontró cobertura DEM en el catálogo para el área {target_bbox}.")

    raster_env = rasterio.Env(
        GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR",
        CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif",
        VSI_CACHE=True,
    )

    dem = None
    real_geo_bounds = None
    folium_bounds = None
    dem_crs = None
    dem_transform = None

    with raster_env:
        last_err = None
        for item_cand in items:
            dem_asset_key = "data" if "data" in item_cand.assets else list(item_cand.assets.keys())[0]
            dem_url = item_cand.assets[dem_asset_key].href
            try:
                with rasterio.open(dem_url) as src:
                    native_bounds = transform_bounds("EPSG:4326", src.crs, *target_bbox)
                    raw_window = from_bounds(*native_bounds, transform=src.transform)
                    img_window = rasterio.windows.Window(0, 0, src.width, src.height)
                    valid_window = raw_window.intersection(img_window).round_lengths().round_offsets()

                    if valid_window.width <= 0 or valid_window.height <= 0:
                        continue

                    dem = src.read(1, window=valid_window).astype("float32")
                    dem_crs = src.crs
                    dem_transform = window_transform_fn(valid_window, src.transform)

                    w_native_bounds = window_bounds_fn(valid_window, src.transform)
                    real_geo_bounds = transform_bounds(src.crs, "EPSG:4326", *w_native_bounds)
                    folium_bounds = [
                        [real_geo_bounds[1], real_geo_bounds[0]],  # South, West
                        [real_geo_bounds[3], real_geo_bounds[2]],  # North, East
                    ]
                    break
            except rasterio.errors.WindowError as we:
                last_err = we
                continue

        if dem is None or real_geo_bounds is None or dem_transform is None:
            raise ValueError(
                "El recuadro seleccionado queda fuera de los límites del DEM."
                + (f" ({last_err})" if last_err else "")
            )

    # Reemplazar valores no válidos (NoData) si existiesen
    dem = np.where((dem < -500) | (dem > 9000), np.nan, dem)
    if np.isnan(dem).all():
        raise ValueError("El DEM obtenido contiene únicamente valores nulos.")

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

    # Pendiente en porcentaje (%) (orientación Sur-arriba para streamplot, y Norte-arriba para cruce espacial)
    slope_pct = np.sqrt(gx**2 + gy**2) * 100.0
    slope_north_up = np.flipud(slope_pct)

    # Vectores de escurrimiento superficial hacia abajo del gradiente
    u_flow = -gx
    v_flow = -gy

    # Estadísticas de Elevación
    elev_min = round(float(np.min(dem)), 1)
    elev_max = round(float(np.max(dem)), 1)
    elev_mean = round(float(np.mean(dem)), 1)
    desnivel_m = round(elev_max - elev_min, 1)

    total_cells = dem.size
    cell_ha = (dy_m * dx_m) / 10000.0
    total_ha = round(total_cells * cell_ha, 1)

    # Dirección media del escurrimiento
    mean_u = float(np.mean(u_flow))
    mean_v = float(np.mean(v_flow))
    mean_azimuth = (math.degrees(math.atan2(mean_u, mean_v)) + 360.0) % 360.0
    rumbo_predominante = azimuth_to_compass(mean_azimuth)

    # -------------------------------------------------------------
    # RESOLUCIÓN DE COBERTURA Y CRUCE ESPACIAL PÍXEL A PÍXEL
    # -------------------------------------------------------------
    lc_ctx, lc_source_label = _resolve_landcover_for_cross(
        bbox=target_bbox,
        classification_context=classification_context,
        auto_fetch_landcover=auto_fetch_landcover,
    )

    macro_grid = None
    schema = "esa-worldcover"
    if lc_ctx and lc_ctx.get("raster_cache_path") and os.path.exists(lc_ctx["raster_cache_path"]):
        schema = _infer_schema_from_context(lc_ctx)
        candidate_macro = _align_landcover_to_dem(
            raster_cache_path=lc_ctx["raster_cache_path"],
            schema=schema,
            dem_shape=(h, w),
            dem_transform=dem_transform,
            dem_crs=dem_crs,
        )
        sin_datos_id = MACRO_CLASS_META["sin_datos"]["id"]
        if candidate_macro is not None and np.sum(candidate_macro != sin_datos_id) >= 0.05 * total_cells:
            macro_grid = candidate_macro

    # Máscara terrestre (excluye cuerpos de agua y sin datos si hay cruce disponible)
    agua_id = MACRO_CLASS_META["agua"]["id"]
    sin_datos_id = MACRO_CLASS_META["sin_datos"]["id"]
    if macro_grid is not None:
        water_mask = macro_grid == agua_id
        terrestrial_mask = (macro_grid != agua_id) & (macro_grid != sin_datos_id)
        if not terrestrial_mask.any():
            terrestrial_mask = np.ones((h, w), dtype=bool)
            water_mask = np.zeros((h, w), dtype=bool)
    else:
        water_mask = np.zeros((h, w), dtype=bool)
        terrestrial_mask = np.ones((h, w), dtype=bool)

    terr_slopes = slope_north_up[terrestrial_mask]
    slope_mean = round(float(np.mean(terr_slopes)), 2)
    slope_max = round(float(np.max(terr_slopes)), 2)
    slope_median = round(float(np.median(terr_slopes)), 2)
    slope_mean_global = round(float(np.mean(slope_north_up)), 2)

    distribucion_pendientes = _compute_slope_distribution(
        slope_north_up=slope_north_up,
        terrestrial_mask=terrestrial_mask,
        cell_ha=cell_ha,
    )

    if macro_grid is not None:
        cruce_espacial = _compute_spatial_crosstabs(
            macro_grid=macro_grid,
            slope_north_up=slope_north_up,
            dem=dem,
            cell_ha=cell_ha,
            schema=schema,
            lc_source_label=lc_source_label,
        )
    else:
        cruce_espacial = {
            "disponible": False,
            "fuente_cobertura": lc_source_label,
            "superficie_terrestre_ha": total_ha,
            "agua_enmascarada_ha": 0.0,
            "agua_enmascarada_pct": 0.0,
            "matriz_cobertura_pendiente": {},
            "indicadores_cruce": {},
        }

    diagnostico_territorial = _build_territorial_diagnosis(
        cruce=cruce_espacial,
        distribucion_pendientes=distribucion_pendientes,
        slope_mean_terr=slope_mean,
        rumbo_predominante=rumbo_predominante,
    )

    # Compatibilidad retroactiva de analisis_agrohidrologico (ahora contextualizado al uso real)
    modulos_texto = " | ".join(
        f"[{m['dominio']}] {m['recomendaciones']}"
        for m in diagnostico_territorial.get("modulos_activos", [])
    )
    analisis_agrohidrologico = {
        "riesgo_erosion_hidrica": (
            f"{diagnostico_territorial['etiqueta_riesgo_principal']}: "
            f"{diagnostico_territorial['nivel_riesgo_principal']}"
        ),
        "recomendacion_conservacion": modulos_texto or diagnostico_territorial.get("resumen_diagnostico", ""),
        "regimen_territorial": diagnostico_territorial["regimen_territorial"],
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

    mag = np.sqrt(u_sub**2 + v_sub**2)
    if np.max(mag) < 1e-7:
        u_sub = u_sub + 1e-6

    # -------------------------------------------------------------
    # 1. MAPA TEMÁTICO DE DRENAJE Y ZONIFICACIÓN DE PENDIENTES (PNG)
    # -------------------------------------------------------------
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 7.2), dpi=150, gridspec_kw={"width_ratios": [1.2, 1]})

    ax1.imshow(hillshade, extent=[r_min_lon, r_max_lon, r_min_lat, r_max_lat], cmap="gray", origin="upper", alpha=0.6)
    im_elev = ax1.imshow(dem, extent=[r_min_lon, r_max_lon, r_min_lat, r_max_lat], cmap="terrain", origin="upper", alpha=0.65)

    strm = ax1.streamplot(
        x_grid,
        y_grid,
        u_sub,
        v_sub,
        color=slope_sub,
        cmap="plasma",
        density=1.4,
        linewidth=1.5,
        arrowsize=1.3,
        arrowstyle="->",
        norm=Normalize(vmin=0, vmax=max(5.0, float(np.percentile(slope_pct, 95)))),
    )
    ax1.set_xlim(r_min_lon, r_max_lon)
    ax1.set_ylim(r_min_lat, r_max_lat)

    cbar1 = fig.colorbar(strm.lines, ax=ax1, fraction=0.038, pad=0.03)
    cbar1.set_label("Pendiente Flujo (%)", fontsize=8.5, fontweight="bold")

    cbar_elev = fig.colorbar(im_elev, ax=ax1, fraction=0.038, pad=0.06)
    cbar_elev.set_label("Elevación (m.s.n.m.)", fontsize=8.5)

    ax1.set_title(
        "Red de Drenaje Hídrico Superficial y Dirección de Flujo\n"
        f"Rumbo Predominante: {rumbo_predominante} ({round(mean_azimuth, 1)}°) | Desnivel: {desnivel_m} m",
        fontsize=10,
        fontweight="bold",
    )
    ax1.set_xlabel("Longitud (°)")
    ax1.set_ylabel("Latitud (°)")

    # Subplot 2: Clasificación de Pendientes Terrestres (6 rangos) + Cuerpos de Agua enmascarados
    slope_img = np.zeros(dem.shape, dtype=np.uint8)
    non_water_mask = ~water_mask
    for idx_bin, (_k, _nom, _short, _col, low, high, _desc) in enumerate(SLOPE_BINS):
        if math.isinf(high):
            b_mask = non_water_mask & (slope_north_up >= low)
        else:
            b_mask = non_water_mask & (slope_north_up >= low) & (slope_north_up < high)
        slope_img[b_mask] = idx_bin
    has_water = bool(water_mask.any())
    if has_water:
        slope_img[water_mask] = 6

    slope_colors = [b[3] for b in SLOPE_BINS] + ["#1e40af"]
    cmap_slopes = matplotlib.colors.ListedColormap(slope_colors)
    norm_slopes = matplotlib.colors.BoundaryNorm([-0.5, 0.5, 1.5, 2.5, 3.5, 4.5, 5.5, 6.5], cmap_slopes.N)

    ax2.imshow(
        slope_img,
        extent=[r_min_lon, r_max_lon, r_min_lat, r_max_lat],
        cmap=cmap_slopes,
        norm=norm_slopes,
        origin="upper",
        interpolation="nearest",
        alpha=0.92,
    )

    legend_patches = [
        mpatches.Patch(
            color=b_col,
            label=f"{b_short} ({distribucion_pendientes[b_key]['porcentaje']}%)",
        )
        for b_key, _b_nom, b_short, b_col, _l, _h, _d in SLOPE_BINS
    ]
    if has_water:
        legend_patches.append(
            mpatches.Patch(
                color="#1e40af",
                label=f"Cuerpo de Agua ({cruce_espacial['agua_enmascarada_pct']}% excl.)",
            )
        )
    ax2.legend(handles=legend_patches, loc="upper right", framealpha=0.92, fontsize=8.0, title="Rangos de Pendiente")
    ax2.set_title(
        "Zonificación de Pendientes Terrestres e Hidro-Susceptibilidad\n"
        f"Pendiente Media Terrestre: {slope_mean}% | Máxima: {slope_max}%",
        fontsize=10,
        fontweight="bold",
    )
    ax2.set_xlabel("Longitud (°)")
    ax2.set_ylabel("Latitud (°)")

    plt.tight_layout()
    tag = _bbox_tag(target_bbox)
    output_filename = f"mapa_drenaje_hidrico_{tag}.png"
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

    ax_ov.streamplot(
        x_grid,
        y_grid,
        u_sub,
        v_sub,
        color=slope_sub,
        cmap="autumn",
        density=1.6,
        linewidth=2.0,
        arrowsize=1.5,
        arrowstyle="->",
        norm=Normalize(vmin=0, vmax=max(4.0, float(np.percentile(slope_pct, 95)))),
    )
    ax_ov.set_xlim(r_min_lon, r_max_lon)
    ax_ov.set_ylim(r_min_lat, r_max_lat)

    overlay_filename = f"overlay_drenaje_hidrico_{tag}.png"
    overlay_path = OUTPUTS_DIR / overlay_filename
    fig_ov.savefig(overlay_path, transparent=True, dpi=150)
    plt.close()

    # -------------------------------------------------------------
    # 3. CARTOGRAFÍA Y GRÁFICO DEL CRUCE ESPACIAL COBERTURA x PENDIENTE
    # -------------------------------------------------------------
    mapa_cruce_path = None
    if macro_grid is not None and cruce_espacial.get("disponible"):
        mapa_cruce_path = _generate_spatial_cross_figure(
            macro_grid=macro_grid,
            slope_north_up=slope_north_up,
            cruce=cruce_espacial,
            real_geo_bounds=real_geo_bounds,
            target_bbox=target_bbox,
        )

    # Resumen Ejecutivo integrado
    agua_note = (
        f" (Terrestre: {cruce_espacial['superficie_terrestre_ha']:,.1f} ha | Agua enmascarada: {cruce_espacial['agua_enmascarada_ha']:,.1f} ha)"
        if has_water
        else ""
    )
    resumen_text = (
        f"🌊 **Diagnóstico Hidro-Territorial y Cruce Espacial (Copernicus DEM 30m):**\n"
        f"• **Superficie Analizada:** {total_ha:,.1f} ha{agua_note} | **Desnivel:** {desnivel_m} m ({elev_min} a {elev_max} m.s.n.m.)\n"
        f"• **Pendiente Terrestre:** Media {slope_mean}% | Máxima {slope_max}% | Mediana {slope_median}%\n"
        f"• **Dirección Predominante de Escurrimiento:** {rumbo_predominante} (Acimut: {round(mean_azimuth, 1)}°)\n"
        f"• **Régimen Territorial:** {diagnostico_territorial['regimen_territorial']}\n"
        f"• **Fuente de Cobertura (Cruce):** {cruce_espacial.get('fuente_cobertura')}\n"
        f"• **{diagnostico_territorial['etiqueta_riesgo_principal']}:** {diagnostico_territorial['nivel_riesgo_principal']}"
    )

    return {
        "status": "success",
        "tipo_analisis": "Red de Drenaje Hídrico Superficial, Pendientes y Cruce Espacial Cobertura x Pendiente",
        "fuente_dem": "Copernicus DEM 30m GLO-30 (ESA / Microsoft Planetary Computer)",
        "superficie_total_ha": total_ha,
        "superficie_terrestre_ha": cruce_espacial.get("superficie_terrestre_ha", total_ha),
        "agua_enmascarada_ha": cruce_espacial.get("agua_enmascarada_ha", 0.0),
        "elevacion": {
            "minima_msnm": elev_min,
            "maxima_msnm": elev_max,
            "media_msnm": elev_mean,
            "desnivel_m": desnivel_m,
        },
        "pendientes": {
            "media_pct": slope_mean,
            "media_global_sin_mascara_pct": slope_mean_global,
            "maxima_pct": slope_max,
            "mediana_pct": slope_median,
            "distribucion": distribucion_pendientes,
        },
        "direccion_flujo": {
            "acimut_grados": round(mean_azimuth, 1),
            "rumbo_cardinal": rumbo_predominante,
            "componentes": {"u_mean": round(mean_u, 4), "v_mean": round(mean_v, 4)},
        },
        "cruce_espacial": cruce_espacial,
        "diagnostico_territorial": diagnostico_territorial,
        "analisis_agrohidrologico": analisis_agrohidrologico,
        "mapa_generado": str(output_path),
        "mapa_cruce_generado": mapa_cruce_path,
        "overlay_generado": str(overlay_path),
        "folium_bounds": folium_bounds,
        "ubicacion_administrativa": get_location_for_bbox(target_bbox),
        "resumen_ejecutivo": resumen_text,
    }
