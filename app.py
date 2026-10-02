"""
Frontend Interactivo con Selección Territorial en Mapa y Asistente ReAct Geoespacial
Soporta:
1. Modelo de IA Deep Learning: ESA WorldCover (10m de resolución - 8+ clases de cobertura)
2. Umbralización Radiométrica: NDVI Sentinel-2 L2A (Bandas B04 y B08 a 10m)
Superposición Georreferenciada Directa sobre el Mapa (ImageOverlay)
Diplomatura Universitaria ISBIA - Lidesia - UNC / Grupo_6_2026
"""
import streamlit as st

st.set_page_config(
    layout="wide",
    page_title="TFI_Grupo_6_2026: Clasificación de Coberturas del suelo con Agentes IA",
    page_icon="🛰️"
)

import folium
from folium.plugins import Draw
from folium.raster_layers import ImageOverlay
from streamlit_folium import st_folium
import json
import os
import math
from pathlib import Path
from shapely.geometry import shape

from agent.core import GeoReActAgent
from tools.base import default_registry
from services.real_satellite_service import (
    search_real_scenes,
    fetch_and_classify_real_scene,
    classify_with_esa_worldcover,
    estimate_bbox_dimensions,
    DEFAULT_BBOX,
    ESA_WORLDCOVER_CLASSES
)
from services.drainage_service import analyze_drainage_and_slope
from services.geo_admin_service import (
    get_location_for_bbox, 
    get_administrative_location,
    search_location_argentina
)
from config import OUTPUTS_DIR
import datetime

@st.cache_data(show_spinner=False, ttl=3600)
def cached_admin_location(bbox_tuple: tuple):
    return get_location_for_bbox(list(bbox_tuple))

@st.dialog("🔬 Configurar y Ejecutar Clasificación", width="large")
def dialog_clasificacion():
    """Cuadro de diálogo modal para configurar y lanzar la clasificación del área seleccionada."""
    admin_info = cached_admin_location(tuple(st.session_state.current_bbox))
    loc_text = admin_info.get("texto_formateado", "Argentina")
    fuente_text = admin_info.get("fuente", "IGN Georef")
    dim_info = estimate_bbox_dimensions(st.session_state.current_bbox)
    
    st.markdown(
        f"""
        <div style="background-color: #f0fdf4; border: 1px solid #bbf7d0; border-left: 4px solid #16a34a; padding: 6px 12px; border-radius: 6px; margin-bottom: 12px; font-size: 0.88rem; color: #1e293b;">
            📍 <b>Área a Clasificar:</b> <b>{dim_info['superficie_ha']:,.1f} ha</b> ({dim_info['total_pixeles']:,} px a 10m) &nbsp;|&nbsp; 🏛️ <b>Ubicación:</b> <span style="font-weight: 600; color: #15803d;">{loc_text}</span> <span style="color: #64748b; font-size: 0.78rem;">({fuente_text})</span>
        </div>
        """,
        unsafe_allow_html=True
    )
    
    engine_choice = st.radio(
        "Seleccioná el método de clasificación:",
        options=[
            "🧠 Modelo IA Deep Learning: ESA WorldCover (10m - 8+ Clases: Bosque, Cultivo, Matorral, Pastizal, Agua, etc.)",
            "⚡ Umbralización Radiométrica: NDVI Sentinel-2 L2A (10m - Vegetación / Suelo / Agua)"
        ],
        index=0
    )
    
    # ---------------------------------------------------------
    # RAMA A: MODELO IA DEEP LEARNING
    # ---------------------------------------------------------
    if "WorldCover" in engine_choice:
        st.markdown("---")
        col_wc1, col_wc2 = st.columns([1, 1.3])
        wc_year = col_wc1.selectbox("📅 Año del Modelo / Imagen:", ["2021", "2020"], index=0)
        col_wc2.info("💡 Clasificación automática en 8+ clases taxonómicas mediante redes convolucionales globales (ESA/VITO).")
        
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button(f"🚀 Ejecutar Modelo de IA: ESA WorldCover ({wc_year})", type="primary", use_container_width=True):
            with st.spinner(f"Ejecutando inferencia del modelo ESA WorldCover 10m para el año {wc_year}..."):
                try:
                    res = classify_with_esa_worldcover(
                        bbox=st.session_state.current_bbox,
                        year=wc_year
                    )
                    st.session_state.classification_result = res
                    st.session_state.map_version += 1
                    if res.get("folium_bounds"):
                        st.session_state.fit_bounds_target = res["folium_bounds"]
                    st.rerun()
                except Exception as e:
                    st.error(f"Error al ejecutar modelo ESA WorldCover: {e}")

    # ---------------------------------------------------------
    # RAMA B: RADIOMETRÍA SENTINEL-2 L2A
    # ---------------------------------------------------------
    else:
        st.markdown("---")
        st.markdown("##### 🕒 Selector de Escenas Históricas y Parámetros Espectrales")
        col_hist1, col_hist2, col_hist3 = st.columns([1, 1, 1])
        hist_year = col_hist1.selectbox("Año Histórico:", ["2024", "2023", "2022", "2021", "2020"], index=0)
        max_clouds = col_hist2.slider("Nubosidad Máx. (%):", 0.0, 30.0, 15.0, 5.0)
        limite_escenas = col_hist3.selectbox("Cant. Escenas:", [5, 10, 15], index=1)

        date_range_query = f"{hist_year}-01-01/{hist_year}-12-31"

        with st.spinner(f"Consultando catálogo STAC para escenas del año {hist_year}..."):
            real_scenes = search_real_scenes(
                bbox=st.session_state.current_bbox,
                date_range=date_range_query,
                max_cloud=max_clouds,
                limit=limite_escenas
            )

        if not real_scenes:
            st.warning(f"No se encontraron escenas con menos del {max_clouds}% de nubes en {hist_year}. Probá aumentando el umbral de nubes.")
        
        options_dict = {
            f"📅 {s['fecha']} | {s['satelite']} (Nubes: {s['cobertura_nubes_pct']}%)": s
            for s in real_scenes
        }

        selected_label = st.selectbox(
            "Seleccioná la escena Sentinel-2 histórica a procesar:",
            options=list(options_dict.keys()),
            index=0 if options_dict else None
        )

        col_s2_1, col_s2_2 = st.columns([1, 1])
        ndvi_thresh = col_s2_1.slider("Umbral NDVI Vegetación:", 0.20, 0.60, 0.35, 0.05)

        if selected_label:
            selected_scene = options_dict[selected_label]
            col_s2_2.info(f"📅 **Fecha:** `{selected_scene['fecha']}`\n🛰️ **Satélite:** `{selected_scene['satelite']}`\n☁️ **Nubosidad:** `{selected_scene['cobertura_nubes_pct']}%`")

            st.markdown("<br>", unsafe_allow_html=True)
            if st.button(f"🚀 Procesar Bandas B04/B08 ({selected_scene['fecha']}) a 10m", type="primary", use_container_width=True):
                with st.spinner(f"Descargando bandas COG para la fecha {selected_scene['fecha']}..."):
                    try:
                        res = fetch_and_classify_real_scene(
                            item_id=selected_scene["id"],
                            bbox=st.session_state.current_bbox,
                            ndvi_threshold=ndvi_thresh
                        )
                        st.session_state.classification_result = res
                        st.session_state.map_version += 1
                        if res.get("folium_bounds"):
                            st.session_state.fit_bounds_target = res["folium_bounds"]
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error al procesar la imagen satelital: {e}")

