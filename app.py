"""
Frontend Interactivo con Selección Territorial en Mapa y Asistente ReAct Geoespacial
Soporta:
1. Modelo de IA Deep Learning: ESA WorldCover (10m de resolución - 8+ clases de cobertura)
2. Umbralización Radiométrica: NDVI Sentinel-2 L2A (Bandas B04 y B08 a 10m)
Superposición Georreferenciada Directa sobre el Mapa (ImageOverlay)
Desarrollo, implementación y despliegue (asistido con IA): Dr. Federico J. Letourneau (IFAB INTA - CONICET)
Desarrollo conceptual: Discusión colaborativa del Grupo 6 (2026)
Diplomatura Universitaria ISBIA - Lidesia - FCEFyN (UNC) | Directora: Dra. Laura Cecilia Díaz Dávila
"""
import streamlit as st

st.set_page_config(
    layout="wide",
    page_title="TFI_Grupo_6_2026: Clasificación de Coberturas del suelo con Agentes IA",
    page_icon="🛰️",
    initial_sidebar_state="expanded"
)

import folium
from folium.plugins import Draw
from folium.raster_layers import ImageOverlay
from streamlit_folium import st_folium
import json
import os
import math
from pathlib import Path
import importlib
import sys
from shapely.geometry import shape

# Recarga defensiva ante hot-reload en caliente de Streamlit Cloud tras un git push
import services.real_satellite_service as _rss_mod
import services.drainage_service as _ds_mod
import rag.vector_store as _rag_vs_mod
import agent.core as _agent_core_mod
if (
    not hasattr(_rss_mod, "discover_available_sources")
    or not hasattr(_rss_mod, "IO_LULC_CLASSES")
    or not hasattr(_rss_mod, "fetch_landcover_reference_for_bbox")
    or not hasattr(_ds_mod, "SLOPE_BINS")
    or not hasattr(_rag_vs_mod, "_normalize_text")
    or not hasattr(_agent_core_mod.GeoReActAgent, "_requires_rag_grounding")
    or not hasattr(_agent_core_mod.GeoReActAgent, "_extract_tagged_json")
):
    for _mod_name in [
        "config",
        "services.real_satellite_service",
        "services.drainage_service",
        "rag.vector_store",
        "tools.base",
        "tools.land_cover",
        "tools.drainage",
        "tools.geo_catalog",
        "tools.rag_search",
        "tools",
        "agent.security",
        "agent.prompts",
        "agent.core",
        "agent.harness",
    ]:
        if _mod_name in sys.modules:
            importlib.reload(sys.modules[_mod_name])

