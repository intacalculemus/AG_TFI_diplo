"""
Servicio de Integración del Ordenamiento Territorial de Bosques Nativos (OTBN - Ley N.° 26.331)
Consumo en vivo vía servicios estándar OGC (WMS GetMap + GetFeatureInfo) de la Subsecretaría de Ambiente
de la Nación / Sistema Nacional de Monitoreo de Bosques (SNMB: geo.ambiente.gob.ar).

Incluye:
1. Descarga por recorte espacial (BBox) sin antialiasing (colores discretos exactos del SLD oficial)
2. Consulta de atributos jurídicos por categoría presente (Provincia, Fecha de Norma/Decreto, Autoridad)
3. Cruce espacial píxel a píxel Cobertura del Suelo (10m) x Categoría OTBN (Rojo I / Amarillo II / Verde III)
4. Generación de overlay transparente para Folium, caché .npz y cartografía analítica comparativa
"""
import hashlib
import io
import json
import math
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional, Tuple

import matplotlib
matplotlib.use("Agg")
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import numpy as np
from PIL import Image
from rasterio.transform import Affine, from_bounds as transform_from_bounds
from rasterio.warp import Resampling, reproject

from config import OUTPUTS_DIR
from services.geo_admin_service import get_location_for_bbox
from services.real_satellite_service import (
    DEFAULT_BBOX,
    MACRO_CLASS_META,
    MACRO_ID_TO_KEY,
    estimate_bbox_dimensions,
    fetch_landcover_reference_for_bbox,
    map_code_grid_to_macro_ids,
)

OTBN_WMS_URL = "https://geo.ambiente.gob.ar/geoserver/bosques/wms"
OTBN_LAYER_NAME = "bosques:otbn_nacional"

# Colores exactos definidos en el SLD oficial de GeoServer para bosques:otbn_nacional
OTBN_CATEGORIES: Dict[int, Dict[str, Any]] = {
    0: {
        "code": 0,
        "cam": "Sin OTBN",
        "name": "Sin categoría OTBN (No boscoso / No zonificado)",
        "short_name": "Sin OTBN",
        "color": "#94a3b8",
        "rgb": (148, 163, 184),
        "sld_rgb": None,
        "alpha": 0,
        "descripcion": "Sectores sin cobertura asignada a categorías I, II o III en la capa nacional.",
    },
    1: {
        "code": 1,
        "cam": "I",
        "name": "Categoría I (Rojo — Muy alto valor de conservación)",
        "short_name": "Cat. I (Rojo)",
        "color": "#f10000",
        "rgb": (241, 0, 0),
        "sld_rgb": (241, 0, 0),
        "alpha": 175,
        "descripcion": "No deben transformarse ni someterse a aprovechamiento maderero; preservación estricta.",
    },
    2: {
        "code": 2,
        "cam": "II",
        "name": "Categoría II (Amarillo — Mediano valor de conservación)",
        "short_name": "Cat. II (Amarillo)",
        "color": "#eff60b",
        "rgb": (239, 246, 11),
        "sld_rgb": (239, 246, 11),
        "alpha": 175,
        "descripcion": "No admiten desmonte; habilitados para aprovechamiento sostenible, turismo e investigación.",
    },
    3: {
        "code": 3,
        "cam": "III",
        "name": "Categoría III (Verde — Bajo valor de conservación)",
        "short_name": "Cat. III (Verde)",
        "color": "#299516",
        "rgb": (41, 149, 22),
        "sld_rgb": (41, 149, 22),
        "alpha": 175,
        "descripcion": "Pueden transformarse parcialmente o en su totalidad previa Evaluación de Impacto Ambiental.",
    },
}


def _bbox_tag(bbox: List[float]) -> str:
    norm = ",".join(f"{float(v):.4f}" for v in bbox)
    return hashlib.sha1(norm.encode("utf-8")).hexdigest()[:8]


def _infer_lc_schema(ctx: Dict[str, Any]) -> str:
    explicit = ctx.get("raster_schema") or ctx.get("coleccion_stac")
    if explicit in ("esa-worldcover", "io-lulc-annual-v02", "sentinel2-ndvi"):
        return explicit
    modelo = str(ctx.get("modelo", "")).lower()
    if "lulc" in modelo or "esri" in modelo:
        return "io-lulc-annual-v02"
    if "ndvi" in modelo or "radiom" in modelo:
        return "sentinel2-ndvi"
    return "esa-worldcover"


def _compute_wms_dimensions(bbox: List[float], max_dim: int = 1024, min_dim: int = 128) -> Tuple[int, int]:
    """Calcula dimensiones en píxeles preservando la relación de aspecto métrica del BBox."""
    dim_info = estimate_bbox_dimensions(bbox, res_m=10.0)
    w_m = max(100.0, float(dim_info["ancho_m"]))
    h_m = max(100.0, float(dim_info["alto_m"]))
    w_px = int(round(w_m / 10.0))
    h_px = int(round(h_m / 10.0))

    scale_down = max(w_px, h_px) / float(max_dim)
    if scale_down > 1.0:
        w_px = int(round(w_px / scale_down))
        h_px = int(round(h_px / scale_down))

    w_px = max(min_dim, min(max_dim, w_px))
    h_px = max(min_dim, min(max_dim, h_px))
    return w_px, h_px


