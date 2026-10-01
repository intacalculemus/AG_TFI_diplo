"""
Frontend Interactivo con Selección Territorial en Mapa y Asistente ReAct Geoespacial
Soporta:
1. Modelo de IA Deep Learning: ESA WorldCover (10m de resolución - 8+ clases de cobertura)
2. Umbralización Radiométrica: NDVI Sentinel-2 L2A (Bandas B04 y B08 a 10m)
Superposición Georreferenciada Directa sobre el Mapa (ImageOverlay)
Diplomatura Universitaria ISBIA - Lidesia - UNC / Grupo_6_2026
"""
import streamlit as st
import folium
from folium.plugins import Draw
from folium.raster_layers import ImageOverlay
from streamlit_folium import st_folium
import json
import os
from pathlib import Path
from shapely.geometry import shape

from agent.core import GeoReActAgent
from tools.base import default_registry
from services.real_satellite_service import (
    search_real_scenes,
    fetch_and_classify_real_scene,
    classify_with_esa_worldcover,
    DEFAULT_BBOX,
    ESA_WORLDCOVER_CLASSES
)
from services.geo_admin_service import get_location_for_bbox, get_administrative_location
from config import OUTPUTS_DIR
import datetime

@st.cache_data(show_spinner=False, ttl=3600)
def cached_admin_location(bbox_tuple: tuple):
    return get_location_for_bbox(list(bbox_tuple))

st.set_page_config(
    layout="wide",
    page_title="TFI_Grupo_6_2026: Clasificación de Coberturas del suelo con Agentes IA",
    page_icon="🛰️"
)

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

# Encabezado y Subtítulo enriquecido con Stack Tecnológico y Timestamp de Compilación
st.title("🛰️ TFI_Grupo_6_2026: Clasificación de Coberturas del suelo con Agentes IA")
st.caption(f"⏱️ **Última compilación / actualización:** `{last_update_str}` | Diplomatura Universitaria ISBIA - Lidesia - FCEFyN (UNC) / Grupo_6_2026")
st.caption("🧩 **Arquitectura & Stack:** **Frontend:** Streamlit + Folium (GIS) | **Datos & Teledetección:** STAC API (Planetary Computer) & Rasterio (COGs) | **Agente Inteligente:** ReAct (*Reasoning + Acting*) + RAG Documental Local | **Modelos:** ESA WorldCover 10m (Deep Learning CNN) & Sentinel-2 MSI")

col_left, col_right = st.columns([1.22, 1.0], gap="large")