from agent.core import GeoReActAgent
from agent.harness import run_evaluation_harness
from agent.security import get_security_and_sandbox_status
from tools.base import default_registry
from services.real_satellite_service import (
    search_real_scenes,
    fetch_and_classify_real_scene,
    classify_with_esa_worldcover,
    discover_available_sources,
    estimate_bbox_dimensions,
    DEFAULT_BBOX,
    ESA_WORLDCOVER_CLASSES,
    IO_LULC_CLASSES
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

@st.cache_data(show_spinner=False, ttl=3600)
def cached_sources_catalog(bbox_tuple: tuple, sync_version: int = 0):
    """Descubre y cachea (TTL 1h) las colecciones, años y fechas disponibles en STAC para el BBox."""
    return discover_available_sources(list(bbox_tuple))

@st.dialog("🔬 Configurar y Ejecutar Clasificación", width="large")
def dialog_clasificacion():
    """Cuadro de diálogo modal para configurar y lanzar la clasificación del área seleccionada."""
    admin_info = cached_admin_location(tuple(st.session_state.current_bbox))
    loc_text = admin_info.get("texto_formateado", "Argentina")
    fuente_text = admin_info.get("fuente", "IGN Georef")
    dim_info = estimate_bbox_dimensions(st.session_state.current_bbox)
    sync_ver = st.session_state.get("stac_sync_version", 0)

    with st.spinner("Sincronizando catálogo STAC (años y fechas disponibles)..."):
        sources_info = cached_sources_catalog(tuple(st.session_state.current_bbox), sync_ver)

    st.markdown(
        f"""
        <div style="background-color: #f0fdf4; border: 1px solid #bbf7d0; border-left: 4px solid #16a34a; padding: 6px 12px; border-radius: 6px; margin-bottom: 8px; font-size: 0.88rem; color: #1e293b;">
            📍 <b>Área a Clasificar:</b> <b>{dim_info['superficie_ha']:,.1f} ha</b> ({dim_info['total_pixeles']:,} px a 10m) &nbsp;|&nbsp; 🏛️ <b>Ubicación:</b> <span style="font-weight: 600; color: #15803d;">{loc_text}</span> <span style="color: #64748b; font-size: 0.78rem;">({fuente_text})</span>
        </div>
        """,
        unsafe_allow_html=True
    )

    # Barra de estado de sincronización STAC + botón manual de refresco
    col_sync_info, col_sync_btn = st.columns([2.7, 1.1])
    stac_badge = "🟢 STAC Online" if sources_info.get("stac_online") else "🟡 Modo Caché Local"
    s2_last = sources_info.get("sentinel2", {}).get("latest_scene_date", "N/A")
    col_sync_info.caption(
        f"📡 **{stac_badge}** | Sincronizado: `{sources_info.get('synced_at')}` | "
        f"Última escena S2 en zona: `{s2_last}`"
    )
    if col_sync_btn.button("🔄 Sincronizar fuentes STAC", use_container_width=True, help="Consulta en vivo Microsoft Planetary Computer STAC para actualizar años y fechas disponibles"):
        st.session_state.stac_sync_version = sync_ver + 1
        cached_sources_catalog.clear()
        st.rerun()

    engine_choice = st.radio(
        "Seleccioná el método de clasificación:",
        options=[
            "🧠 Modelo IA Deep Learning 10m (ESA WorldCover / Esri Annual LULC - Multiclase)",
            "⚡ Umbralización Radiométrica: NDVI Sentinel-2 L2A (10m - Vegetación / Suelo / Agua)"
        ],
        index=0
    )

    # ---------------------------------------------------------
    # RAMA A: MODELO IA DEEP LEARNING (ESA WORLDCOVER + ESRI 10M LULC)
    # ---------------------------------------------------------
    if "Modelo IA" in engine_choice or "WorldCover" in engine_choice:
        st.markdown("---")
        col_src, col_yr = st.columns([1.6, 1.0])
        ai_collection_map = {
            "🌎 Esri / Impact Observatory 10m Annual LULC (Serie Anual Multitemporal)": "io-lulc-annual-v02",
            "🌍 ESA WorldCover 10m (ESA/VITO - Alta Precisión Taxonómica)": "esa-worldcover",
        }
        selected_ai_label = col_src.selectbox(
            "🛰️ Fuente / Colección de IA en STAC:",
            options=list(ai_collection_map.keys()),
            index=0
        )
        chosen_coll_id = ai_collection_map[selected_ai_label]

        if chosen_coll_id == "esa-worldcover":
            available_ai_years = sources_info.get("esa_worldcover", {}).get("years", ["2021", "2020"])
            info_msg = (
                f"💡 **ESA WorldCover 10m (`esa-worldcover`):** Clasificación en 11 clases taxonómicas (ESA/VITO). "
                f"Años detectados en STAC para esta zona: `{', '.join(available_ai_years)}`."
            )
        else:
            available_ai_years = sources_info.get("io_lulc", {}).get("years", ["2023", "2022", "2021", "2020", "2019", "2018", "2017"])
            info_msg = (
                f"💡 **Esri / Impact Observatory 10m LULC (`io-lulc-annual-v02`):** Serie anual continua entrenada sobre Sentinel-2 en 9 clases. "
                f"Años detectados en STAC para esta zona: `{', '.join(available_ai_years)}`."
            )

        wc_year = col_yr.selectbox("📅 Año disponible en STAC:", available_ai_years, index=0)
        st.info(info_msg)

        st.markdown("<br>", unsafe_allow_html=True)
        short_model_btn = "ESA WorldCover" if chosen_coll_id == "esa-worldcover" else "Esri 10m Annual LULC"
        if st.button(f"🚀 Ejecutar Modelo de IA: {short_model_btn} ({wc_year})", type="primary", use_container_width=True):
            with st.spinner(f"Ejecutando inferencia de {short_model_btn} (10m) para el año {wc_year}..."):
                try:
                    res = classify_with_esa_worldcover(
                        bbox=st.session_state.current_bbox,
                        year=wc_year,
                        collection_id=chosen_coll_id
                    )
                    st.session_state.classification_result = res
                    st.session_state.map_version += 1
                    if res.get("folium_bounds"):
                        st.session_state.fit_bounds_target = res["folium_bounds"]
                    st.rerun()
                except Exception as e:
                    st.error(f"Error al ejecutar modelo de IA ({short_model_btn}): {e}")

    # ---------------------------------------------------------
    # RAMA B: RADIOMETRÍA SENTINEL-2 L2A (AÑO DINÁMICO + RANGO PERSONALIZADO)
    # ---------------------------------------------------------
    else:
        st.markdown("---")
        st.markdown("##### 🕒 Selector Dinámico de Fechas y Parámetros Espectrales (Sentinel-2 L2A)")

        s2_meta = sources_info.get("sentinel2", {})
        dynamic_s2_years = s2_meta.get("years", [str(y) for y in range(datetime.date.today().year, 2016, -1)])
        today_dt = datetime.date.today()
        min_dt_allowed = datetime.date(2017, 1, 1)

        search_mode = st.radio(
            "Modo de búsqueda temporal en STAC:",
            options=[
                "📅 Por Año (2017 – Presente, actualizado automáticamente)",
                "📆 Rango de Fechas Personalizado (Desde / Hasta)"
            ],
            horizontal=True,
            index=0
        )

        if "Por Año" in search_mode:
            col_hist1, col_hist2, col_hist3 = st.columns([1, 1, 1])
            hist_year = col_hist1.selectbox("Año (Dinámico):", dynamic_s2_years, index=0)
            max_clouds = col_hist2.slider("Nubosidad Máx. (%):", 0.0, 50.0, 15.0, 5.0)
            limite_escenas = col_hist3.selectbox("Cant. Escenas:", [5, 10, 15, 25], index=1)
            date_range_query = f"{hist_year}-01-01/{hist_year}-12-31"
            period_label = f"el año {hist_year}"
        else:
            col_d1, col_d2, col_d3, col_d4 = st.columns([1.05, 1.05, 1.0, 0.8])
            default_start = max(min_dt_allowed, today_dt - datetime.timedelta(days=120))
            start_date_val = col_d1.date_input(
                "Fecha Desde:",
                value=default_start,
                min_value=min_dt_allowed,
                max_value=today_dt
            )
            end_date_val = col_d2.date_input(
                "Fecha Hasta:",
                value=today_dt,
                min_value=min_dt_allowed,
                max_value=today_dt
            )
            max_clouds = col_d3.slider("Nubosidad Máx. (%):", 0.0, 50.0, 15.0, 5.0)
            limite_escenas = col_d4.selectbox("Cant. Escenas:", [5, 10, 15, 25], index=1)

            if start_date_val > end_date_val:
                st.warning("⚠️ La 'Fecha Desde' no puede ser posterior a la 'Fecha Hasta'. Se ajustó automáticamente.")
                start_date_val = end_date_val

            date_range_query = f"{start_date_val.strftime('%Y-%m-%d')}/{end_date_val.strftime('%Y-%m-%d')}"
            period_label = f"el período {start_date_val.strftime('%Y-%m-%d')} a {end_date_val.strftime('%Y-%m-%d')}"

        with st.spinner(f"Consultando catálogo STAC para escenas en {period_label}..."):
            real_scenes = search_real_scenes(
                bbox=st.session_state.current_bbox,
                date_range=date_range_query,
                max_cloud=max_clouds,
                limit=limite_escenas
            )

        if not real_scenes:
            st.warning(f"No se encontraron escenas con menos del {max_clouds}% de nubes en {period_label}. Probá ampliando el rango de fechas o aumentando el umbral de nubes.")
        
        options_dict = {
            f"📅 {s['fecha']} | {s['satelite']} (Nubes: {s['cobertura_nubes_pct']}%)": s
            for s in real_scenes
        }

        selected_label = st.selectbox(
            "Seleccioná la escena Sentinel-2 a procesar:",
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


@st.dialog("🛡️ Auditoría: Agent Harness, Ciberseguridad, Sandbox y Contenedores", width="large")
def dialog_harness_seguridad():
    """Panel interactivo de auditoría de Ingeniería de IA para la Diplomatura ISBIA."""
    sec_info = get_security_and_sandbox_status()
    st.markdown(
        """
        <div style="background-color: #f8fafc; border: 1px solid #cbd5e1; border-left: 4px solid #0284c7; padding: 10px 14px; border-radius: 6px; margin-bottom: 12px; font-size: 0.88rem; color: #1e293b;">
            <b>Arquitectura de Capas Desacopladas (ISBIA - FCEFyN UNC):</b> El núcleo del agente <code>GeoReActAgent</code> se encuentra envuelto por cuatro capas de ingeniería que garantizan control determinístico, ciberseguridad y aislamiento en la nube.
        </div>
        """,
        unsafe_allow_html=True
    )

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("##### 🛡️ 1. Ciberseguridad (OWASP LLM Top 10)")
        st.caption(f"• **Input Guardrail:** {sec_info['input_guardrail']}")
        st.caption(f"• **Output Guardrail:** {sec_info['output_guardrail']}")
        st.markdown("##### ⚙️ 2. Agent Harness (Orquestación & Eval)")
        st.caption("• **Runtime Harness:** Control de bucle (`max_steps=7`), parser Regex determinista, telemetría de latencia y motor de contingencia local.")
    with c2:
        st.markdown("##### 🔒 3. Sandbox de Ejecución")
        st.caption(f"• **Sandbox de Herramientas:** {sec_info['tool_sandbox']}")
        st.caption(f"• **Cuota Máx. de Superficie RAM:** `{sec_info['sandbox_max_area_ha']:,.0f} ha` por consulta satelital COG.")
        st.markdown("##### 📦 4. Contenedores (Cloud / Docker)")
        st.caption("• **Despliegue Dual:** Contenedor Linux aislado en *Streamlit Cloud* + especificación `Dockerfile` (`non-root appuser`, `mem_limit: 2g`) para servidores de INTA.")

    st.markdown("---")
    st.markdown("#### 📊 Telemetría en Vivo de la Sesión Actual (Runtime Harness)")
    sess_m = getattr(st.session_state.agent, "session_metrics", {}) or {}
    q_cnt = sess_m.get("queries_count", 0)
    avg_lat = round(sess_m.get("total_latency_ms", 0.0) / q_cnt, 1) if q_cnt > 0 else 0.0
    sm1, sm2, sm3, sm4 = st.columns(4)
    sm1.metric("💬 Consultas Sesión", f"{q_cnt}")
    sm2.metric("🪙 Tokens Consumidos", f"{sess_m.get('total_tokens', 0):,}", f"Prompt: {sess_m.get('prompt_tokens', 0):,} | Out: {sess_m.get('completion_tokens', 0):,}")
    sm3.metric("⏱️ Latencia Media", f"{avg_lat} ms")
    sm4.metric("🛠️ Tools / Bloqueos", f"{sess_m.get('tools_invoked', 0)} tools", f"{sess_m.get('security_blocks', 0)} bloqueos")

    st.markdown("---")
    st.markdown("#### 🧪 Banco de Pruebas Automatizado (*Agent Evaluation Harness*)")
    st.caption("Ejecuta en vivo el *Golden Dataset* (7 casos de prueba) para verificar selección de herramientas, grounding RAG, cumplimiento del protocolo ReAct, bloqueo de *Prompt Injection* y frenado del *Sandbox* ante sobrecarga de memoria o *Path Traversal*.")

    if st.button("▶️ Ejecutar Batería de Pruebas (Eval Harness & Seguridad)", type="primary", use_container_width=True):
        with st.spinner("Ejecutando Golden Dataset sobre el Agente y las capas de Seguridad/Sandbox..."):
            st.session_state.harness_report = run_evaluation_harness(use_deterministic_mode=True)

    if st.session_state.get("harness_report"):
        rep = st.session_state.harness_report
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("✅ Casos Aprobados", f"{rep['aprobados']}/{rep['total_tests']}")
        m2.metric("🎯 Tasa de Éxito", f"{rep['tasa_exito_pct']}%")
        m3.metric("📐 Protocolo ReAct", f"{rep['cumplimiento_protocolo_pct']}%")
        m4.metric("⚡ Latencia Media", f"{rep['latencia_promedio_ms']} ms")

        table_rows = []
        for item in rep["detalle_casos"]:
            table_rows.append({
                "ID": item["id"],
                "Categoría Evaluada": item["categoria"],
                "Prueba": item["nombre"],
                "Acción / Capa": item["herramienta_invocada"],
                "Latencia": f"{item['latencia_ms']} ms",
                "Resultado": item["estado"]
            })
        st.table(table_rows)


# Fecha y hora de compilación / última actualización del archivo
app_mtime = os.path.getmtime(__file__)
last_update_str = datetime.datetime.fromtimestamp(app_mtime).strftime("%d/%m/%Y %H:%M:%S")

# Inicializar estado de sesión
# Punto de inicio por defecto: Laguna Mar Chiquita (Mar de Ansenuza), Córdoba, Argentina
MAR_CHIQUITA_CENTER = [-30.60, -62.65]
MAR_CHIQUITA_ZOOM = 9

if "agent" not in st.session_state or not hasattr(st.session_state.agent, "_requires_rag_grounding"):
    st.session_state.agent = GeoReActAgent(registry=default_registry)
elif getattr(st.session_state.agent, "last_error", None) or "Qwen/Qwen" in str(getattr(st.session_state.agent, "model", "")) or "llama-3.3" in str(getattr(st.session_state.agent, "model", "")):
    # Re-inicializar si se actualizó el archivo .env a Groq
    st.session_state.agent.last_error = None
    st.session_state.agent.client = st.session_state.agent._init_client()
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

# -------------------------------------------------------------
# SIDEBAR: CONFIGURACIÓN DEL SISTEMA E INGENIERÍA DE IA
# -------------------------------------------------------------
with st.sidebar:
    st.header("⚙️ Configuración del Sistema")
    
    with st.expander("🤖 Conexión al Modelo LLM", expanded=True):
        st.markdown(
            "Configurá tu clave en **Streamlit Secrets** (`GROQ_API_KEY`, `HF_TOKEN` o `OPENAI_API_KEY`) o ingresala aquí:"
        )
        provider_choice = st.selectbox(
            "Proveedor LLM:",
            ["Automático (Secrets / .env)", "Groq (Gratuito y Ultrarrápido)", "Hugging Face Router", "OpenAI"],
            index=0
        )
        
        user_key = st.text_input(
            "API Key / Token:",
            type="password",
            placeholder="gsk_... / hf_... / sk-...",
            help="Pegá tu clave de Groq (gsk_...), Hugging Face (hf_...) u OpenAI (sk-...)."
        )
        
        default_m = st.session_state.agent.model or "openai/gpt-oss-120b"
        if "Groq" in provider_choice and "Qwen/Qwen" in default_m:
            default_m = "openai/gpt-oss-120b"
        elif "OpenAI" in provider_choice and "Qwen/Qwen" in default_m:
            default_m = "gpt-4o-mini"

        custom_model = st.text_input(
            "Modelo:",
            value=default_m,
            help="Groq: openai/gpt-oss-120b, qwen/qwen3.8-27b | HuggingFace: Qwen/Qwen2.5-72B-Instruct | OpenAI: gpt-4o-mini"
        )
        
        if st.button("🔌 Conectar / Actualizar LLM", use_container_width=True, type="primary"):
            st.session_state.agent.last_error = None
            st.session_state.agent.client = st.session_state.agent._init_client(
                custom_key=user_key if user_key else None,
                custom_provider=provider_choice if provider_choice != "Automático (Secrets / .env)" else None,
                custom_model=custom_model if custom_model else None
            )
            st.rerun()

    # Estado de Conexión en Sidebar
    if getattr(st.session_state.agent, "last_error", None):
        st.warning(f"⚠️ **Aviso de Cuota LLM (402/API):** Se agotaron los créditos gratuitos del proveedor externo. **El Asistente activó automáticamente el Motor Local de Contingencia** para responder sin interrupciones.")
    elif st.session_state.agent.client is not None:
        st.success(f"🟢 **LLM Conectado:** `{st.session_state.agent.model}`")
    else:
        st.warning("🟡 **Modo Local:** Sin API Key activa.\n\n*Podés ingresar tu token en esta barra lateral o agregar `GROQ_API_KEY` / `HF_TOKEN` en Secrets.*")
    
    st.markdown("---")
    st.markdown("### 🛡️ Ingeniería de IA (ISBIA)")
    st.caption("Capas activas: **Agent Harness**, **Guardrails OWASP**, **Sandbox COG** y **Contenedor**.")
    sess_side = getattr(st.session_state.agent, "session_metrics", {}) or {}
    if sess_side.get("queries_count", 0) > 0:
        q_c = sess_side["queries_count"]
        avg_l = round(sess_side.get("total_latency_ms", 0.0) / q_c, 1)
        st.markdown(
            f"""
            <div style="background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px; padding: 6px 10px; margin-bottom: 8px; font-size: 0.78rem; color: #334155;">
                📊 <b>Telemetría de Sesión:</b><br>
                • 🪙 <b>Tokens Totales:</b> <code>{sess_side.get('total_tokens', 0):,}</code> <i>(In: {sess_side.get('prompt_tokens', 0):,} / Out: {sess_side.get('completion_tokens', 0):,})</i><br>
                • ⏱️ <b>Latencia Media:</b> <code>{avg_l} ms</code> ({q_c} consultas)<br>
                • 🛠️ <b>Tools Invocadas:</b> <code>{sess_side.get('tools_invoked', 0)}</code> | 🛡️ <b>Bloqueos:</b> <code>{sess_side.get('security_blocks', 0)}</code>
            </div>
            """,
            unsafe_allow_html=True
        )
    if st.button("🛡️ Auditoría: Harness & Seguridad", use_container_width=True):
        dialog_harness_seguridad()

    st.markdown("---")
    st.markdown("### 📡 Catálogo Satelital STAC")
    sync_ver_side = st.session_state.get("stac_sync_version", 0)
    st.caption(
        "Sincronización dinámica con **Microsoft Planetary Computer** "
        "(`sentinel-2-l2a`, `esa-worldcover`, `io-lulc-annual-v02`)."
    )
    if st.button("🔄 Sincronizar fuentes STAC", key="btn_sync_sidebar", use_container_width=True):
        st.session_state.stac_sync_version = sync_ver_side + 1
        cached_sources_catalog.clear()
        with st.spinner("Actualizando colecciones y fechas desde STAC..."):
            s_cat = cached_sources_catalog(tuple(st.session_state.current_bbox), st.session_state.stac_sync_version)
        st.toast(
            f"✅ Fuentes sincronizadas ({s_cat.get('synced_at')}) | "
            f"Esri LULC: {s_cat['io_lulc']['years'][0]}–{s_cat['io_lulc']['years'][-1]} | "
            f"S2: hasta {s_cat['sentinel2']['latest_scene_date']}"
        )
        st.rerun()

    st.markdown("---")
    st.markdown("### 📚 Acerca del Proyecto")
    st.markdown(
        "- **Desarrollo, Implementación y Despliegue (asistido con IA):** Dr. Federico J. Letourneau *(IFAB INTA - CONICET)*\n"
        "- **Desarrollo Conceptual:** Discusión colaborativa — Grupo 6 (2026)\n"
        "- **Diplomatura:** ISBIA - Lidesia - FCEFyN (UNC)\n"
        "- **Directora de la Diplomatura:** Dra. Laura Cecilia Díaz Dávila\n"
        "- **Base Agente ReAct:** Notebook base de Ing. Sandro Mauricio Comerci y Dra. Laura Cecilia Díaz Dávila *(LIDeSIA - FCEFyN)*\n"
        "- **Datos:** STAC Microsoft Planetary Computer\n"
        "- **Modelos:** ESA WorldCover 10m, Esri Annual LULC 10m & Copernicus DEM 30m"
    )

# Encabezado y Subtítulo enriquecido con Stack Tecnológico y Timestamp de Compilación
st.title("🛰️ TFI_Grupo_6_2026: Clasificación de Coberturas del suelo con Agentes IA")
st.caption(f"⏱️ **Última compilación / actualización:** `{last_update_str}` | Desarrollo e implementación: **Dr. Federico J. Letourneau (IFAB INTA - CONICET)** | Desarrollo conceptual: **Grupo 6 (2026)** | Diplomatura ISBIA - Lidesia - FCEFyN (UNC) — Dir. **Dra. Laura Cecilia Díaz Dávila**")
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
        modelo_str = str(res_prev.get("modelo", ""))
        is_ia = any(k in modelo_str for k in ("WorldCover", "LULC", "Deep Learning", "IA"))
        if is_ia:
            year_tag = res_prev.get("año_referencia") or "2021"
            src_short = "Esri LULC" if "Esri" in modelo_str or "LULC" in modelo_str else "WorldCover"
            overlay_name = f"🛰️ Cobertura [IA - {src_short} {year_tag}]"
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
        export=False,
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
        height=420,
        use_container_width=True,
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

            if col_drain_btn.button("🌊 Red de Drenaje y Pendientes", use_container_width=True, help="Descarga Copernicus DEM 30m, modela líneas de escurrimiento y ejecuta cruce espacial Cobertura × Pendiente"):
                with st.spinner("Descargando Copernicus DEM 30m y ejecutando cruce espacial Cobertura × Pendiente..."):
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

            # Caso Modelo IA Multiclase (ESA WorldCover o Esri 10m Annual LULC)
            if any(k in str(res.get("modelo")) for k in ("WorldCover", "LULC", "Deep Learning")):
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
            col_dh1.markdown("#### 🌊 Red de Drenaje, Pendientes y Cruce Espacial (DEM 30m)")
            if col_dh2.button("🔄 Recalcular Drenaje", use_container_width=True):
                with st.spinner("Recalculando modelo hidrológico y cruce espacial Cobertura × Pendiente..."):
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

            agua_excl_ha = float(d_res.get("agua_enmascarada_ha", 0.0) or 0.0)
            terr_ha_val = float(d_res.get("superficie_terrestre_ha", d_res["superficie_total_ha"]) or d_res["superficie_total_ha"])

            # Métricas Topográficas Principales
            dc1, dc2, dc3, dc4 = st.columns(4)
            dc1.metric("⛰️ Desnivel", f"{d_res['elevacion']['desnivel_m']} m", f"Cotas: {d_res['elevacion']['minima_msnm']} a {d_res['elevacion']['maxima_msnm']} m")
            dc2.metric(
                "📐 Pendiente Media" + (" (Terr.)" if agua_excl_ha > 0 else ""),
                f"{d_res['pendientes']['media_pct']}%",
                f"Máx: {d_res['pendientes']['maxima_pct']}%"
            )
            dc3.metric("🧭 Rumbo de Flujo", f"{d_res['direccion_flujo']['rumbo_cardinal']}", f"Acimut: {d_res['direccion_flujo']['acimut_grados']}°")
            dc4.metric(
                "📐 Superficie Terrestre" if agua_excl_ha > 0 else "📐 Superficie",
                f"{terr_ha_val:,.1f} ha",
                f"Agua excl.: {agua_excl_ha:,.1f} ha" if agua_excl_ha > 0 else "Copernicus 30m"
            )

            # Diagnóstico Territorial Multi-Dominio (basado en cruce espacial Cobertura × Pendiente)
            diag_t = d_res.get("diagnostico_territorial")
            cruce = d_res.get("cruce_espacial", {})
            if diag_t:
                fuente_cob = cruce.get("fuente_cobertura", "Referencia satelital 10m")
                st.markdown(
                    f"""
                    <div style="background-color: #f8fafc; border: 1px solid #cbd5e1; border-left: 4px solid #0f172a; padding: 8px 12px; border-radius: 6px; margin-top: 6px; margin-bottom: 8px; font-size: 0.87rem; color: #1e293b;">
                        🧭 <b>Régimen Territorial Detectado:</b> <b>{diag_t.get('regimen_territorial')}</b><br>
                        🛰️ <b>Fuente de Cobertura (Cruce 10m × 30m):</b> <span style="color: #334155;">{fuente_cob}</span>
                    </div>
                    """,
                    unsafe_allow_html=True
                )

                for mod in diag_t.get("modulos_activos", []):
                    border_col = mod.get("color", "#2563eb")
                    st.markdown(
                        f"""
                        <div style="background-color: #ffffff; border: 1px solid #e2e8f0; border-left: 4px solid {border_col}; padding: 8px 12px; border-radius: 6px; margin-bottom: 8px; font-size: 0.86rem; color: #1e293b;">
                            📌 <b>{mod.get('dominio')}</b> &nbsp;<span style="background-color: #f1f5f9; border: 1px solid #cbd5e1; border-radius: 4px; padding: 1px 6px; font-size: 0.78rem; color: #334155;">{mod.get('nivel')}</span><br>
                            <span style="color: #334155;">{mod.get('hallazgo')}</span><br>
                            💡 <b>Recomendación:</b> {mod.get('recomendaciones')}
                        </div>
                        """,
                        unsafe_allow_html=True
                    )

                if diag_t.get("nota_alcance_regulatorio"):
                    st.caption(f"⚖️ **Alcance normativo:** {diag_t['nota_alcance_regulatorio']}")

            elif d_res.get("analisis_agrohidrologico") and d_res["analisis_agrohidrologico"].get("riesgo_erosion_hidrica"):
                agro = d_res["analisis_agrohidrologico"]
                st.markdown(
                    f"""
                    <div style="background-color: #eff6ff; border: 1px solid #bfdbfe; border-left: 4px solid #2563eb; padding: 8px 12px; border-radius: 6px; margin-top: 6px; margin-bottom: 10px; font-size: 0.88rem; color: #1e3a8a;">
                        🌊 <b>Evaluación de Riesgo:</b> <b>{agro.get('riesgo_erosion_hidrica')}</b><br>
                        💡 <b>Recomendación de Manejo:</b> {agro.get('recomendacion_conservacion')}
                    </div>
                    """,
                    unsafe_allow_html=True
                )

            # Visualización y Matriz Cuantitativa del Cruce Espacial Cobertura × Pendiente
            d_cruce_path = d_res.get("mapa_cruce_generado")
            if d_cruce_path and os.path.exists(d_cruce_path):
                st.image(d_cruce_path, caption="Cruce Espacial: Zonificación Funcional Hidro-Territorial y Superficie por Cobertura × Pendiente", use_container_width=True)

            if cruce.get("disponible") and cruce.get("matriz_cobertura_pendiente"):
                with st.expander("📊 Ver matriz cuantitativa Cobertura × Pendiente (hectáreas)"):
                    matriz = cruce["matriz_cobertura_pendiente"]
                    table_cross = []
                    for row in sorted(matriz.values(), key=lambda x: x["hectareas"], reverse=True):
                        pr = row.get("por_rango_pendiente", {})
                        is_water = row.get("macro_clase") == "agua"
                        table_cross.append({
                            "Cobertura": row["nombre"].split("(")[0].strip(),
                            "Total (ha)": f"{row['hectareas']:,.1f}",
                            "% Área": f"{row['porcentaje_area']}%",
                            "Pend. Media": "—" if is_water else f"{row['pendiente_media_pct']}%",
                            "< 3% (ha)": "—" if is_water else f"{row['ha_pendiente_baja_menor_3pct']:,.1f}",
                            "3–8% (ha)": "—" if is_water else f"{pr.get('moderada_3_a_8pct', {}).get('hectareas', 0.0):,.1f}",
                            "8–15% (ha)": "—" if is_water else f"{pr.get('fuerte_8_a_15pct', {}).get('hectareas', 0.0):,.1f}",
                            "15–30% (ha)": "—" if is_water else f"{pr.get('muy_fuerte_15_a_30pct', {}).get('hectareas', 0.0):,.1f}",
                            "> 30% (ha)": "—" if is_water else f"{pr.get('extrema_mayor_30pct', {}).get('hectareas', 0.0):,.1f}",
                        })
                    st.table(table_cross)

            with st.expander("📋 Ver distribución cuantitativa por rangos de pendiente terrestre"):
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
                if agua_excl_ha > 0:
                    st.caption(f"💧 Cuerpos de agua enmascarados fuera del cálculo de pendiente terrestre: **{agua_excl_ha:,.1f} ha** ({cruce.get('agua_enmascarada_pct', 0.0)}%).")

            d_mapa_path = d_res.get("mapa_generado")
            if d_mapa_path and os.path.exists(d_mapa_path):
                st.image(d_mapa_path, caption="Topografía 3D, Líneas de Drenaje Hídrico y Zonificación de Pendientes Terrestres", use_container_width=True)

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
    
    # Verificar si el cliente LLM está conectado y mostrar badge informativo + acceso directo
    agent_inst = st.session_state.agent
    if agent_inst.client is None:
        agent_inst.client = agent_inst._init_client()
        
    llm_col_status, llm_col_cfg = st.columns([2.4, 1.2])
    with llm_col_status:
        if getattr(agent_inst, "last_error", None):
            st.caption("🟠 **Fallback Automático Activo:** Cuota de API agotada → Respondiendo con Motor Local")
        elif agent_inst.client is not None:
            st.caption(f"🟢 **LLM Conectado:** `{agent_inst.model}` (Inferencia Activa)")
        else:
            st.caption("🟡 **Modo Local:** Motor de Contingencia (Sin API Key / Fallback)")
    with llm_col_cfg:
        with st.popover("🔌 Enlace LLM / Seg.", use_container_width=True):
            st.markdown("**🤖 Estado del Modelo LLM**")
            st.caption(f"Modelo activo: `{agent_inst.model}`")
            st.caption("Podés cambiar el proveedor (`Groq`, `HuggingFace`, `OpenAI`) o la API Key en el panel **⚙️ Configuración del Sistema** de la barra lateral izquierda.")
            if st.button("🛡️ Abrir Auditoría Harness & Seguridad", key="btn_audit_inline", use_container_width=True):
                dialog_harness_seguridad()

    q_col1, q_col2, q_col3, q_col4 = st.columns([1.05, 1.25, 1.05, 1.25])
    preset_query = None
    if q_col1.button("📉 Coberturas", use_container_width=True):
        preset_query = "Analizá y diagnosticá la distribución cuantitativa de coberturas obtenidas por el modelo en el área seleccionada, indicando superficies en hectáreas, porcentajes y su balance territorial (forestal, productivo, urbano e hídrico)."
    if q_col2.button("🌊 Drenaje y Pendiente", use_container_width=True):
        preset_query = "Analizá y diagnosticá la red de drenaje hídrico superficial, pendientes (%) y dirección de escurrimiento en el área seleccionada, evaluando los riesgos hídricos y recomendaciones pertinentes según el cruce espacial Cobertura × Pendiente."
    if q_col3.button("🛠️ Stack y Código", use_container_width=True):
        preset_query = "Explicá el stack tecnológico utilizado para construir esta app, su arquitectura modular y cómo intervenir o modificar el código según la guía del proyecto."
    if q_col4.button("🛡️ Harness y Seguridad", use_container_width=True):
        preset_query = "Explicá cómo se integran el Agent Harness, la Ciberseguridad (Guardrails OWASP), el Sandbox y los Contenedores en la arquitectura de este proyecto."

    chat_container = st.container(height=450)
    with chat_container:
        if not st.session_state.chat_history:
            st.info("👋 Podés hacer consultas en lenguaje natural para que el asistente interprete los datos cuantitativos clasificados, evalúe la red de drenaje hídrico o explique la arquitectura, seguridad y código de la app.")

        for chat in st.session_state.chat_history:
            with st.chat_message(chat["role"]):
                st.markdown(chat["content"])

                # Mostrar píldora de telemetría (Tokens, Latencia, Pasos, Seguridad) bajo cada respuesta
                if chat.get("metrics"):
                    m_info = chat["metrics"]
                    st.markdown(
                        f"""
                        <div style="background-color: #f1f5f9; border: 1px solid #cbd5e1; border-radius: 5px; padding: 4px 10px; margin-top: 6px; margin-bottom: 4px; font-size: 0.76rem; color: #334155;">
                            ⏱️ <b>Latencia:</b> <code>{m_info.get('total_latency_ms', 0)} ms</code> <i>(LLM: {m_info.get('llm_latency_ms', 0)} ms | Tool: {m_info.get('tool_latency_ms', 0)} ms)</i> &nbsp;|&nbsp;
                            🪙 <b>Tokens:</b> <code>{m_info.get('total_tokens', 0):,}</code> <i>(Prompt: {m_info.get('prompt_tokens', 0):,} / Salida: {m_info.get('completion_tokens', 0):,})</i> &nbsp;|&nbsp;
                            🔄 <b>Pasos ReAct:</b> <code>{m_info.get('steps_used', 1)}/{m_info.get('max_steps', 7)}</code> &nbsp;|&nbsp;
                            🛡️ <b>Seguridad:</b> <code>{m_info.get('security_status', 'OK')}</code>
                        </div>
                        """,
                        unsafe_allow_html=True
                    )

                if chat.get("trace"):
                    with st.expander("🔍 Ver Traza de Razonamiento ReAct y Telemetría por Paso"):
                        for step in chat["trace"]:
                            lat_str = f" | ⏱️ Total: {step['latency_ms']} ms (LLM: {step.get('llm_latency_ms', 0)} ms, Tool: {step.get('tool_latency_ms', 0)} ms)" if step.get("latency_ms") is not None else ""
                            tok_str = f" | 🪙 Tokens: {step.get('total_tokens', 0)} (In: {step.get('prompt_tokens', 0)}, Out: {step.get('completion_tokens', 0)})" if step.get("total_tokens") else ""
                            st.markdown(f"**Paso {step['step']}:** `{step.get('action') or 'Respuesta Final'}`{lat_str}{tok_str}")
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
            c_raw = st.session_state.classification_result
            c_compact = {
                k: c_raw.get(k)
                for k in (
                    "modelo", "coleccion_stac", "año_referencia", "fecha_analizada",
                    "superficie_total_ha", "total_pixeles_10m", "coberturas", "ubicacion_administrativa"
                )
                if c_raw.get(k) is not None
            }
            final_query += f" [Última Clasificación: {json.dumps(c_compact, ensure_ascii=False)}]"
        if st.session_state.get("drainage_result"):
            d_raw = st.session_state.drainage_result
            cruce_raw = d_raw.get("cruce_espacial", {}) or {}
            d_compact = {
                "superficie_total_ha": d_raw.get("superficie_total_ha"),
                "superficie_terrestre_ha": d_raw.get("superficie_terrestre_ha"),
                "agua_enmascarada_ha": d_raw.get("agua_enmascarada_ha"),
                "elevacion": d_raw.get("elevacion"),
                "pendientes": {
                    "media_pct": d_raw.get("pendientes", {}).get("media_pct"),
                    "maxima_pct": d_raw.get("pendientes", {}).get("maxima_pct"),
                    "mediana_pct": d_raw.get("pendientes", {}).get("mediana_pct"),
                },
                "direccion_flujo": d_raw.get("direccion_flujo"),
                "cruce_espacial": {
                    "disponible": cruce_raw.get("disponible"),
                    "fuente_cobertura": cruce_raw.get("fuente_cobertura"),
                    "esquema_semantico": cruce_raw.get("esquema_semantico"),
                    "indicadores_cruce": cruce_raw.get("indicadores_cruce"),
                },
                "diagnostico_territorial": d_raw.get("diagnostico_territorial"),
                "analisis_agrohidrologico": d_raw.get("analisis_agrohidrologico"),
            }
            final_query += f" [Último Análisis de Drenaje Hídrico: {json.dumps(d_compact, ensure_ascii=False)}]"

        st.session_state.chat_history.append({"role": "user", "content": query_to_run})

        with st.spinner("🤖 El asistente está razonando e integrando evidencia..."):
            answer, trace = st.session_state.agent.run(final_query)
            run_metrics = getattr(st.session_state.agent, "last_run_metrics", {})

            st.session_state.chat_history.append({
                "role": "assistant",
                "content": answer,
                "trace": trace,
                "metrics": run_metrics
            })
            st.rerun()