def _decode_otbn_rgba_to_grid(rgba: np.ndarray) -> np.ndarray:
    """
    Decodifica una imagen RGBA devuelta por GeoServer (format_options=antialias:none)
    a códigos discretos: 0=Sin OTBN, 1=Cat I (Rojo), 2=Cat II (Amarillo), 3=Cat III (Verde).
    """
    h, w, _ = rgba.shape
    grid = np.zeros((h, w), dtype=np.uint8)
    alpha = rgba[:, :, 3]
    opaque_mask = alpha >= 128
    if not opaque_mask.any():
        return grid

    rgb = rgba[:, :, :3].astype(np.int32)
    matched = np.zeros((h, w), dtype=bool)

    # Coincidencia exacta con los colores SLD oficiales
    for cat_id in (1, 2, 3):
        sr, sg, sb = OTBN_CATEGORIES[cat_id]["sld_rgb"]
        exact = opaque_mask & (rgb[:, :, 0] == sr) & (rgb[:, :, 1] == sg) & (rgb[:, :, 2] == sb)
        grid[exact] = cat_id
        matched |= exact

    # Respaldo por distancia euclidiana mínima para eventuales píxeles opacos no exactos
    unmatched = opaque_mask & (~matched)
    if unmatched.any():
        pts = rgb[unmatched]  # shape (N, 3)
        palette = np.array([OTBN_CATEGORIES[k]["sld_rgb"] for k in (1, 2, 3)], dtype=np.int32)
        dists = np.sum((pts[:, None, :] - palette[None, :, :]) ** 2, axis=2)
        nearest_idx = np.argmin(dists, axis=1) + 1  # 1, 2 o 3
        grid[unmatched] = nearest_idx.astype(np.uint8)

    return grid


def _fetch_wms_otbn_image(
    bbox: List[float],
    width: int,
    height: int,
    timeout: float = 18.0,
) -> np.ndarray:
    """Descarga el recorte OTBN vía WMS GetMap sin antialiasing (PNG 24/32 bits)."""
    min_lon, min_lat, max_lon, max_lat = [float(x) for x in bbox]
    params = {
        "SERVICE": "WMS",
        "VERSION": "1.1.1",
        "REQUEST": "GetMap",
        "LAYERS": OTBN_LAYER_NAME,
        "STYLES": "",
        "SRS": "EPSG:4326",
        "BBOX": f"{min_lon},{min_lat},{max_lon},{max_lat}",
        "WIDTH": str(width),
        "HEIGHT": str(height),
        "FORMAT": "image/png",
        "TRANSPARENT": "TRUE",
        "format_options": "antialias:none",
    }
    url = f"{OTBN_WMS_URL}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "TFI-Diplo-ISBIA/1.0 (OTBN Integration)"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        content_type = str(resp.headers.get("Content-Type", "")).lower()
        raw = resp.read()
        if "image/png" not in content_type:
            snippet = raw[:400].decode("utf-8", errors="replace")
            raise RuntimeError(f"GeoServer WMS no devolvió PNG ({content_type}): {snippet}")
        img = Image.open(io.BytesIO(raw)).convert("RGBA")
        return np.array(img, dtype=np.uint8)


def _fetch_wms_feature_info_at_pixel(
    bbox: List[float],
    width: int,
    height: int,
    px_x: int,
    px_y: int,
    timeout: float = 8.0,
) -> Optional[Dict[str, Any]]:
    """Consulta atributos legales (provincia, decreto, organismo) vía WMS GetFeatureInfo."""
    min_lon, min_lat, max_lon, max_lat = [float(x) for x in bbox]
    params = {
        "SERVICE": "WMS",
        "VERSION": "1.1.1",
        "REQUEST": "GetFeatureInfo",
        "LAYERS": OTBN_LAYER_NAME,
        "QUERY_LAYERS": OTBN_LAYER_NAME,
        "SRS": "EPSG:4326",
        "BBOX": f"{min_lon},{min_lat},{max_lon},{max_lat}",
        "WIDTH": str(width),
        "HEIGHT": str(height),
        "X": str(int(px_x)),
        "Y": str(int(px_y)),
        "INFO_FORMAT": "application/json",
        "FEATURE_COUNT": "3",
    }
    url = f"{OTBN_WMS_URL}?{urllib.parse.urlencode(params)}"
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "TFI-Diplo-ISBIA/1.0 (OTBN FeatureInfo)"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
            feats = payload.get("features") or []
            if not feats:
                return None
            return feats[0].get("properties")
    except Exception:
        return None