# Fecha y hora de compilación / última actualización del archivo
app_mtime = os.path.getmtime(__file__)
last_update_str = datetime.datetime.fromtimestamp(app_mtime).strftime("%d/%m/%Y %H:%M:%S")

# Inicializar estado de sesión
# Punto de inicio por defecto: Laguna Mar Chiquita (Mar de Ansenuza), Córdoba, Argentina
MAR_CHIQUITA_CENTER = [-30.60, -62.65]
MAR_CHIQUITA_ZOOM = 9

if "agent" not in st.session_state:
    st.session_state.agent = GeoReActAgent(registry=default_registry)
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
if "classification_result" not in st.session_state:
    st.session_state.classification_result = None
if "drainage_result" not in st.session_state:
    st.session_state.drainage_result = None
if "current_bbox" not in st.session_state:
    st.session_state.current_bbox = DEFAULT_BBOX
if "map_center" not in st.session_state:
    st.session_state.map_center = MAR_CHIQUITA_CENTER
if "map_zoom" not in st.session_state:
    st.session_state.map_zoom = MAR_CHIQUITA_ZOOM
if "map_version" not in st.session_state:
    st.session_state.map_version = 0
if "fit_bounds_target" not in st.session_state:
    st.session_state.fit_bounds_target = None
if "drawn_geometry" not in st.session_state:
    st.session_state.drawn_geometry = None
if "last_searched_location" not in st.session_state:
    st.session_state.last_searched_location = None