# -------------------------------------------------------------
# COLUMNA IZQUIERDA: MAPA INTERACTIVO Y CLASIFICACIÓN CON IA
# -------------------------------------------------------------
with col_left:
    st.subheader("1. 🗺️ Delimitación Territorial sobre el Mapa (Visor Satelital)")
    st.markdown(
        "Punto inicial: **Laguna Mar Chiquita (Córdoba)**. El visor conserva siempre tu última posición y nivel de zoom. "
        "Dibuja un **rectángulo** para definir tu área de interés:"
    )

    # Controles de Encuadre y Zoom del Visor
    col_zoom1, col_zoom2 = st.columns([1.4, 1.0])
    btn_fit_area = col_zoom1.button("🎯 Centrar y Maximizar Área", use_container_width=True)
    btn_reset_mar = col_zoom2.button("🌊 Reset: Mar Chiquita", use_container_width=True)

    if btn_fit_area:
        st.session_state.map_version += 1
        if st.session_state.classification_result and st.session_state.classification_result.get("folium_bounds"):
            target_b = st.session_state.classification_result["folium_bounds"]
        else:
            bbox = st.session_state.current_bbox
            target_b = [[bbox[1], bbox[0]], [bbox[3], bbox[2]]]
        st.session_state.fit_bounds_target = target_b
        st.session_state.map_center = [
            round((target_b[0][0] + target_b[1][0]) / 2.0, 5),
            round((target_b[0][1] + target_b[1][1]) / 2.0, 5)
        ]
        st.rerun()

    if btn_reset_mar:
        st.session_state.map_version += 1
        st.session_state.map_center = MAR_CHIQUITA_CENTER
        st.session_state.map_zoom = MAR_CHIQUITA_ZOOM
        st.session_state.current_bbox = DEFAULT_BBOX
        st.session_state.drawn_geometry = None
        st.session_state.fit_bounds_target = None
        st.session_state.classification_result = None
        st.rerun()

    # Crear mapa folium con la imagen satelital por defecto (Google Satellite)
    m = folium.Map(
        location=st.session_state.map_center,
        zoom_start=st.session_state.map_zoom,
        tiles="https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}",
        attr="Google Satellite",
        control_scale=True
    )

    # Si se solicitó centrar y maximizar el área clasificada / AOI
    if st.session_state.fit_bounds_target:
        m.fit_bounds(st.session_state.fit_bounds_target)

    # Renderizar el rectángulo delimitado activo para clasificación
    active_geom = st.session_state.drawn_geometry
    if not active_geom:
        minx, miny, maxx, maxy = st.session_state.current_bbox
        active_geom = {
            "type": "Polygon",
            "coordinates": [[
                [minx, miny],
                [maxx, miny],
                [maxx, maxy],
                [minx, maxy],
                [minx, miny]
            ]]
        }

    folium.GeoJson(
        active_geom,
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
        fecha_overlay = res_prev.get("fecha_analizada") or res_prev.get("año_referencia") or "Procesada"
        
        if overlay_path and os.path.exists(overlay_path) and f_bounds:
            ImageOverlay(
                name=f"🛰️ Coberturas ({fecha_overlay})",
                image=overlay_path,
                bounds=f_bounds,
                opacity=0.75,
                interactive=True,
                cross_origin=False,
                zindex=10
            ).add_to(m)

    # Herramienta de dibujo (Draw) - Solo Rectángulo
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
        }
    )
    draw.add_to(m)
    folium.LayerControl(position="topright", collapsed=True).add_to(m)

    # Configurar returned_objects=['last_active_drawing'] y key dinámica con map_version
    map_output = st_folium(
        m, 
        width="100%", 
        height=420, 
        returned_objects=["last_active_drawing"],
        key=f"main_map_{st.session_state.map_version}"
    )

    # Extraer Bounding Box y Geometría únicamente cuando el usuario realiza un nuevo dibujo
    if map_output and map_output.get("last_active_drawing"):
        drawing = map_output["last_active_drawing"]
        geom = drawing.get("geometry")
        if geom:
            try:
                poly = shape(geom)
                minx, miny, maxx, maxy = poly.bounds
                new_bbox = [round(minx, 4), round(miny, 4), round(maxx, 4), round(maxy, 4)]
                if new_bbox != st.session_state.current_bbox or geom != st.session_state.drawn_geometry:
                    st.session_state.current_bbox = new_bbox
                    st.session_state.drawn_geometry = geom
                    # Actualizar centro según el nuevo dibujo
                    st.session_state.map_center = [
                        round((miny + maxy) / 2.0, 5),
                        round((minx + maxx) / 2.0, 5)
                    ]
                    st.session_state.classification_result = None
                    st.rerun()
            except Exception as e:
                st.warning(f"Error procesando geometría: {e}")

    # Consultar ubicación administrativa oficial para el BBox activo
    admin_info = cached_admin_location(tuple(st.session_state.current_bbox))
    loc_text = admin_info.get("texto_formateado", "Argentina")
    fuente_text = admin_info.get("fuente", "IGN Georef")

    st.markdown(
        f"""
        <div style="background-color: #f0fdf4; border: 1px solid #bbf7d0; border-left: 4px solid #16a34a; padding: 7px 12px; border-radius: 6px; margin-top: 6px; margin-bottom: 12px; font-size: 0.88rem; color: #1e293b;">
            📍 <b>BBox Activo:</b> <code>[Lon: {st.session_state.current_bbox[0]} a {st.session_state.current_bbox[2]}, Lat: {st.session_state.current_bbox[1]} a {st.session_state.current_bbox[3]}]</code><br>
            🏛️ <b>Ubicación Administrativa (Argentina):</b> <span style="font-weight: 600; color: #15803d;">{loc_text}</span> &nbsp;<span style="color: #64748b; font-size: 0.78rem;">({fuente_text})</span>
        </div>
        """,
        unsafe_allow_html=True
    )

    st.markdown("---")

    # =========================================================
    # SECCIÓN 2: CLASIFICACIÓN DE COBERTURAS Y RESULTADOS
    # =========================================================
    st.subheader("2. 🔬 Clasificación de Coberturas (Modelos de IA & Umbrales Radiométricos)")
    st.markdown(
        "Configura el método de clasificación y analiza los resultados cuantitativos correspondientes:"
    )

    engine_choice = st.radio(
        "Seleccioná el método de clasificación a utilizar:",
        options=[
            "🧠 Modelo IA Deep Learning: ESA WorldCover (10m - 8+ Clases: Bosque, Cultivo, Matorral, Pastizal, Agua, etc.)",
            "⚡ Umbralización Radiométrica: NDVI Sentinel-2 L2A (10m - Vegetación / Suelo / Agua)"
        ],
        index=0
    )

    # ---------------------------------------------------------
    # RAMA A: MODELO DE IA DEEP LEARNING (ESA WORLDCOVER)
    # ---------------------------------------------------------
    if "WorldCover" in engine_choice:
        col_wc1, col_wc2 = st.columns([1, 1.4])
        wc_year = col_wc1.selectbox("📅 Año de la Imagen Satelital / Modelo:", ["2021", "2020"], index=0)
        
        classify_wc_btn = col_wc2.button(
            f"🚀 Ejecutar Modelo de IA: ESA WorldCover ({wc_year})", 
            type="primary", 
            use_container_width=True
        )

        if classify_wc_btn:
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
    # RAMA B: UMBRALIZACIÓN RADIOMÉTRICA (SENTINEL-2 L2A)
    # ---------------------------------------------------------
    else:
        st.markdown("##### 🕒 Selector de Imágenes Históricas y Parámetros Espectrales")
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

        col_s2_1, col_s2_2 = st.columns([1, 1.4])
        ndvi_thresh = col_s2_1.slider("Umbral NDVI Vegetación:", 0.20, 0.60, 0.35, 0.05)

        if selected_label:
            selected_scene = options_dict[selected_label]
            st.info(f"📅 **Fecha seleccionada:** `{selected_scene['fecha']}` | **Satélite:** `{selected_scene['satelite']}` | **Nubosidad:** `{selected_scene['cobertura_nubes_pct']}%`")

            classify_s2_btn = col_s2_2.button(
                f"🚀 Procesar Bandas B04/B08 ({selected_scene['fecha']}) a 10m", 
                type="primary", 
                use_container_width=True
            )

            if classify_s2_btn:
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

    # ---------------------------------------------------------
    # RENDERIZADO DE RESULTADOS DENTRO DE LA SECCIÓN DE CLASIFICACIÓN
    # ---------------------------------------------------------
    if st.session_state.classification_result:
        res = st.session_state.classification_result
        
        fecha_display = res.get("fecha_analizada") or res.get("año_referencia") or "N/A"
        st.markdown(f"#### 📊 Resultados del Análisis | 📅 Fecha/Año: `{fecha_display}` ({res.get('modelo')})")

        ub_res = res.get("ubicacion_administrativa") or cached_admin_location(tuple(st.session_state.current_bbox))
        if ub_res and ub_res.get("texto_formateado"):
            st.info(f"🏛️ **Jurisdicción Territorial:** {ub_res['texto_formateado']} *(Fuente: {ub_res.get('fuente', 'IGN Georef')})*")

        # Caso ESA WorldCover (8 Clases)
        if "WorldCover" in str(res.get("modelo")):
            coberturas = res["coberturas"]
            
            # Mostrar las clases principales en métricas
            sorted_classes = sorted(coberturas.values(), key=lambda x: x["hectareas"], reverse=True)
            top_classes = sorted_classes[:4]
            
            cols = st.columns(len(top_classes))
            for i, c in enumerate(top_classes):
                cols[i].metric(
                    c["nombre"].split("(")[0].strip(),
                    f"{c['porcentaje']}%",
                    f"{c['hectareas']:,.1f} ha"
                )

            # Tabla completa de clases
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

        with st.expander("🌐 Verificación de Georreferenciación"):
            coords = res["coordenadas_exactas_raster"]
            st.write(f"**BBox Solicitado:** `{coords['bbox_solicitado']}`")
            st.write(f"**Límites del Ráster (EPSG:4326):** `{coords['geo_bounds_reales']}`")
            st.write(f"**Límites de Superposición Folium:** `{coords['folium_bounds']}`")
            st.success("✅ Capa proyectada directamente sobre el mapa satelital.")

        mapa_path = res.get("mapa_generado")
        if mapa_path and os.path.exists(mapa_path):
            st.image(mapa_path, caption=f"Detalle Temático de Clasificación | Fecha/Año: {fecha_display}", use_container_width=True)