def _collect_legal_metadata(
    otbn_grid: np.ndarray,
    bbox: List[float],
    width: int,
    height: int,
) -> Dict[str, Any]:
    """Muestrea 1 píxel representativo por cada categoría OTBN presente para obtener provincia, fecha y autoridad."""
    sample_tasks: List[Tuple[int, int, int]] = []
    for cat_id in (1, 2, 3):
        ys, xs = np.where(otbn_grid == cat_id)
        if len(ys) > 0:
            mid = len(ys) // 2
            sample_tasks.append((cat_id, int(xs[mid]), int(ys[mid])))

    if not sample_tasks:
        return {"provincias": [], "fechas_norma": [], "autoridades": [], "por_categoria": {}}

    results: Dict[str, Any] = {}
    provs = set()
    dates = set()
    auths = set()

    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {
            cat_id: executor.submit(_fetch_wms_feature_info_at_pixel, bbox, width, height, px_x, px_y)
            for cat_id, px_x, px_y in sample_tasks
        }
        for cat_id, fut in futures.items():
            props = fut.result()
            if props:
                prov = props.get("fna")
                dct = str(props.get("dct") or "").replace("Z", "").strip()
                sag = props.get("sag")
                cam = props.get("cam") or OTBN_CATEGORIES[cat_id]["cam"]
                if prov:
                    provs.add(str(prov))
                if dct:
                    dates.add(dct)
                if sag:
                    auths.add(str(sag))
                results[cam] = {
                    "provincia": prov,
                    "fecha_norma_dct": dct or None,
                    "autoridad_sag": sag,
                }

    return {
        "provincias": sorted(provs),
        "fechas_norma": sorted(dates),
        "autoridades": sorted(auths),
        "por_categoria": results,
    }


def _resolve_landcover_context(
    bbox: List[float],
    classification_context: Optional[Dict[str, Any]],
    auto_fetch_landcover: bool,
) -> Tuple[Optional[Dict[str, Any]], str]:
    """Reutiliza la clasificación activa (.npz) o descarga referencia ESA WorldCover / Esri LULC 10m."""
    if classification_context and isinstance(classification_context, dict):
        cache_path = classification_context.get("raster_cache_path")
        if cache_path and cache_path != "None":
            try:
                with np.load(cache_path, allow_pickle=False) as _:
                    pass
                fecha_lbl = (
                    classification_context.get("año_referencia")
                    or classification_context.get("fecha_analizada")
                    or ""
                )
                label = f"{classification_context.get('modelo', 'Clasificación Activa')} ({fecha_lbl}) — Clasificación activa".strip()
                return classification_context, label
            except Exception:
                pass

    if auto_fetch_landcover:
        ref = fetch_landcover_reference_for_bbox(bbox)
        if ref and ref.get("raster_cache_path"):
            fecha_lbl = ref.get("año_referencia") or "2021"
            label = f"{ref.get('modelo', 'ESA WorldCover 10m')} ({fecha_lbl}) — Referencia automática"
            return ref, label

    return None, "Sin cobertura satelital disponible"