# Encabezado y Subtítulo enriquecido con Stack Tecnológico y Timestamp de Compilación
st.title("🛰️ TFI_Grupo_6_2026: Clasificación de Coberturas del suelo con Agentes IA")
st.caption(f"⏱️ **Última compilación / actualización:** `{last_update_str}` | Diplomatura Universitaria ISBIA - Lidesia - FCEFyN (UNC) / Grupo_6_2026")
st.caption("🧩 **Arquitectura & Stack:** **Frontend:** Streamlit + Folium (GIS) | **Datos & Teledetección:** STAC API (Planetary Computer) & Rasterio (COGs) | **Agente Inteligente:** ReAct (*Reasoning + Acting*) + RAG Documental Local | **Modelos:** ESA WorldCover 10m (Deep Learning CNN), Sentinel-2 MSI & Copernicus DEM 30m (Hidrología)")

col_left, col_right = st.columns([1.22, 1.0], gap="large")

# -------------------------------------------------------------
# COLUMNA IZQUIERDA: MAPA INTERACTIVO Y CLASIFICACIÓN CON IA
# -------------------------------------------------------------
with col_left:
    st.subheader("1. 🗺️ Delimitación Territorial sobre el Mapa (Visor Satelital)")
    st.markdown(
        "Posicioná rápidamente el visor buscando tu localidad o paraje, o navegá libremente por el mapa. "
        "Luego trazá un **rectángulo** para definir tu área de análisis:"
    )

    # ---------------------------------------------------------
    # BUSCADOR RÁPIDO DE POSICIONAMIENTO EN ARGENTINA (IGN GEOREF)
    # ---------------------------------------------------------
    with st.form(key="geo_search_form", clear_on_submit=False):
        col_s_input, col_s_btn = st.columns([3.3, 1.2])
        query_input = col_s_input.text_input(
            "Buscar localidad, departamento o paraje en Argentina:",
            placeholder="🔍 Ej: Pergamino, Buenos Aires / Balcarce / Río Cuarto / Bandera...",
            label_visibility="collapsed"
        )
        submit_search = col_s_btn.form_submit_button("📍 Buscar Zona", use_container_width=True)

    if submit_search:
        if query_input and query_input.strip():
            with st.spinner(f"Consultando IGN Georef para '{query_input.strip()}'..."):
                geo_res = search_location_argentina(query_input.strip())
                if geo_res.get("ok"):
                    st.session_state.map_center = [geo_res["lat"], geo_res["lon"]]
                    st.session_state.map_zoom = geo_res.get("zoom_sugerido", 12)
                    st.session_state.fit_bounds_target = geo_res.get("folium_bounds")
                    st.session_state.map_version += 1
                    st.session_state.last_searched_location = geo_res
                    st.rerun()
                else:
                    st.error(geo_res.get("error", f"No se encontró la ubicación '{query_input}'."))
        else:
            st.warning("⚠️ Ingresá el nombre de una localidad, paraje o departamento.")

    # Notificación visual de la última ubicación posicionada
    if st.session_state.get("last_searched_location"):
        last_loc = st.session_state.last_searched_location
        st.markdown(
            f"""
            <div style="background-color: #f0fdf4; border: 1px solid #bbf7d0; border-left: 4px solid #16a34a; padding: 4px 10px; border-radius: 4px; margin-bottom: 8px; font-size: 0.83rem; color: #1e293b;">
                📍 <b>Visor posicionado en:</b> <span style="font-weight: 600; color: #15803d;">{last_loc.get('texto_formateado')}</span> 
                <span style="color: #64748b; font-size: 0.76rem;">({last_loc.get('fuente')})</span>
            </div>
            """,
            unsafe_allow_html=True
        )

    # Controles de Encuadre, Limpieza y Reset del Visor
    col_zoom1, col_zoom2, col_zoom3 = st.columns([1.2, 1.2, 1.0])
    btn_fit_area = col_zoom1.button("🎯 Centrar Área", use_container_width=True, help="Encuadra el visor en el rectángulo seleccionado o ráster clasificado")
    btn_clear_map = col_zoom2.button("🗑️ Limpiar Visor", use_container_width=True, help="Borra la selección rectangular, la clasificación y el drenaje")
    btn_reset_mar = col_zoom3.button("🌊 Reset: Inicio", use_container_width=True, help="Restaura la vista inicial en Laguna Mar Chiquita (Córdoba)")

    if btn_fit_area:
        st.session_state.map_version += 1
        if st.session_state.classification_result and st.session_state.classification_result.get("folium_bounds"):
            target_b = st.session_state.classification_result["folium_bounds"]
        elif st.session_state.drainage_result and st.session_state.drainage_result.get("folium_bounds"):
            target_b = st.session_state.drainage_result["folium_bounds"]
        elif st.session_state.current_bbox:
            bbox = st.session_state.current_bbox
            target_b = [[bbox[1], bbox[0]], [bbox[3], bbox[2]]]
        else:
            target_b = [[DEFAULT_BBOX[1], DEFAULT_BBOX[0]], [DEFAULT_BBOX[3], DEFAULT_BBOX[2]]]
        st.session_state.fit_bounds_target = target_b
        st.session_state.map_center = [
            round((target_b[0][0] + target_b[1][0]) / 2.0, 5),
            round((target_b[0][1] + target_b[1][1]) / 2.0, 5)
        ]
        st.rerun()

    if btn_clear_map:
        # Borra el rectángulo, el ráster clasificado y las líneas de drenaje
        st.session_state.map_version += 1
        st.session_state.drawn_geometry = None
        st.session_state.classification_result = None
        st.session_state.drainage_result = None
        st.session_state.fit_bounds_target = None
        st.rerun()

    if btn_reset_mar:
        st.session_state.map_version += 1
        st.session_state.map_center = MAR_CHIQUITA_CENTER
        st.session_state.map_zoom = MAR_CHIQUITA_ZOOM
        st.session_state.current_bbox = DEFAULT_BBOX
        st.session_state.drawn_geometry = None
        st.session_state.fit_bounds_target = None
        st.session_state.classification_result = None
        st.session_state.drainage_result = None
        st.session_state.last_searched_location = None
        st.rerun()


    # Crear mapa folium con capa base Google Híbrido (Satelital + Rutas/Límites/Ciudades)
    m = folium.Map(
        location=st.session_state.map_center,
        zoom_start=st.session_state.map_zoom,
        tiles=None,
        control_scale=True
    )
    folium.TileLayer(
        tiles="https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}",
        attr="Google Hybrid",
        name="🗺️ Google Híbrido (Satelital + Rutas/Límites)",
        overlay=False,
        control=True
    ).add_to(m)

    # Etiqueta en la esquina inferior derecha situada por encima de la barra de Leaflet
    watermark_html = """
    <div style="
        position: absolute;
        bottom: 20px;
        right: 5px;
        z-index: 999;
        background-color: rgba(255, 255, 255, 0.88);
        padding: 2px 7px;
        border-radius: 3px;
        font-size: 10px;
        color: #334155;
        border: 1px solid #cbd5e1;
        box-shadow: 0 1px 2px rgba(0,0,0,0.15);
        pointer-events: none;
        font-family: sans-serif;
    ">
        🛰️ <b>Base:</b> Google Hybrid <i>(Mosaico Compuesto)</i>
    </div>
    """
    m.get_root().html.add_child(folium.Element(watermark_html))

    # Si se solicitó centrar y maximizar el área clasificada / AOI
    if st.session_state.fit_bounds_target:
        m.fit_bounds(st.session_state.fit_bounds_target)

    # Renderizar el rectángulo delimitado activo únicamente si hay una geometría activa
    if st.session_state.drawn_geometry:
        folium.GeoJson(
            st.session_state.drawn_geometry,
            name="📍 Rectángulo Delimitado",
            style_function=lambda x: {
                "color": "#e53935",
                "weight": 2.5,
                "fillColor": "#e53935",
                "fillOpacity": 0.15,
                "dashArray": "5, 5"
            },
            tooltip="Área rectangular activa para clasificación"
        ).add_to(m)

    # Si hay una clasificación previa con overlay generado, superponerla en el mapa
    if st.session_state.classification_result:
        res_prev = st.session_state.classification_result
        overlay_path = res_prev.get("overlay_generado")
        f_bounds = res_prev.get("folium_bounds")
        
        # Etiqueta clara con método y fecha/año para evitar cualquier confusión
        is_ia = "WorldCover" in str(res_prev.get("modelo", "")) or "IA" in str(res_prev.get("modelo", ""))
        if is_ia:
            year_tag = res_prev.get("año_referencia") or "2021"
            overlay_name = f"🛰️ Cobertura [IA - WorldCover {year_tag}]"
        else:
            fecha_tag = res_prev.get("fecha_analizada") or "S2"
            overlay_name = f"🛰️ Cobertura [Radiometría - S2 {fecha_tag}]"
        
        if overlay_path and os.path.exists(overlay_path) and f_bounds:
            ImageOverlay(
                name=overlay_name,
                image=overlay_path,
                bounds=f_bounds,
                opacity=0.75,
                interactive=True,
                cross_origin=False,
                zindex=10
            ).add_to(m)

    # Si hay análisis de red de drenaje con overlay generado, superponerlo en el mapa
    if st.session_state.get("drainage_result"):
        res_drain = st.session_state.drainage_result
        d_overlay_path = res_drain.get("overlay_generado")
        d_bounds = res_drain.get("folium_bounds")
        if d_overlay_path and os.path.exists(d_overlay_path) and d_bounds:
            ImageOverlay(
                name="🌊 Red de Drenaje Hídrico (Dirección + Pendiente)",
                image=d_overlay_path,
                bounds=d_bounds,
                opacity=0.88,
                interactive=True,
                cross_origin=False,
                zindex=20
            ).add_to(m)

    # Herramienta de dibujo (Draw) - Solo Rectángulo con soporte de edición y borrado (papelera)
    draw = Draw(
        export=True,
        filename="area_seleccionada.geojson",
        position="topleft",
        draw_options={
            "polyline": False,
            "circle": False,
            "circlemarker": False,
            "marker": False,
            "polygon": False,
            "rectangle": True
        },
        edit_options={
            "edit": True,
            "remove": True
        }
    )
    draw.add_to(m)
    folium.LayerControl(position="topright", collapsed=True).add_to(m)

    # Configurar returned_objects=['last_active_drawing', 'all_drawings'] y key dinámica
    map_output = st_folium(
        m, 
        width="100%", 
        height=420, 
        returned_objects=["last_active_drawing", "all_drawings"],
        key=f"main_map_{st.session_state.map_version}"
    )

    # Procesar eventos del mapa: dibujo nuevo o borrado con la papelera
    if map_output:
        all_drawings = map_output.get("all_drawings")
        last_drawing = map_output.get("last_active_drawing")

        # CASO A: El usuario hizo clic en la papelera y eliminó los dibujos en el mapa
        if all_drawings is not None and len(all_drawings) == 0 and (st.session_state.drawn_geometry is not None or st.session_state.classification_result is not None or st.session_state.drainage_result is not None):
            st.session_state.drawn_geometry = None
            st.session_state.classification_result = None
            st.session_state.drainage_result = None
            st.session_state.fit_bounds_target = None
            st.session_state.map_version += 1
            st.rerun()

        # CASO B: El usuario realizó un nuevo dibujo de rectángulo
        elif last_drawing and last_drawing.get("geometry"):
            geom = last_drawing.get("geometry")
            try:
                poly = shape(geom)
                minx, miny, maxx, maxy = poly.bounds
                new_bbox = [round(minx, 4), round(miny, 4), round(maxx, 4), round(maxy, 4)]
                if new_bbox != st.session_state.current_bbox or geom != st.session_state.drawn_geometry:
                    st.session_state.current_bbox = new_bbox
                    st.session_state.drawn_geometry = geom
                    delta_deg = max(maxx - minx, maxy - miny)
                    st.session_state.map_center = [
                        round((miny + maxy) / 2.0, 5),
                        round((minx + maxx) / 2.0, 5)
                    ]
                    if delta_deg > 0:
                        st.session_state.map_zoom = max(8, min(15, round(math.log2(360.0 / delta_deg) - 1)))
                    # Limpiar clasificación previa y encuadre forzado para que el visor no salte a la posición anterior
                    st.session_state.classification_result = None
                    st.session_state.drainage_result = None
                    st.session_state.fit_bounds_target = None
            except Exception as e:
                st.warning(f"Error procesando geometría: {e}")

    # Consultar ubicación administrativa oficial y métricas si hay geometría activa
    has_selection = st.session_state.drawn_geometry is not None
    if has_selection:
        admin_info = cached_admin_location(tuple(st.session_state.current_bbox))
        loc_text = admin_info.get("texto_formateado", "Argentina")
        fuente_text = admin_info.get("fuente", "IGN Georef")

        # Estimación en tiempo real de dimensiones, cantidad de píxeles (10m) y superficie
        dim_info = estimate_bbox_dimensions(st.session_state.current_bbox)
        px_total_str = f"{dim_info['total_pixeles']:,}"
        ha_total_str = f"{dim_info['superficie_ha']:,.1f}"
        km2_total_str = f"{dim_info['superficie_km2']:,.1f}"
        grid_dim_str = f"{dim_info['pixeles_ancho']:,} x {dim_info['pixeles_alto']:,} px"

        # Estilos dinámicos según nivel de carga computacional
        badge_bg = "#f0fdf4" if dim_info["nivel"] == "optimo" else ("#fffbeb" if dim_info["nivel"] == "advertencia" else "#fef2f2")
        badge_border = "#bbf7d0" if dim_info["nivel"] == "optimo" else ("#fde68a" if dim_info["nivel"] == "advertencia" else "#fecaca")
        badge_left = "#16a34a" if dim_info["nivel"] == "optimo" else ("#d97706" if dim_info["nivel"] == "advertencia" else "#dc2626")

        st.markdown(
            f"""
            <div style="background-color: {badge_bg}; border: 1px solid {badge_border}; border-left: 4px solid {badge_left}; padding: 8px 12px; border-radius: 6px; margin-top: 6px; margin-bottom: 8px; font-size: 0.88rem; color: #1e293b;">
                📍 <b>BBox Activo:</b> <code>[Lon: {st.session_state.current_bbox[0]} a {st.session_state.current_bbox[2]}, Lat: {st.session_state.current_bbox[1]} a {st.session_state.current_bbox[3]}]</code><br>
                🏛️ <b>Ubicación:</b> <span style="font-weight: 600; color: #15803d;">{loc_text}</span> &nbsp;<span style="color: #64748b; font-size: 0.78rem;">({fuente_text})</span><br>
                📐 <b>Cálculo de Selección (10m):</b> <b>{px_total_str} píxeles</b> ({grid_dim_str}) &nbsp;|&nbsp; <b>{ha_total_str} ha</b> (~{km2_total_str} km²)
            </div>
            """,
            unsafe_allow_html=True
        )

        if dim_info["bloqueado"]:
            st.error(dim_info["mensaje"])
        elif dim_info["nivel"] == "advertencia":
            st.warning(dim_info["mensaje"])
        
        can_classify = not dim_info["bloqueado"]

        if can_classify:
            col_cfg_btn, col_drain_btn = st.columns([1.1, 1.3])
            if col_cfg_btn.button("⚙️ Clasificar Coberturas", type="primary", use_container_width=True):
                dialog_clasificacion()

            if col_drain_btn.button("🌊 Red de Drenaje y Pendientes", use_container_width=True, help="Descarga Copernicus DEM 30m y calcula líneas de escurrimiento con dirección e intensidad por pendiente"):
                with st.spinner("Descargando Copernicus DEM 30m y modelando red de drenaje superficial..."):
                    try:
                        d_res = analyze_drainage_and_slope(
                            bbox=st.session_state.current_bbox,
                            classification_context=st.session_state.classification_result
                        )
                        st.session_state.drainage_result = d_res
                        st.session_state.map_version += 1
                        if d_res.get("folium_bounds"):
                            st.session_state.fit_bounds_target = d_res["folium_bounds"]
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error al calcular drenaje hídrico: {e}")

    else:
        st.markdown(
            """
            <div style="background-color: #f8fafc; border: 1px solid #e2e8f0; border-left: 4px solid #64748b; padding: 8px 12px; border-radius: 6px; margin-top: 6px; margin-bottom: 8px; font-size: 0.88rem; color: #475569;">
                📍 <b>Estado del Visor:</b> <i>Sin rectángulo seleccionado. Trazá un rectángulo sobre el mapa satelital para definir tu área de análisis.</i>
            </div>
            """,
            unsafe_allow_html=True
        )
        can_classify = False

    st.markdown("---")

    # =========================================================
    # SECCIÓN 2: RESULTADOS, COBERTURAS E HIDROLOGÍA
    # =========================================================
    st.subheader("2. 📊 Resultados, Coberturas e Hidrología")

    has_class_res = st.session_state.classification_result is not None
    has_drain_res = st.session_state.get("drainage_result") is not None

    if has_class_res and has_drain_res:
        tab_cob, tab_drain = st.tabs(["🛰️ Coberturas del Suelo", "🌊 Hidrología y Red de Drenaje"])
    elif has_class_res:
        tab_cob, tab_drain = st.container(), None
    elif has_drain_res:
        tab_cob, tab_drain = None, st.container()
    else:
        tab_cob, tab_drain = None, None

    # ---------------------------------------------------------
    # TAB / SECCIÓN A: COBERTURAS DEL SUELO
    # ---------------------------------------------------------
    if tab_cob is not None:
        with tab_cob:
            res = st.session_state.classification_result
            col_hdr_1, col_hdr_2 = st.columns([1.5, 1.0])
            fecha_display = res.get("fecha_analizada") or res.get("año_referencia") or "N/A"
            col_hdr_1.markdown(f"#### 🛰️ Coberturas | 📅 `{fecha_display}` ({res.get('modelo')})")
            if col_hdr_2.button("🔄 Cambiar Método / Fecha", use_container_width=True):
                dialog_clasificacion()

            ub_res = res.get("ubicacion_administrativa") or cached_admin_location(tuple(st.session_state.current_bbox))
            if ub_res and ub_res.get("texto_formateado"):
                st.info(f"🏛️ **Jurisdicción Territorial:** {ub_res['texto_formateado']} *(Fuente: {ub_res.get('fuente', 'IGN Georef')})*")

            # Caso ESA WorldCover (8 Clases)
            if "WorldCover" in str(res.get("modelo")):
                coberturas = res["coberturas"]
                sorted_classes = sorted(coberturas.values(), key=lambda x: x["hectareas"], reverse=True)
                top_classes = sorted_classes[:4]
                
                cols = st.columns(len(top_classes))
                for i, c in enumerate(top_classes):
                    cols[i].metric(
                        c["nombre"].split("(")[0].strip(),
                        f"{c['porcentaje']}%",
                        f"{c['hectareas']:,.1f} ha"
                    )

                with st.expander("📋 Ver desglose completo de todas las clases taxonómicas"):
                    table_data = []
                    for c in sorted_classes:
                        table_data.append({
                            "Código": c["codigo"],
                            "Tipo de Cobertura": c["nombre"],
                            "Porcentaje (%)": f"{c['porcentaje']}%",
                            "Superficie (ha)": f"{c['hectareas']:,.1f}",
                            "Píxeles (10m)": f"{c['pixeles']:,}"
                        })
                    st.table(table_data)

            # Caso Sentinel-2 NDVI (3 Clases)
            else:
                m_col1, m_col2, m_col3, m_col4 = st.columns(4)
                veg = res["coberturas"]["vegetacion"]
                suelo = res["coberturas"]["suelo_desnudo"]
                agua = res["coberturas"].get("cuerpos_de_agua", {"porcentaje": 0.0, "hectareas": 0.0})
                
                m_col1.metric("🌿 Vegetación", f"{veg['porcentaje']}%", f"{veg['hectareas']:,.1f} ha")
                m_col2.metric("🏜️ Suelo Desnudo", f"{suelo['porcentaje']}%", f"{suelo['hectareas']:,.1f} ha")
                m_col3.metric("💧 Agua / Sombras", f"{agua['porcentaje']}%", f"{agua['hectareas']:,.1f} ha")
                m_col4.metric("📐 Superficie Total", f"{res['superficie_total_ha']:,.1f} ha")

            mapa_path = res.get("mapa_generado")
            if mapa_path and os.path.exists(mapa_path):
                st.image(mapa_path, caption=f"Detalle Temático de Clasificación | Fecha/Año: {fecha_display}", use_container_width=True)

    # ---------------------------------------------------------
    # TAB / SECCIÓN B: HIDROLOGÍA Y RED DE DRENAJE
    # ---------------------------------------------------------
    if tab_drain is not None:
        with tab_drain:
            d_res = st.session_state.drainage_result
            col_dh1, col_dh2 = st.columns([1.5, 1.0])
            col_dh1.markdown("#### 🌊 Red de Drenaje y Pendientes (Copernicus DEM 30m)")
            if col_dh2.button("🔄 Recalcular Drenaje", use_container_width=True):
                with st.spinner("Recalculando modelo de drenaje superficial..."):
                    try:
                        d_res = analyze_drainage_and_slope(
                            bbox=st.session_state.current_bbox,
                            classification_context=st.session_state.classification_result
                        )
                        st.session_state.drainage_result = d_res
                        st.session_state.map_version += 1
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error: {e}")

            # Métricas Topográficas Principales
            dc1, dc2, dc3, dc4 = st.columns(4)
            dc1.metric("⛰️ Desnivel", f"{d_res['elevacion']['desnivel_m']} m", f"Cotas: {d_res['elevacion']['minima_msnm']} a {d_res['elevacion']['maxima_msnm']} m")
            dc2.metric("📐 Pendiente Media", f"{d_res['pendientes']['media_pct']}%", f"Máx: {d_res['pendientes']['maxima_pct']}%")
            dc3.metric("🧭 Rumbo de Flujo", f"{d_res['direccion_flujo']['rumbo_cardinal']}", f"Acimut: {d_res['direccion_flujo']['acimut_grados']}°")
            dc4.metric("📐 Superficie", f"{d_res['superficie_total_ha']:,.1f} ha", "Copernicus 30m")

            # Diagnóstico Agrohidrológico y Recomendación
            if d_res.get("analisis_agrohidrologico") and d_res["analisis_agrohidrologico"].get("riesgo_erosion_hidrica"):
                agro = d_res["analisis_agrohidrologico"]
                st.markdown(
                    f"""
                    <div style="background-color: #eff6ff; border: 1px solid #bfdbfe; border-left: 4px solid #2563eb; padding: 8px 12px; border-radius: 6px; margin-top: 6px; margin-bottom: 10px; font-size: 0.88rem; color: #1e3a8a;">
                        🌊 <b>Evaluación de Riesgo de Erosión Hídrica:</b> <b>{agro.get('riesgo_erosion_hidrica')}</b><br>
                        💡 <b>Recomendación de Manejo:</b> {agro.get('recomendacion_conservacion')}
                    </div>
                    """,
                    unsafe_allow_html=True
                )

            with st.expander("📋 Ver distribución cuantitativa por rangos de pendiente"):
                dist = d_res["pendientes"]["distribucion"]
                table_dist = []
                for k, v in dist.items():
                    table_dist.append({
                        "Rango de Pendiente": v["nombre"],
                        "Dinámica / Escurrimiento": v["descripcion"],
                        "Superficie (ha)": f"{v['hectareas']:,.1f}",
                        "Porcentaje (%)": f"{v['porcentaje']}%"
                    })
                st.table(table_dist)

            d_mapa_path = d_res.get("mapa_generado")
            if d_mapa_path and os.path.exists(d_mapa_path):
                st.image(d_mapa_path, caption="Topografía 3D, Líneas de Drenaje Hídrico y Zonificación de Pendientes", use_container_width=True)

    if not has_class_res and not has_drain_res:
        if has_selection and can_classify:
            st.info("💡 **Área delimitada lista.** Presioná **'⚙️ Clasificar Coberturas'** para identificar el uso del suelo o **'🌊 Red de Drenaje y Pendientes'** para modelar el escurrimiento hídrico.")
        else:
            st.info("📍 Trazá un rectángulo sobre el mapa satelital para habilitar la clasificación de coberturas y la red de drenaje.")