# -------------------------------------------------------------
# COLUMNA DERECHA: ASISTENTE (CONSULTAS Y RAG)
# -------------------------------------------------------------
with col_right:
    st.subheader("3. 🤖 Asistente (Consultas y RAG)")

    q_col1, q_col2 = st.columns(2)
    preset_query = None
    if q_col1.button("📉 Diagnóstico de Coberturas"):
        preset_query = "Analizá y diagnosticá la distribución cuantitativa de coberturas obtenidas por el modelo en el área seleccionada, indicando superficies en hectáreas, porcentajes y su balance agroambiental."
    if q_col2.button("🛠️ Stack y Arquitectura"):
        preset_query = "Explicá el stack tecnológico utilizado para construir esta app, su arquitectura modular y cómo intervenir o modificar el código según la guía del proyecto."

    chat_container = st.container(height=450)
    with chat_container:
        if not st.session_state.chat_history:
            st.info("👋 Podés hacer consultas en lenguaje natural para que el asistente interprete los datos cuantitativos clasificados o explique cómo intervenir el código de la app.")

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

        st.session_state.chat_history.append({"role": "user", "content": query_to_run})

        with st.spinner("🤖 El asistente está razonando e integrando evidencia..."):
            answer, trace = st.session_state.agent.run(final_query)

            st.session_state.chat_history.append({
                "role": "assistant",
                "content": answer,
                "trace": trace
            })
            st.rerun()