def _cross_landcover_with_otbn(
    otbn_grid: np.ndarray,
    otbn_transform: Affine,
    lc_ctx: Dict[str, Any],
    lc_source_label: str,
) -> Optional[Dict[str, Any]]:
    """
    Reproyecta la grilla OTBN (EPSG:4326) a la grilla exacta de cobertura 10m (UTM/WGS84)
    mediante vecino más cercano y calcula la matriz cuantitativa Cobertura x Categoría OTBN.
    """
    cache_path = lc_ctx.get("raster_cache_path")
    if not cache_path:
        return None

    schema = _infer_lc_schema(lc_ctx)

    try:
        with np.load(cache_path, allow_pickle=False) as npz:
            lc_grid = npz["grid"].astype(np.uint8)
            tf_vals = npz["transform"]
            crs_raw = npz["crs"]
            lc_crs_str = str(crs_raw.item() if crs_raw.ndim == 0 else crs_raw)
    except Exception:
        return None

    dst_transform = Affine(*[float(x) for x in tf_vals[:6]])
    h, w = lc_grid.shape
    otbn_aligned = np.zeros((h, w), dtype=np.uint8)

    reproject(
        source=otbn_grid,
        destination=otbn_aligned,
        src_transform=otbn_transform,
        src_crs="EPSG:4326",
        dst_transform=dst_transform,
        dst_crs=lc_crs_str,
        resampling=Resampling.nearest,
    )

    macro_grid = map_code_grid_to_macro_ids(lc_grid, schema)

    # Área métrica exacta por píxel según CRS de la clasificación
    real_geo_bounds = (lc_ctx.get("coordenadas_exactas_raster") or {}).get("geo_bounds_reales")
    if "4326" in lc_crs_str and real_geo_bounds and len(real_geo_bounds) == 4:
        r_min_lon, r_min_lat, r_max_lon, r_max_lat = real_geo_bounds
        mid_lat = (r_min_lat + r_max_lat) / 2.0
        dy_m = ((r_max_lat - r_min_lat) / max(1, h)) * 111320.0
        dx_m = ((r_max_lon - r_min_lon) / max(1, w)) * 111320.0 * math.cos(math.radians(mid_lat))
        cell_ha = (dy_m * dx_m) / 10000.0
    else:
        cell_ha = abs(float(tf_vals[0]) * float(tf_vals[4])) / 10000.0
        if cell_ha <= 0:
            cell_ha = 0.01

    sin_datos_id = MACRO_CLASS_META["sin_datos"]["id"]
    valid_mask = macro_grid != sin_datos_id
    valid_px = int(valid_mask.sum())
    if valid_px == 0:
        return None

    total_ha = round(valid_px * cell_ha, 1)
    matriz: Dict[str, Dict[str, Any]] = {}

    for macro_id in np.unique(macro_grid[valid_mask]):
        m_id = int(macro_id)
        m_key = MACRO_ID_TO_KEY.get(m_id, "sin_datos")
        m_meta = MACRO_CLASS_META[m_key]
        c_mask = macro_grid == m_id
        c_px = int(c_mask.sum())
        c_ha = round(c_px * cell_ha, 1)

        por_otbn: Dict[str, Dict[str, Any]] = {}
        for cat_id in (1, 2, 3, 0):
            cat_meta = OTBN_CATEGORIES[cat_id]
            inter_px = int(np.sum(c_mask & (otbn_aligned == cat_id)))
            inter_ha = round(inter_px * cell_ha, 1)
            por_otbn[cat_meta["cam"]] = {
                "categoria_id": cat_id,
                "nombre": cat_meta["short_name"],
                "hectareas": inter_ha,
                "porcentaje_de_cobertura": round((inter_px / max(1, c_px)) * 100.0, 1),
            }

        matriz[m_key] = {
            "macro_clase": m_key,
            "nombre": m_meta["nombre"],
            "color": m_meta["color"],
            "hectareas": c_ha,
            "porcentaje_area": round((c_px / valid_px) * 100.0, 2),
            "por_otbn": por_otbn,
        }

    def _get_inter_ha(macro_key: str, cam_key: str) -> float:
        return float(matriz.get(macro_key, {}).get("por_otbn", {}).get(cam_key, {}).get("hectareas", 0.0))

    bosque_en_rojo = _get_inter_ha("bosque", "I")
    bosque_en_amarillo = _get_inter_ha("bosque", "II")
    bosque_en_verde = _get_inter_ha("bosque", "III")
    bosque_sin_otbn = _get_inter_ha("bosque", "Sin OTBN")

    lenoso_en_rojo = round(bosque_en_rojo + _get_inter_ha("matorral", "I"), 1)
    lenoso_en_amarillo = round(bosque_en_amarillo + _get_inter_ha("matorral", "II"), 1)
    lenoso_en_verde = round(bosque_en_verde + _get_inter_ha("matorral", "III"), 1)

    cultivo_en_rojo = _get_inter_ha("cultivo", "I")
    cultivo_en_amarillo = _get_inter_ha("cultivo", "II")
    suelo_en_rojo = _get_inter_ha("suelo_desnudo", "I")
    suelo_en_amarillo = _get_inter_ha("suelo_desnudo", "II")
    urbano_en_rojo_amarillo = round(_get_inter_ha("urbano", "I") + _get_inter_ha("urbano", "II"), 1)

    # Distribución OTBN calculada sobre la misma grilla alineada de 10m
    otbn_dist_aligned: Dict[str, Dict[str, Any]] = {}
    for cat_id in (1, 2, 3, 0):
        cat_meta = OTBN_CATEGORIES[cat_id]
        cat_px = int(np.sum(valid_mask & (otbn_aligned == cat_id)))
        otbn_dist_aligned[cat_meta["cam"]] = {
            "codigo": cat_id,
            "cam": cat_meta["cam"],
            "nombre": cat_meta["name"],
            "short_name": cat_meta["short_name"],
            "color": cat_meta["color"],
            "hectareas": round(cat_px * cell_ha, 1),
            "porcentaje": round((cat_px / valid_px) * 100.0, 2),
        }

    indicadores = {
        "superficie_analizada_ha": total_ha,
        "bosque_en_rojo_I_ha": bosque_en_rojo,
        "bosque_en_amarillo_II_ha": bosque_en_amarillo,
        "bosque_en_verde_III_ha": bosque_en_verde,
        "bosque_sin_otbn_ha": bosque_sin_otbn,
        "lenoso_en_rojo_I_ha": lenoso_en_rojo,
        "lenoso_en_amarillo_II_ha": lenoso_en_amarillo,
        "lenoso_en_verde_III_ha": lenoso_en_verde,
        "cultivo_en_rojo_I_ha": cultivo_en_rojo,
        "cultivo_en_amarillo_II_ha": cultivo_en_amarillo,
        "suelo_desnudo_en_rojo_I_ha": suelo_en_rojo,
        "suelo_desnudo_en_amarillo_II_ha": suelo_en_amarillo,
        "urbano_en_rojo_o_amarillo_ha": urbano_en_rojo_amarillo,
        "presion_productiva_en_rojo_I_ha": round(cultivo_en_rojo + suelo_en_rojo, 1),
        "presion_productiva_en_amarillo_II_ha": round(cultivo_en_amarillo + suelo_en_amarillo, 1),
    }

    return {
        "disponible": True,
        "fuente_cobertura": lc_source_label,
        "esquema_semantico": schema,
        "superficie_total_ha": total_ha,
        "distribucion_otbn_alineada": otbn_dist_aligned,
        "matriz_cobertura_otbn": matriz,
        "indicadores_cruce": indicadores,
    }