# -------------------------------------------------------------
# COLUMNA DERECHA: ASISTENTE (CONSULTAS Y RAG)
# -------------------------------------------------------------
with col_right:
    st.subheader("3. 🤖 Asistente (Consultas y RAG)")
    
    # Verificar si el cliente LLM está conectado y mostrar badge informativo
    agent_inst = st.session_state.agent
    if agent_inst.client is None:
        agent_inst.client = agent_inst._init_client()
        
    if agent_inst.client is not None:
        st.caption(f"🟢 **LLM Conectado:** `{agent_inst.model}` (Inferencia Activa)")
    else:
        st.caption("🟡 **Modo Local:** Motor de Contingencia (Sin API Key / Fallback)")

    q_col1, q_col2, q_col3 = st.columns([1.1, 1.3, 1.1])
    preset_query = None
    if q_col1.button("📉 Coberturas", use_container_width=True):
        preset_query = "Analizá y diagnosticá la distribución cuantitativa de coberturas obtenidas por el modelo en el área seleccionada, indicando superficies en hectáreas, porcentajes y su balance agroambiental."
    if q_col2.button("🌊 Drenaje y Pendiente", use_container_width=True):
        preset_query = "Analizá y diagnosticá la red de drenaje hídrico superficial, pendientes (%) y dirección de escurrimiento en el área seleccionada, indicando el riesgo de erosión hídrica en sectores productivos."
    if q_col3.button("🛠️ Stack y Código", use_container_width=True):
        preset_query = "Explicá el stack tecnológico utilizado para construir esta app, su arquitectura modular y cómo intervenir o modificar el código según la guía del proyecto."

    chat_container = st.container(height=450)
    with chat_container:
        if not st.session_state.chat_history:
            st.info("👋 Podés hacer consultas en lenguaje natural para que el asistente interprete los datos cuantitativos clasificados, evalúe la red de drenaje hídrico o explique cómo intervenir el código de la app.")

        for chat in st.session_state.chat_history:
            with st.chat_message(chat["role"]):
                st.markdown(chat["content"])

                if chat.get("trace"):
                    with st.expander("🔍 Ver Traza de Razonamiento ReAct"):
                        for step in chat["trace"]:
                            st.markdown(f"**Paso {step['step']}:** `{step.get('action') or 'Respuesta Final'}`")
                            st.text(step["thought_and_output"])
                            if step.get("observation"):
                                st.caption("Observación:")
                                st.text(str(step["observation"])[:300])

    user_input = st.chat_input("Escribí tu consulta técnica...")
    query_to_run = preset_query or user_input

    if query_to_run:
        admin_context = cached_admin_location(tuple(st.session_state.current_bbox)).get("texto_formateado", "Argentina")
        final_query = f"{query_to_run} [BBox activo: {st.session_state.current_bbox}] [Ubicación Administrativa: {admin_context}]"
        if st.session_state.classification_result:
            final_query += f" [Última Clasificación: {json.dumps(st.session_state.classification_result)}]"
        if st.session_state.get("drainage_result"):
            final_query += f" [Último Análisis de Drenaje Hídrico: {json.dumps(st.session_state.drainage_result)}]"

        st.session_state.chat_history.append({"role": "user", "content": query_to_run})

        with st.spinner("🤖 El asistente está razonando e integrando evidencia..."):
            answer, trace = st.session_state.agent.run(final_query)

            st.session_state.chat_history.append({
                "role": "assistant",
                "content": answer,
                "trace": trace
            })
            st.rerun()