def _build_otbn_diagnosis(
    otbn_dist: Dict[str, Dict[str, Any]],
    cruce: Dict[str, Any],
    legal_meta: Dict[str, Any],
) -> Dict[str, Any]:
    """Genera diagnóstico normativo-territorial orientativo a partir del OTBN y su cruce con coberturas."""
    ha_i = otbn_dist["I"]["hectareas"]
    ha_ii = otbn_dist["II"]["hectareas"]
    ha_iii = otbn_dist["III"]["hectareas"]
    ha_sin = otbn_dist["Sin OTBN"]["hectareas"]
    ha_otbn_total = round(ha_i + ha_ii + ha_iii, 1)

    fechas_str = ", ".join(legal_meta.get("fechas_norma") or []) or "No informada"
    provs_str = ", ".join(legal_meta.get("provincias") or []) or "Argentina"

    nota_legal = (
        f"Capa oficial nacional SNMB (bosques:otbn_nacional) — Jurisdicción: {provs_str} | "
        f"Fecha de norma registrada (dct): {fechas_str}. "
        "Tamizaje geoespacial orientativo: algunas provincias pueden contar con actualizaciones recientes de su OTBN "
        "aún no consolidadas en el GeoServer nacional; verificar con la Autoridad Local de Aplicación provincial."
    )

    modulos: List[Dict[str, Any]] = []

    if ha_otbn_total == 0.0:
        modulos.append({
            "dominio": "Cobertura OTBN Nacional (Ley N.° 26.331)",
            "nivel": "Sin Zonificación OTBN",
            "color": "#64748b",
            "hallazgo": (
                f"Las {ha_sin:,.1f} ha del recuadro no registran polígonos de Categoría I, II ni III en la capa nacional `bosques:otbn_nacional` "
                "(área no boscosa, ejido urbano, espejo de agua o jurisdicción sin zonificación consolidada)."
            ),
            "recomendaciones": (
                "Consultar el nodo IDE provincial correspondiente si el área se encuentra próxima a bosques nativos recientemente recategorizados."
            ),
        })
        return {
            "estado_zonificacion": "Área Sin Categorías OTBN en Capa Nacional",
            "nivel_alerta": "Informativo",
            "modulos_activos": modulos,
            "nota_alcance_regulatorio": nota_legal,
        }

    # Resumen de zonificación dominante
    if ha_i >= max(ha_ii, ha_iii) and ha_i > 0:
        dom_label = "Predominio de Categoría I (Rojo — Conservación Estricta)"
    elif ha_ii >= max(ha_i, ha_iii) and ha_ii > 0:
        dom_label = "Predominio de Categoría II (Amarillo — Uso Sostenible)"
    else:
        dom_label = "Predominio de Categoría III (Verde — Transformación Regulada)"

    if not cruce.get("disponible"):
        modulos.append({
            "dominio": "Zonificación Legal OTBN (Ley N.° 26.331)",
            "nivel": "Zonificación Detectada",
            "color": "#15803d",
            "hallazgo": (
                f"Superficie zonificada en OTBN: {ha_otbn_total:,.1f} ha "
                f"(Cat. I Rojo: {ha_i:,.1f} ha | Cat. II Amarillo: {ha_ii:,.1f} ha | Cat. III Verde: {ha_iii:,.1f} ha)."
            ),
            "recomendaciones": (
                "Ejecutá la clasificación de coberturas (ESA WorldCover / Esri LULC) para contrastar la cobertura real del suelo contra las restricciones Rojo/Amarillo/Verde."
            ),
        })
        return {
            "estado_zonificacion": dom_label,
            "nivel_alerta": "Alto" if ha_i > 0 else "Moderado",
            "modulos_activos": modulos,
            "nota_alcance_regulatorio": nota_legal,
        }

    ind = cruce["indicadores_cruce"]
    pres_i = ind["presion_productiva_en_rojo_I_ha"]
    pres_ii = ind["presion_productiva_en_amarillo_II_ha"]
    len_i = ind["lenoso_en_rojo_I_ha"]
    len_ii = ind["lenoso_en_amarillo_II_ha"]
    len_iii = ind["lenoso_en_verde_III_ha"]
    bos_sin = ind["bosque_sin_otbn_ha"]
    urb_ra = ind["urbano_en_rojo_o_amarillo_ha"]

    # Módulo 1: Conservación de masa forestal en Categorías I y II
    if len_i > 0 or len_ii > 0:
        modulos.append({
            "dominio": "Resguardo de Bosques Nativos (Cat. I Rojo y II Amarillo)",
            "nivel": "Protección Estricta / Restricción de Desmonte",
            "color": "#dc2626" if len_i >= 5.0 else "#d97706",
            "hallazgo": (
                f"Se identifican {len_i:,.1f} ha de cobertura arbórea/leñosa dentro de Categoría I (Rojo) "
                f"y {len_ii:,.1f} ha dentro de Categoría II (Amarillo)."
            ),
            "recomendaciones": (
                "En Categoría I (Rojo) no corresponde transformación ni aprovechamiento maderero. "
                "En Categoría II (Amarillo) no se admite cambio de uso del suelo (desmonte), requiriéndose Plan de Manejo Sostenible aprobado."
            ),
        })

    # Módulo 2: Contraste de Cultivos / Suelo Desnudo en áreas de conservación
    if pres_i >= 2.0 or pres_ii >= 5.0:
        nivel_p = "Atención Prioritaria" if pres_i >= 2.0 else "Seguimiento"
        modulos.append({
            "dominio": "Contraste Uso Productivo / Suelo Expuesto × OTBN",
            "nivel": nivel_p,
            "color": "#b91c1c" if pres_i >= 2.0 else "#d97706",
            "hallazgo": (
                f"La cobertura satelital detecta {ind['cultivo_en_rojo_I_ha']:,.1f} ha de cultivos y "
                f"{ind['suelo_desnudo_en_rojo_I_ha']:,.1f} ha de suelo desnudo dentro de Cat. I (Rojo), más "
                f"{ind['cultivo_en_amarillo_II_ha']:,.1f} ha de cultivos y {ind['suelo_desnudo_en_amarillo_II_ha']:,.1f} ha "
                "de suelo desnudo dentro de Cat. II (Amarillo)."
            ),
            "recomendaciones": (
                "Verificar si dichas superficies corresponden a desmontes previos a la sanción de la Ley N.° 26.331, "
                "enclaves productivos preexistentes, recategorizaciones prediales o eventuales intervenciones no autorizadas."
            ),
        })

    # Módulo 3: Categoría III (Verde), Urbano en Rojo/Amarillo o Bosque fuera de OTBN
    if len_iii >= 2.0 or urb_ra >= 2.0 or bos_sin >= 5.0:
        hallazgos_extra = []
        if len_iii >= 2.0:
            hallazgos_extra.append(f"{len_iii:,.1f} ha arbóreas/leñosas en Cat. III (Verde)")
        if urb_ra >= 2.0:
            hallazgos_extra.append(f"{urb_ra:,.1f} ha de trama construida/urbana superpuesta con Cat. I/II")
        if bos_sin >= 5.0:
            hallazgos_extra.append(f"{bos_sin:,.1f} ha de cobertura arbórea fuera de polígonos OTBN nacionales")
        modulos.append({
            "dominio": "Transformación Regulada, Periurbano y Cobertura Extra-OTBN",
            "nivel": "Gestión Territorial",
            "color": "#15803d",
            "hallazgo": "Se registran: " + "; ".join(hallazgos_extra) + ".",
            "recomendaciones": (
                "Cualquier cambio de uso del suelo en Cat. III (Verde) requiere Evaluación de Impacto Ambiental previa ante la autoridad provincial; "
                "la cobertura arbórea fuera de OTBN puede corresponder a forestaciones implantadas, cortinas o bosque no cartografiado en el corte nacional."
            ),
        })

    if not modulos:
        modulos.append({
            "dominio": "Zonificación Legal OTBN (Ley N.° 26.331)",
            "nivel": "Informativo",
            "color": "#15803d",
            "hallazgo": f"Superficie zonificada en OTBN: {ha_otbn_total:,.1f} ha (Rojo: {ha_i:,.1f} ha | Amarillo: {ha_ii:,.1f} ha | Verde: {ha_iii:,.1f} ha).",
            "recomendaciones": "Mantener monitoreo multitemporal en el área según las categorías provinciales vigentes.",
        })

    nivel_alerta = "Alto" if (pres_i >= 2.0 or len_i >= 5.0) else ("Moderado" if (ha_ii > 0 or pres_ii >= 5.0) else "Bajo")

    return {
        "estado_zonificacion": dom_label,
        "nivel_alerta": nivel_alerta,
        "modulos_activos": modulos,
        "nota_alcance_regulatorio": nota_legal,
    }


def _generate_otbn_figure(
    otbn_grid: np.ndarray,
    otbn_dist: Dict[str, Dict[str, Any]],
    cruce: Dict[str, Any],
    bbox: List[float],
    legal_meta: Dict[str, Any],
) -> str:
    """Genera figura analítica (Mapa de Categorías OTBN + Distribución de Coberturas por Categoría)."""
    min_lon, min_lat, max_lon, max_lat = [float(x) for x in bbox]
    has_cross = bool(cruce.get("disponible") and cruce.get("matriz_cobertura_otbn"))

    if has_cross:
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14.5, 6.4), dpi=150, gridspec_kw={"width_ratios": [1.05, 1.15]})
    else:
        fig, ax1 = plt.subplots(1, 1, figsize=(8.2, 6.4), dpi=150)
        ax2 = None

    # Panel 1: Mapa categórico OTBN
    h, w = otbn_grid.shape
    vis_rgba = np.zeros((h, w, 4), dtype=np.uint8)
    vis_rgba[otbn_grid == 0] = [226, 232, 240, 255]
    for cat_id in (1, 2, 3):
        r, g, b = OTBN_CATEGORIES[cat_id]["rgb"]
        vis_rgba[otbn_grid == cat_id] = [r, g, b, 235]

    ax1.imshow(vis_rgba, extent=[min_lon, max_lon, min_lat, max_lat], origin="upper", interpolation="nearest")
    patches = [
        mpatches.Patch(
            color=OTBN_CATEGORIES[cid]["color"],
            label=f"{OTBN_CATEGORIES[cid]['short_name']} ({otbn_dist[OTBN_CATEGORIES[cid]['cam']]['porcentaje']}% — {otbn_dist[OTBN_CATEGORIES[cid]['cam']]['hectareas']:,.1f} ha)",
        )
        for cid in (1, 2, 3, 0)
    ]
    ax1.legend(handles=patches, loc="lower left", framealpha=0.92, fontsize=8.0, title="Ley N.° 26.331 (OTBN)")
    provs_str = ", ".join(legal_meta.get("provincias") or []) or "Argentina"
    ax1.set_title(
        f"Zonificación OTBN Nacional ({provs_str})\nFuente: SNMB GeoServer (bosques:otbn_nacional)",
        fontsize=10.5,
        fontweight="bold",
    )
    ax1.set_xlabel("Longitud (°)")
    ax1.set_ylabel("Latitud (°)")

    # Panel 2: Barras horizontales apiladas Cobertura x Categoría OTBN
    if ax2 is not None:
        matriz = cruce["matriz_cobertura_otbn"]
        sorted_rows = sorted(matriz.values(), key=lambda x: x["hectareas"], reverse=True)
        sorted_rows = [r for r in sorted_rows if r["hectareas"] > 0][:7]

        if sorted_rows:
            labels = [r["nombre"].split("(")[0].strip() for r in sorted_rows][::-1]
            y_pos = np.arange(len(labels))
            left_acc = np.zeros(len(labels), dtype=float)

            for cat_id in (1, 2, 3, 0):
                cam = OTBN_CATEGORIES[cat_id]["cam"]
                vals = np.array(
                    [float(r.get("por_otbn", {}).get(cam, {}).get("hectareas", 0.0)) for r in sorted_rows][::-1],
                    dtype=float,
                )
                ax2.barh(
                    y_pos,
                    vals,
                    left=left_acc,
                    color=OTBN_CATEGORIES[cat_id]["color"],
                    edgecolor="#ffffff",
                    linewidth=0.6,
                    label=OTBN_CATEGORIES[cat_id]["short_name"],
                )
                left_acc += vals

            ax2.set_yticks(y_pos)
            ax2.set_yticklabels(labels, fontsize=9)
            ax2.set_xlabel("Superficie (hectáreas)")
            ax2.set_title(
                f"Cruce Espacial: Cobertura Real × Categoría OTBN\nFuente Cobertura: {cruce.get('fuente_cobertura')}",
                fontsize=10.0,
                fontweight="bold",
            )
            ax2.grid(axis="x", linestyle="--", alpha=0.35)
            ax2.legend(loc="lower right", framealpha=0.92, fontsize=8.0)

    plt.tight_layout()
    tag = _bbox_tag(bbox)
    out_path = OUTPUTS_DIR / f"mapa_otbn_{tag}.png"
    plt.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close()
    return str(out_path)


def analyze_otbn_for_bbox(
    bbox: Optional[List[float]] = None,
    classification_context: Optional[Dict[str, Any]] = None,
    auto_fetch_landcover: bool = True,
) -> Dict[str, Any]:
    """
    Descarga la capa oficial del Ordenamiento Territorial de Bosques Nativos (OTBN - Ley N.° 26.331)
    para un Bounding Box [min_lon, min_lat, max_lon, max_lat], recupera metadatos legales y ejecuta
    el cruce espacial píxel a píxel contra la cobertura del suelo (10m).
    """
    target_bbox = [float(x) for x in (bbox or DEFAULT_BBOX)]

    # Guardrail espacial coherente con el Sandbox (máx. 100.000 ha)
    dim_check = estimate_bbox_dimensions(target_bbox, res_m=10.0)
    if dim_check["bloqueado"]:
        raise ValueError(dim_check["mensaje"])

    width, height = _compute_wms_dimensions(target_bbox, max_dim=1024, min_dim=128)
    rgba = _fetch_wms_otbn_image(target_bbox, width=width, height=height)
    otbn_grid = _decode_otbn_rgba_to_grid(rgba)

    min_lon, min_lat, max_lon, max_lat = target_bbox
    otbn_transform = transform_from_bounds(min_lon, min_lat, max_lon, max_lat, width, height)
    folium_bounds = [[min_lat, min_lon], [max_lat, max_lon]]

    # Área geodésica aproximada por píxel WMS
    mid_lat = (min_lat + max_lat) / 2.0
    dy_m = ((max_lat - min_lat) / max(1, height)) * 111320.0
    dx_m = ((max_lon - min_lon) / max(1, width)) * 111320.0 * math.cos(math.radians(mid_lat))
    wms_cell_ha = (dy_m * dx_m) / 10000.0
    total_wms_px = otbn_grid.size
    total_ha_bbox = round(total_wms_px * wms_cell_ha, 1)

    # Estadísticas base sobre la grilla WMS
    otbn_dist_wms: Dict[str, Dict[str, Any]] = {}
    for cat_id in (1, 2, 3, 0):
        cat_meta = OTBN_CATEGORIES[cat_id]
        c_px = int(np.sum(otbn_grid == cat_id))
        otbn_dist_wms[cat_meta["cam"]] = {
            "codigo": cat_id,
            "cam": cat_meta["cam"],
            "nombre": cat_meta["name"],
            "short_name": cat_meta["short_name"],
            "color": cat_meta["color"],
            "hectareas": round(c_px * wms_cell_ha, 1),
            "porcentaje": round((c_px / max(1, total_wms_px)) * 100.0, 2),
        }

    # Metadatos jurídicos (provincia, decreto, autoridad) vía WMS GetFeatureInfo
    legal_meta = _collect_legal_metadata(otbn_grid, target_bbox, width, height)

    # Cruce espacial Cobertura x OTBN
    lc_ctx, lc_source_label = _resolve_landcover_context(
        bbox=target_bbox,
        classification_context=classification_context,
        auto_fetch_landcover=auto_fetch_landcover,
    )
    cruce: Dict[str, Any] = {
        "disponible": False,
        "fuente_cobertura": lc_source_label,
        "matriz_cobertura_otbn": {},
        "indicadores_cruce": {},
    }
    if lc_ctx is not None:
        cross_res = _cross_landcover_with_otbn(
            otbn_grid=otbn_grid,
            otbn_transform=otbn_transform,
            lc_ctx=lc_ctx,
            lc_source_label=lc_source_label,
        )
        if cross_res is not None:
            cruce = cross_res

    # Usar la distribución alineada a 10m cuando el cruce está disponible para total consistencia en ha
    otbn_dist_final = cruce.get("distribucion_otbn_alineada") or otbn_dist_wms
    superficie_final_ha = cruce.get("superficie_total_ha") or total_ha_bbox

    # Guardar overlay transparente para Folium
    overlay_rgba = np.zeros((height, width, 4), dtype=np.uint8)
    for cat_id in (1, 2, 3):
        r, g, b = OTBN_CATEGORIES[cat_id]["rgb"]
        a = OTBN_CATEGORIES[cat_id]["alpha"]
        overlay_rgba[otbn_grid == cat_id] = [r, g, b, a]

    tag = _bbox_tag(target_bbox)
    overlay_path = OUTPUTS_DIR / f"overlay_otbn_{tag}.png"
    Image.fromarray(overlay_rgba, mode="RGBA").save(overlay_path)

    # Guardar caché .npz de la grilla OTBN
    cache_path = OUTPUTS_DIR / f"otbn_grid_{tag}.npz"
    tf_arr = np.array(list(otbn_transform)[:6], dtype=np.float64)
    np.savez_compressed(
        cache_path,
        grid=otbn_grid,
        transform=tf_arr,
        crs=np.array("EPSG:4326"),
    )

    diagnostico = _build_otbn_diagnosis(otbn_dist_final, cruce, legal_meta)
    mapa_path = _generate_otbn_figure(otbn_grid, otbn_dist_final, cruce, target_bbox, legal_meta)

    ubicacion_admin = get_location_for_bbox(target_bbox)
    provs_lbl = ", ".join(legal_meta.get("provincias") or []) or ubicacion_admin.get("provincia") or "Argentina"
    fechas_lbl = ", ".join(legal_meta.get("fechas_norma") or []) or "N/D"

    resumen_lines = [
        f"🌳 **Zonificación OTBN Nacional (Ley N.° 26.331) — {provs_lbl} (Norma dct: {fechas_lbl}):**",
        f"• **Categoría I (Rojo):** {otbn_dist_final['I']['porcentaje']}% ({otbn_dist_final['I']['hectareas']:,.1f} ha)",
        f"• **Categoría II (Amarillo):** {otbn_dist_final['II']['porcentaje']}% ({otbn_dist_final['II']['hectareas']:,.1f} ha)",
        f"• **Categoría III (Verde):** {otbn_dist_final['III']['porcentaje']}% ({otbn_dist_final['III']['hectareas']:,.1f} ha)",
        f"• **Sin categoría OTBN:** {otbn_dist_final['Sin OTBN']['porcentaje']}% ({otbn_dist_final['Sin OTBN']['hectareas']:,.1f} ha)",
    ]
    if cruce.get("disponible"):
        ind = cruce["indicadores_cruce"]
        resumen_lines.append(
            f"• **Cruce Cobertura × OTBN ({cruce['fuente_cobertura']}):** "
            f"Bosque en Rojo I: {ind['bosque_en_rojo_I_ha']:,.1f} ha | "
            f"Bosque en Amarillo II: {ind['bosque_en_amarillo_II_ha']:,.1f} ha | "
            f"Cultivo+Suelo en Rojo I: {ind['presion_productiva_en_rojo_I_ha']:,.1f} ha"
        )

    return {
        "status": "success",
        "tipo_analisis": "Ordenamiento Territorial de Bosques Nativos (OTBN - Ley N.° 26.331) y Cruce Espacial",
        "fuente_otbn": "GeoServer Subsecretaría de Ambiente de la Nación / SNMB (bosques:otbn_nacional)",
        "superficie_total_ha": superficie_final_ha,
        "distribucion_otbn": otbn_dist_final,
        "metadatos_legales": legal_meta,
        "cruce_cobertura_otbn": cruce,
        "diagnostico_otbn": diagnostico,
        "raster_cache_path": str(cache_path),
        "overlay_generado": str(overlay_path),
        "mapa_generado": mapa_path,
        "folium_bounds": folium_bounds,
        "ubicacion_administrativa": ubicacion_admin,
        "resumen_ejecutivo": "\n".join(resumen_lines),
    }
