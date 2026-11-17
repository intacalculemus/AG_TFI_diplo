"""
Motor Principal del Agente ReAct Geoambiental (GeoReActAgent)
Incluye Sintetizador Dinámico de Observaciones Reales (ESA WorldCover, Sentinel-2, NDVI, RAG)
"""
from typing import List, Dict, Any, Tuple, Optional
import os
import re
import json
import time
from pathlib import Path

try:
    from openai import OpenAI
    HAS_OPENAI = True
except ImportError:
    OpenAI = None
    HAS_OPENAI = False

from config import (
    LLM_BASE_URL,
    LLM_API_KEY,
    DEFAULT_MODEL,
    AGENT_MAX_STEPS,
    AGENT_TEMPERATURE
)
from tools.base import ToolRegistry, default_registry
from agent.prompts import build_system_prompt
from agent.parser import parse_action, parse_final_answer
from agent.security import validate_user_input, sanitize_output

class GeoReActAgent:
    """
    Orquestador del ciclo de razonamiento y acción ReAct.
    """

    def __init__(
        self,
        registry: Optional[ToolRegistry] = None,
        model: str = DEFAULT_MODEL,
        temperature: float = AGENT_TEMPERATURE,
        max_steps: int = AGENT_MAX_STEPS
    ):
        self.registry = registry or default_registry
        self.model = model
        self.temperature = temperature
        self.max_steps = max_steps
        self.system_prompt = build_system_prompt(self.registry.build_system_description())
        self.last_error: Optional[str] = None
        self._last_step_usage: Dict[str, Any] = {}
        self.last_run_metrics: Dict[str, Any] = {}
        self.session_metrics: Dict[str, Any] = {
            "queries_count": 0,
            "total_tokens": 0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_latency_ms": 0.0,
            "tools_invoked": 0,
            "security_blocks": 0,
        }
        self.client = self._init_client()

    def _init_client(
        self,
        custom_key: Optional[str] = None,
        custom_provider: Optional[str] = None,
        custom_model: Optional[str] = None
    ) -> Optional[Any]:
        """Inicializa el cliente de API OpenAI, Groq o HuggingFace de forma segura."""
        if not HAS_OPENAI:
            return None

        from dotenv import load_dotenv
        load_dotenv(override=True)

        hf_token = os.getenv("HF_TOKEN", "")
        openai_key = os.getenv("OPENAI_API_KEY", "")
        groq_key = os.getenv("GROQ_API_KEY", "")
        model_id = os.getenv("MODEL_ID", "")
        base_url = LLM_BASE_URL
        api_key = LLM_API_KEY

        # Compatibilidad directa con Streamlit Cloud Secrets (st.secrets)
        try:
            import sys
            if "streamlit" in sys.modules:
                import streamlit as st
                if hasattr(st, "secrets"):
                    if not hf_token and "HF_TOKEN" in st.secrets:
                        hf_token = str(st.secrets["HF_TOKEN"]).strip()
                    if not openai_key and "OPENAI_API_KEY" in st.secrets:
                        openai_key = str(st.secrets["OPENAI_API_KEY"]).strip()
                    if not groq_key and "GROQ_API_KEY" in st.secrets:
                        groq_key = str(st.secrets["GROQ_API_KEY"]).strip()
                    if not model_id and "MODEL_ID" in st.secrets:
                        model_id = str(st.secrets["MODEL_ID"]).strip()
        except Exception:
            pass

        # Parámetros personalizados pasados desde la interfaz de usuario (Sidebar)
        if custom_key:
            custom_key = custom_key.strip()
            if "Groq" in str(custom_provider) or custom_key.startswith("gsk_"):
                groq_key = custom_key
                hf_token = ""
                openai_key = ""
            elif "Hugging" in str(custom_provider) or custom_key.startswith("hf_"):
                hf_token = custom_key
                openai_key = ""
                groq_key = ""
            elif "OpenAI" in str(custom_provider) or custom_key.startswith("sk-"):
                openai_key = custom_key
                hf_token = ""
                groq_key = ""
            else:
                if custom_key.startswith("gsk_"):
                    groq_key = custom_key
                elif custom_key.startswith("hf_"):
                    hf_token = custom_key
                else:
                    openai_key = custom_key

        if custom_model:
            model_id = custom_model.strip()

        if groq_key:
            base_url = "https://api.groq.com/openai/v1"
            api_key = groq_key
            self.model = model_id if (model_id and "Qwen/Qwen" not in model_id) else "openai/gpt-oss-120b"
        elif hf_token:
            base_url = "https://router.huggingface.co/v1"
            api_key = hf_token
            self.model = model_id or "Qwen/Qwen2.5-72B-Instruct"
        elif openai_key:
            base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
            api_key = openai_key
            self.model = model_id if (model_id and "Qwen" not in model_id) else "gpt-4o-mini"
        elif LLM_API_KEY:
            api_key = LLM_API_KEY
            base_url = LLM_BASE_URL
            if model_id:
                self.model = model_id

        if not api_key:
            return None

        try:
            return OpenAI(
                base_url=base_url,
                api_key=api_key
            )
        except Exception:
            return None

    def _call_llm(self, messages: List[Dict[str, str]]) -> str:
        """Invoca al modelo de lenguaje y registra métricas exactas de tokens y modo de inferencia."""
        prompt_chars = sum(len(m.get("content", "")) for m in messages)
        est_prompt_tokens = max(1, prompt_chars // 4)

        if self.client is None:
            out = self._mock_llm_reasoning(messages)
            est_comp_tokens = max(1, len(out) // 4)
            self._last_step_usage = {
                "prompt_tokens": est_prompt_tokens,
                "completion_tokens": est_comp_tokens,
                "total_tokens": est_prompt_tokens + est_comp_tokens,
                "is_estimated": True,
                "inference_mode": "Motor Local (Determinístico)"
            }
            return out

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=self.temperature
            )
            content = response.choices[0].message.content or ""
            usage = getattr(response, "usage", None)
            if usage is not None:
                p_tok = getattr(usage, "prompt_tokens", None) or est_prompt_tokens
                c_tok = getattr(usage, "completion_tokens", None) or max(1, len(content) // 4)
                t_tok = getattr(usage, "total_tokens", None) or (p_tok + c_tok)
                is_est = False
            else:
                p_tok = est_prompt_tokens
                c_tok = max(1, len(content) // 4)
                t_tok = p_tok + c_tok
                is_est = True

            self._last_step_usage = {
                "prompt_tokens": int(p_tok),
                "completion_tokens": int(c_tok),
                "total_tokens": int(t_tok),
                "is_estimated": is_est,
                "inference_mode": f"API ({self.model})"
            }
            return content
        except Exception as e:
            self.last_error = str(e)
            # Fallback automático al motor local si se agota la cuota (402/429) o falla la API
            out = self._mock_llm_reasoning(messages)
            est_comp_tokens = max(1, len(out) // 4)
            self._last_step_usage = {
                "prompt_tokens": est_prompt_tokens,
                "completion_tokens": est_comp_tokens,
                "total_tokens": est_prompt_tokens + est_comp_tokens,
                "is_estimated": True,
                "inference_mode": "Fallback Local (Contingencia)"
            }
            return out

    def _extract_json_from_text(self, text: str) -> Optional[Dict[str, Any]]:
        """Intenta extraer un objeto JSON embebido en una cadena de texto."""
        if not text:
            return None
        decoder = json.JSONDecoder()
        idx = text.find("{")
        while idx != -1:
            try:
                obj, _end = decoder.raw_decode(text[idx:])
                if isinstance(obj, dict):
                    return obj
            except Exception:
                pass
            idx = text.find("{", idx + 1)
        return None

    def _extract_tagged_json(self, text: str, tag: str) -> Optional[Dict[str, Any]]:
        """Extrae el objeto JSON inmediatamente posterior a una etiqueta de contexto (p. ej. '[Última Clasificación:')."""
        if tag not in text:
            return None
        after = text.split(tag, 1)[1]
        return self._extract_json_from_text(after)

    def _synthesize_real_data(self, data: Dict[str, Any], context_normativa: str = "") -> str:
        """Genera una síntesis técnica y agroambiental rigurosa utilizando exactamente los números de la clasificación real."""
        # 1. Caso Modelos IA Multiclase 10m (ESA WorldCover / Esri Annual LULC)
        if any(k in str(data.get("modelo", "")) for k in ("ESA WorldCover", "LULC", "Deep Learning")) or any("codigo" in str(v) for v in data.get("coberturas", {}).values()):
            coberturas = data.get("coberturas", {})
            total_ha = data.get("superficie_total_ha", 0.0)
            total_px = data.get("total_pixeles_10m", 0)
            year = data.get("año_referencia", "2021")
            model_name = data.get("modelo", "Modelo de IA 10m")

            sorted_c = sorted(coberturas.values(), key=lambda x: x.get("hectareas", 0), reverse=True)
            desglose = []
            for c in sorted_c:
                desglose.append(f"• **{c['nombre']}:** {c['porcentaje']}% ({c['hectareas']:,.1f} ha)")

            # Ubicación administrativa si está disponible
            ub_info = data.get("ubicacion_administrativa", {})
            loc_line = f"📍 **Ubicación Territorial:** {ub_info.get('texto_formateado')}\n" if isinstance(ub_info, dict) and ub_info.get("texto_formateado") else ""

            # Interpretación cuantitativa territorial multi-clase
            bosque_ha = sum(c["hectareas"] for c in coberturas.values() if "Bosque" in c.get("nombre", "") or "Tree" in c.get("nombre", ""))
            matorral_ha = sum(c["hectareas"] for c in coberturas.values() if "Matorral" in c.get("nombre", "") or "Shrub" in c.get("nombre", ""))
            cultivo_ha = sum(c["hectareas"] for c in coberturas.values() if "Cultivo" in c.get("nombre", "") or "Crop" in c.get("nombre", ""))
            pasturas_ha = sum(c["hectareas"] for c in coberturas.values() if any(k in c.get("nombre", "") for k in ("Pastizal", "Grassland", "Rangeland")))
            urbano_ha = sum(c["hectareas"] for c in coberturas.values() if "Urbana" in c.get("nombre", "") or "Built" in c.get("nombre", ""))
            suelo_ha = sum(c["hectareas"] for c in coberturas.values() if "Desnudo" in c.get("nombre", "") or "Bare" in c.get("nombre", ""))
            agua_ha = sum(c["hectareas"] for c in coberturas.values() if "Agua" in c.get("nombre", "") or "Humedal" in c.get("nombre", "") or "Water" in c.get("nombre", "") or "Flooded" in c.get("nombre", ""))

            lines = [
                f"### 📊 Diagnóstico de Coberturas - {model_name} (Año {year})",
                f"{loc_line}Para el área de interés delimitada (**{total_ha:,.1f} ha**, {total_px:,} píxeles clasificados a 10m de resolución), los resultados son:",
                "",
                "\n".join(desglose),
                "",
                "**Interpretación Territorial e Hídrica:**",
            ]

            if bosque_ha > 0 or matorral_ha > 0:
                lenoso_ha = bosque_ha + matorral_ha
                lines.append(
                    f"- **Cobertura Forestal y Leñosa:** Representa {round((lenoso_ha/total_ha)*100, 1) if total_ha > 0 else 0}% "
                    f"({bosque_ha:,.1f} ha de bosque/árboles"
                    + (f" + {matorral_ha:,.1f} ha de matorral/arbustal" if matorral_ha > 0 else "")
                    + "), clave para protección de cuencas, infiltración y regulación del escurrimiento."
                )
            if urbano_ha > 0:
                lines.append(
                    f"- **Área Urbana / Construida:** Ocupa {round((urbano_ha/total_ha)*100, 1) if total_ha > 0 else 0}% ({urbano_ha:,.1f} ha), "
                    "lo que introduce impermeabilización superficial y requiere analizar drenaje pluvial y contacto en interfaz urbano-forestal."
                )
            if cultivo_ha > 0 or pasturas_ha > 0:
                lines.append(f"- **Área Agrícola / Ganadera:** Registra {cultivo_ha:,.1f} ha de cultivos agrícolas y {pasturas_ha:,.1f} ha de pastizales/sabanas.")
            if suelo_ha > 0:
                lines.append(f"- **Suelo Desnudo / Roca / Barbecho:** {suelo_ha:,.1f} ha expuestas (sujetas a evaluación según pendiente).")
            if agua_ha > 0:
                lines.append(f"- **Cuerpos de Agua y Humedales:** {agua_ha:,.1f} ha identificadas en la matriz territorial.")

            if context_normativa:
                lines.append(f"\n**Marco Complementario:**\n{context_normativa}")

            return "\n".join(lines)

        # 2. Caso Clasificación Radiométrica Sentinel-2 L2A (Bandas B04/B08)
        if "coberturas" in data and "vegetacion" in data["coberturas"]:
            c = data["coberturas"]
            veg = c.get("vegetacion", {})
            suelo = c.get("suelo_desnudo", {})
            agua = c.get("cuerpos_de_agua", {})
            total_ha = data.get("superficie_total_ha", 0.0)
            fecha = data.get("fecha_analizada", "")

            # Ubicación administrativa si está disponible
            ub_info = data.get("ubicacion_administrativa", {})
            loc_line = f"📍 **Ubicación Territorial:** {ub_info.get('texto_formateado')}\n" if isinstance(ub_info, dict) and ub_info.get("texto_formateado") else ""

            lines = [
                f"### 📊 Diagnóstico Radiométrico - Sentinel-2 L2A (Fecha: {fecha})",
                f"{loc_line}Procesamiento multiespectral a 10m sobre un área total de **{total_ha:,.1f} ha**:",
                "",
                f"• **Vegetación Activa (NDVI ≥ 0.35):** {veg.get('porcentaje', 0)}% ({veg.get('hectareas', 0):,.1f} ha)",
                f"• **Suelo Desnudo / Barbecho (0.05 ≤ NDVI < 0.35):** {suelo.get('porcentaje', 0)}% ({suelo.get('hectareas', 0):,.1f} ha)",
                f"• **Cuerpos de Agua / Sombras (NDVI < 0.05):** {agua.get('porcentaje', 0)}% ({agua.get('hectareas', 0):,.1f} ha)",
                "",
                "**Evaluación Biofísica:** Los valores espectrales reflejan el estado del vigor vegetativo para la fecha seleccionada, diferenciando áreas con actividad fotosintética vigorosa frente a suelos expuestos o rastrojos secos."
            ]

            if context_normativa:
                lines.append(f"\n**Marco Complementario:**\n{context_normativa}")

            return "\n".join(lines)

        # 3. Caso Series Temporales de NDVI
        if "estadisticas_ndvi" in data:
            stats = data["estadisticas_ndvi"]
            diag = data.get("diagnostico_biofisico", {})
            zona = data.get("zona_analizada", "")
            
            return (
                f"El análisis de la serie temporal de NDVI para **{zona}** ({data.get('rango_fechas', '')}) "
                f"muestra un valor inicial de **{stats.get('valor_inicial')}**, un valor final de **{stats.get('valor_final')}** y un promedio de **{stats.get('media')}** "
                f"(Variación acumulada: **{stats.get('variacion_porcentual_total')}**).\n\n"
                f"**Diagnóstico:** {diag.get('interpretacion')}"
            )

        # 4. Caso Red de Drenaje Hídrico, Pendientes y Cruce Espacial Cobertura x Pendiente (Copernicus DEM 30m)
        if "pendientes" in data and "elevacion" in data:
            elev = data.get("elevacion", {})
            pend = data.get("pendientes", {})
            flujo = data.get("direccion_flujo", {})
            cruce = data.get("cruce_espacial", {})
            diag = data.get("diagnostico_territorial", {})
            agro = data.get("analisis_agrohidrologico", {})
            total_ha = data.get("superficie_total_ha", 0.0)
            terr_ha = data.get("superficie_terrestre_ha", total_ha)
            agua_excl = data.get("agua_enmascarada_ha", 0.0)

            lines = [
                "### 🌊 Diagnóstico Hidro-Territorial y Cruce Espacial — Copernicus DEM 30m",
                f"Superficie total analizada: **{total_ha:,.1f} ha**"
                + (f" (Terrestre: **{terr_ha:,.1f} ha** | Agua enmascarada: **{agua_excl:,.1f} ha**)" if agua_excl > 0 else "") + ":",
                "",
                f"• **Cotas y Desnivel:** {elev.get('minima_msnm')} a {elev.get('maxima_msnm')} msnm (Desnivel: **{elev.get('desnivel_m')} m**)",
                f"• **Pendiente Terrestre Media / Máxima:** **{pend.get('media_pct')}%** (Máx: {pend.get('maxima_pct')}%)",
                f"• **Dirección Predominante de Escurrimiento:** **{flujo.get('rumbo_cardinal')}** (Acimut: {flujo.get('acimut_grados')}°)",
            ]

            if diag:
                lines.append(f"• **Régimen Territorial Detectado:** **{diag.get('regimen_territorial')}**")
                if cruce.get("disponible"):
                    lines.append(f"• **Fuente de Cobertura (Cruce 10m×30m):** {cruce.get('fuente_cobertura')}")
                lines.append(f"• **{diag.get('etiqueta_riesgo_principal', 'Riesgo Principal')}:** {diag.get('nivel_riesgo_principal')}")

                modulos = diag.get("modulos_activos", [])
                if modulos:
                    lines.append("\n**Módulos de Diagnóstico y Recomendaciones por Uso Real del Suelo:**")
                    for m in modulos:
                        lines.append(f"- **{m.get('dominio')} [{m.get('nivel')}]:** {m.get('hallazgo')} *Recomendación:* {m.get('recomendaciones')}")

                if diag.get("nota_alcance_regulatorio"):
                    lines.append(f"\n> ℹ️ *{diag.get('nota_alcance_regulatorio')}*")
            else:
                lines.append(f"• **Evaluación de Riesgo:** **{agro.get('riesgo_erosion_hidrica', 'Moderado')}**")
                lines.append(f"\n**Recomendación de Manejo:** {agro.get('recomendacion_conservacion', 'Monitorear escurrimiento superficial.')}")

            return "\n".join(lines)

        return str(data.get("resumen_ejecutivo", "Datos procesados correctamente."))

    @staticmethod
    def _requires_rag_grounding(query: str) -> bool:
        """Determina si la consulta exige verificación previa obligatoria en el RAG documental."""
        user_text = query.split("[BBox activo:")[0].strip().lower()
        rag_keywords = (
            "autor", "autores", "autoría", "autoria", "creador", "creadores",
            "desarrollador", "desarrolladores", "desarrolló", "desarrollo",
            "créditos", "creditos", "equipo", "directora", "director",
            "diplomatura", "institucion", "institución", "letourneau", "comerci",
            "davila", "dávila", "notebook", "arquitectura", "stack",
            "tecnologias", "tecnologías", "harness", "ciberseguridad",
            "sandbox", "contenedor", "docker", "owasp", "langchain",
            "intervenir", "modificar", "código", "codigo", "quien hizo", "quién hizo",
        )
        return any(k in user_text for k in rag_keywords)

    def _mock_llm_reasoning(self, messages: List[Dict[str, str]]) -> str:
        """
        Simulador de inferencia dinámico:
        Lee y extrae los datos REALES de las herramientas ejecutadas para sintetizar respuestas precisas.
        """
        user_raw = ""
        for m in messages:
            if m["role"] == "user" and not m["content"].startswith("Observation:"):
                user_raw = m["content"]
        
        # Separar el texto principal de la consulta de los metadatos JSON adjuntos
        main_query_text = user_raw.split("[BBox activo:")[0].strip().lower()
        class_json = self._extract_tagged_json(user_raw, "[Última Clasificación:")
        drain_json = self._extract_tagged_json(user_raw, "[Último Análisis de Drenaje Hídrico:")
        query_json = class_json or drain_json or self._extract_json_from_text(user_raw)

        # Extraer BBox explícito en el texto o el BBox activo inyectado por la app
        explicit_bbox_match = re.search(r"(\[\s*-?\d+\.?\d*\s*,\s*-?\d+\.?\d*\s*,\s*-?\d+\.?\d*\s*,\s*-?\d+\.?\d*\s*\])", main_query_text)
        active_bbox_match = re.search(r"\[BBox activo:\s*(\[[^\]]+\])\]", user_raw)
        explicit_bbox = (
            explicit_bbox_match.group(1)
            if explicit_bbox_match
            else (active_bbox_match.group(1) if active_bbox_match else "[-62.2, -26.15, -61.9, -25.85]")
        )

        last_msg = messages[-1]["content"]

        # Paso inicial: razonar qué herramienta invocar según la intención
        if len(messages) == 2:
            # 0. Si el usuario consulta sobre autoría, autores, equipo, dirección académica o créditos
            if any(k in main_query_text for k in [
                "autor", "autores", "autoría", "autoria", "creador", "creadores",
                "desarrollador", "desarrolladores", "créditos", "creditos",
                "quien hizo", "quién hizo", "quien desarrollo", "quién desarrolló",
                "quien creo", "quién creó", "equipo", "directora", "diplomatura",
                "letourneau", "comerci", "davila", "dávila", "ifab", "conicet"
            ]):
                return (
                    "Thought: El usuario consulta sobre la autoría, desarrollo, créditos institucionales o dirección académica del proyecto. Consultaré la base documental RAG.\n"
                    "Action: rag_documental_inta | autor autores autoria desarrollador equipo creditos directora"
                )

            # 0b. Si el usuario consulta sobre Harness, Ciberseguridad, Sandbox, Contenedores, Docker u OWASP
            if any(k in main_query_text for k in ["harness", "ciberseguridad", "cyberseguridad", "sandbox", "contenedor", "docker", "owasp", "guardrail", "seguridad"]):
                return (
                    "Thought: El usuario consulta sobre la integración de Agent Harness, Ciberseguridad (Guardrails), Sandbox y Contenedores en la arquitectura del proyecto. Consultaré la base documental RAG.\n"
                    "Action: rag_documental_inta | harness ciberseguridad sandbox contenedores owasp"
                )

            # 0c. Si el usuario consulta sobre Ley 26.331, OTBN, interfaz urbano-forestal o marco normativo de cuencas
            if any(k in main_query_text for k in ["26.331", "26331", "26.815", "26815", "otbn", "ley de bosques", "interfaz urbano-forestal", "iuf", "preservacion del bosque", "preservación del bosque"]) and "[Último Análisis de Drenaje Hídrico:" not in user_raw:
                return (
                    "Thought: El usuario consulta sobre el marco normativo de bosques nativos (Ley 26.331 / OTBN), protección de cuencas e interfaz urbano-forestal. Consultaré la base documental RAG.\n"
                    "Action: rag_documental_inta | marco territorial cuencas bosques nativos ley 26331 otbn interfaz urbano forestal"
                )

            # 1. Si el usuario solicita diagnóstico de drenaje / pendientes / cruce espacial / riesgo hídrico
            is_drain_query = any(
                k in main_query_text
                for k in ["drenaje", "pendiente", "escurrimiento", "erosion", "erosión", "topografia", "topografía", "dem", "cruce espacial", "cuenca", "aluvional", "interfaz"]
            )
            is_cov_only_query = any(k in main_query_text for k in ["cobertura", "coberturas", "proporcion", "proporción", "balance"]) and not is_drain_query
            if is_drain_query or (
                drain_json is not None
                and not is_cov_only_query
                and any(k in main_query_text for k in ["riesgo", "manejo", "recomendacion", "recomendación"])
            ):
                if drain_json:
                    sintesis = self._synthesize_real_data(drain_json)
                    return f"Thought: Cuento con las métricas topográficas, hidrológicas y de cruce espacial calculadas sobre el área activa.\nFINAL: {sintesis}"
                return (
                    "Thought: El usuario solicita modelar la red de drenaje hídrico superficial, pendientes y cruce espacial Cobertura × Pendiente a partir de Copernicus DEM 30m.\n"
                    f"Action: red_drenaje_hidrico | {explicit_bbox}"
                )

            # 2. Si el usuario solicita diagnóstico de coberturas y ya hay datos clasificados adjuntos
            if any(k in main_query_text for k in ["cobertura", "diagnostico", "diagnóstico", "proporcion", "proporción", "balance", "bosque", "cultivo", "urbano"]):
                if class_json and ("coberturas" in class_json or "modelo" in class_json) and not explicit_bbox_match:
                    sintesis = self._synthesize_real_data(class_json)
                    return f"Thought: Cuento con los datos exactos obtenidos de la clasificación del modelo.\nFINAL: {sintesis}"

            # 3. Si el usuario pregunta por las fuentes de imágenes o diferencias entre IA y Umbralización
            if any(k in main_query_text for k in ["imagenes", "imágenes", "fuentes", "origen", "diferencia", "comparativa", "utiliza cada", "usa cada"]):
                return (
                    "Thought: El usuario consulta sobre las fuentes de imágenes satelitales y diferencias metodológicas entre el Modelo de IA y la Umbralización. Consultaré la base documental RAG.\n"
                    "Action: rag_documental_inta | comparativa fuentes imagenes modelo ia worldcover umbralizacion sentinel"
                )

            # 4. Si el usuario pregunta sobre el tipo de agente, ReAct vs LangChain o rendimiento del agente
            if any(k in main_query_text for k in ["langchain", "react", "tipo de agente", "comparativa agente", "rendimiento agente", "framework", "agente react"]):
                return (
                    "Thought: El usuario consulta sobre el tipo de agente implementado (ReAct Nativo), la comparativa con LangChain y el análisis de rendimiento. Consultaré la base documental RAG.\n"
                    "Action: rag_documental_inta | arquitectura agente react langchain rendimiento comparativa"
                )

            # 5. Si el usuario pregunta sobre la arquitectura general, stack, tecnologías o cómo intervenir la app
            if any(k in main_query_text for k in ["stack", "arquitectura", "construida", "desarrollada", "tecnologias", "tecnologías", "librerias", "librerías", "funciona", "intervenir", "modificar", "código", "codigo"]):
                return (
                    "Thought: El usuario solicita información sobre el stack tecnológico, la arquitectura o la forma de intervenir la app. Consultaré la base documental RAG.\n"
                    "Action: rag_documental_inta | arquitectura stack tecnologias funcionamiento intervenir"
                )

            # 6. Si el usuario solicita series temporales de NDVI
            if any(k in main_query_text for k in ["ndvi", "serie", "temporal", "tendencia"]):
                return (
                    "Thought: El usuario solicita analizar la serie temporal de NDVI para evaluar tendencias.\n"
                    "Action: series_temporales_ndvi | Copo_Bosque_Nativo"
                )

            # 7. Si el usuario pregunta por coberturas pero no hay datos previos (o especificó un BBox explícito)
            if any(k in main_query_text for k in ["cobertura", "diagnostico", "diagnóstico", "proporcion", "proporción", "bosque", "cultivo", "clasificar", "worldcover", "suelo"]):
                return (
                    "Thought: El usuario solicita evaluar la distribución de coberturas del suelo con el modelo de IA.\n"
                    f"Action: clasificador_ia_worldcover | 2021 | {explicit_bbox}"
                )

            # Fallback a RAG
            return (
                "Thought: Para responder la consulta técnica, consultaré la base documental RAG.\n"
                "Action: rag_documental_inta | arquitectura stack tecnologias guia"
            )

        # Pasos intermedios y síntesis final
        if "Observation:" in last_msg:
            # Si la observación fue bloqueada por el Sandbox de Herramientas
            if "sandbox_blocked" in last_msg or "sandbox_timeout" in last_msg:
                parsed_block = self._extract_json_from_text(last_msg)
                msg_block = parsed_block.get("mensaje", last_msg) if parsed_block else last_msg
                tipo_block = parsed_block.get("tipo_bloqueo", "Sandbox de Ejecución") if parsed_block else "Sandbox"
                return (
                    "Thought: El Sandbox de ejecución de herramientas detuvo la operación por políticas de seguridad y cuota de recursos.\n"
                    f"FINAL: 🔒 **Protección de Sandbox Activada ({tipo_block}):** {msg_block}"
                )

            # Si la observación provino de RAG documental
            if "rag_documental_inta" in str(messages[1:]) or "--- Documento" in last_msg:
                clean_obs = last_msg.replace("Observation:", "").split("Continuá")[0].strip()
                return f"Thought: He recuperado la información técnica de la base de conocimiento.\nFINAL: {clean_obs}"

            # Extraer los datos reales acumulados en los mensajes
            prev_classification_data = None
            for m in messages:
                if m["role"] == "user" and m["content"].startswith("Observation:"):
                    content = m["content"]
                    parsed = self._extract_json_from_text(content)
                    if parsed and any(k in parsed for k in ["coberturas", "modelo", "estadisticas_ndvi", "pendientes"]):
                        prev_classification_data = parsed

            # Si la consulta del usuario traía una clasificación activa previa
            if not prev_classification_data:
                prev_classification_data = self._extract_json_from_text(user_raw)

            if prev_classification_data:
                sintesis = self._synthesize_real_data(prev_classification_data)
                return f"Thought: He analizado las observaciones numéricas reales generadas por la herramienta.\nFINAL: {sintesis}"

        # Si no hubo observación pero el user_raw tenía JSON embebido
        if query_json:
            sintesis = self._synthesize_real_data(query_json)
            return f"FINAL: {sintesis}"

        return "FINAL: Consulta procesada correctamente en base a los datos disponibles."

    def _finalize_run_metrics(self, trace: List[Dict[str, Any]], total_ms: float, blocked: bool = False) -> Dict[str, Any]:
        """Calcula y acumula las métricas de telemetría de la consulta actual y de la sesión."""
        p_tok = sum(int(s.get("prompt_tokens", 0)) for s in trace)
        c_tok = sum(int(s.get("completion_tokens", 0)) for s in trace)
        t_tok = sum(int(s.get("total_tokens", 0)) for s in trace)
        llm_ms = round(sum(float(s.get("llm_latency_ms", 0.0)) for s in trace), 1)
        tool_ms = round(sum(float(s.get("tool_latency_ms", 0.0)) for s in trace), 1)
        tools_used = [
            s.get("action")
            for s in trace
            if s.get("action") and s.get("action") not in ("security_guardrail_block", "harness_grounding_redirect")
        ]
        mode = trace[-1].get("inference_mode", "Motor Local") if trace else "Motor Local"

        metrics = {
            "total_latency_ms": round(total_ms, 1),
            "llm_latency_ms": llm_ms,
            "tool_latency_ms": tool_ms,
            "prompt_tokens": p_tok,
            "completion_tokens": c_tok,
            "total_tokens": t_tok,
            "steps_used": len(trace),
            "max_steps": self.max_steps,
            "tools_called": tools_used,
            "inference_mode": mode,
            "security_status": "Bloqueado por Guardrail" if blocked else "OK (Validado)",
        }
        self.last_run_metrics = metrics

        if not hasattr(self, "session_metrics") or not isinstance(self.session_metrics, dict):
            self.session_metrics = {
                "queries_count": 0,
                "total_tokens": 0,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_latency_ms": 0.0,
                "tools_invoked": 0,
                "security_blocks": 0,
            }
        self.session_metrics["queries_count"] += 1
        self.session_metrics["total_tokens"] += t_tok
        self.session_metrics["prompt_tokens"] += p_tok
        self.session_metrics["completion_tokens"] += c_tok
        self.session_metrics["total_latency_ms"] = round(self.session_metrics["total_latency_ms"] + total_ms, 1)
        self.session_metrics["tools_invoked"] += len(tools_used)
        if blocked:
            self.session_metrics["security_blocks"] += 1

        return metrics

    def run(self, query: str) -> Tuple[str, List[Dict[str, Any]]]:
        """
        Ejecuta el Agent Runtime Harness completo para una consulta de usuario:
        1. Verifica Input Guardrails (Ciberseguridad OWASP LLM01).
        2. Orquesta el bucle ReAct con límite de pasos y telemetría de latencia y tokens.
        3. Ejecuta herramientas dentro del Sandbox de Aplicación.
        4. Aplica Output Guardrails (prevención de fuga de secretos OWASP LLM02).
        Retorna (respuesta_final, traza_de_pasos).
        """
        t0 = time.perf_counter()
        is_safe, check_result = validate_user_input(query)
        if not is_safe:
            elapsed_ms = round((time.perf_counter() - t0) * 1000, 2)
            trace = [{
                "step": 1,
                "thought_and_output": "Thought: Input Guardrail interceptó la consulta antes de invocar al modelo LLM por políticas de ciberseguridad.",
                "action": "security_guardrail_block",
                "input": query[:120],
                "observation": check_result,
                "latency_ms": elapsed_ms,
                "llm_latency_ms": 0.0,
                "tool_latency_ms": 0.0,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
                "inference_mode": "Input Guardrail (OWASP LLM01)"
            }]
            self._finalize_run_metrics(trace, elapsed_ms, blocked=True)
            return check_result, trace

        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": query}
        ]
        trace: List[Dict[str, Any]] = []

        for step in range(1, self.max_steps + 1):
            step_t0 = time.perf_counter()
            llm_t0 = time.perf_counter()
            llm_output = sanitize_output(self._call_llm(messages))
            llm_ms = round((time.perf_counter() - llm_t0) * 1000, 1)
            usage_info = getattr(self, "_last_step_usage", {}) or {}
            messages.append({"role": "assistant", "content": llm_output})

            final_answer = parse_final_answer(llm_output)
            action = parse_action(llm_output)

            # Guardrail de Grounding en Runtime Harness: impedir FINAL sin consulta RAG previa
            has_rag_call = any(s.get("action") == "rag_documental_inta" for s in trace)
            if (final_answer or not action) and not has_rag_call and self._requires_rag_grounding(query) and step < self.max_steps:
                rag_tool = self.registry.get("rag_documental_inta")
                if rag_tool:
                    user_clean_q = query.split("[BBox activo:")[0].strip()
                    tool_t0 = time.perf_counter()
                    observation = rag_tool.run(user_clean_q)
                    tool_ms = round((time.perf_counter() - tool_t0) * 1000, 1)
                    step_ms = round((time.perf_counter() - step_t0) * 1000, 1)
                    trace.append({
                        "step": step,
                        "thought_and_output": llm_output,
                        "action": "rag_documental_inta",
                        "input": user_clean_q,
                        "observation": observation,
                        "latency_ms": step_ms,
                        "llm_latency_ms": llm_ms,
                        "tool_latency_ms": tool_ms,
                        "prompt_tokens": usage_info.get("prompt_tokens", 0),
                        "completion_tokens": usage_info.get("completion_tokens", 0),
                        "total_tokens": usage_info.get("total_tokens", 0),
                        "inference_mode": usage_info.get("inference_mode", "LLM")
                    })
                    # Normalizar el último mensaje en el historial para mantener un ciclo ReAct limpio hacia el LLM
                    messages[-1]["content"] = (
                        f"Thought: Debo consultar la documentación oficial mediante rag_documental_inta antes de responder.\n"
                        f"Action: rag_documental_inta | {user_clean_q}"
                    )
                    messages.append({
                        "role": "user",
                        "content": (
                            f"Observation: {observation}\n"
                            "Basate EXCLUSIVAMENTE en los hechos y nombres de esta Observation (sin inventar nombres, cargos ni secciones) "
                            "y respondé ahora con 'Thought:' y 'FINAL:'."
                        )
                    })
                    continue

            # Caso 1: El modelo finalizó
            if final_answer and not action:
                step_ms = round((time.perf_counter() - step_t0) * 1000, 1)
                trace.append({
                    "step": step,
                    "thought_and_output": llm_output,
                    "action": None,
                    "observation": None,
                    "latency_ms": step_ms,
                    "llm_latency_ms": llm_ms,
                    "tool_latency_ms": 0.0,
                    "prompt_tokens": usage_info.get("prompt_tokens", 0),
                    "completion_tokens": usage_info.get("completion_tokens", 0),
                    "total_tokens": usage_info.get("total_tokens", 0),
                    "inference_mode": usage_info.get("inference_mode", "LLM")
                })
                total_ms = round((time.perf_counter() - t0) * 1000, 1)
                self._finalize_run_metrics(trace, total_ms)
                return sanitize_output(final_answer), trace

            # Caso 2: El modelo solicitó una acción
            if action:
                tool_name, tool_input = action
                tool = self.registry.get(tool_name)

                tool_t0 = time.perf_counter()
                if not tool:
                    available = list(self.registry.list_tools().keys())
                    observation = f"Error: Herramienta '{tool_name}' no existe. Disponibles: {available}"
                else:
                    observation = tool.run(tool_input)
                tool_ms = round((time.perf_counter() - tool_t0) * 1000, 1)

                step_ms = round((time.perf_counter() - step_t0) * 1000, 1)
                trace.append({
                    "step": step,
                    "thought_and_output": llm_output,
                    "action": tool_name,
                    "input": tool_input,
                    "observation": observation,
                    "latency_ms": step_ms,
                    "llm_latency_ms": llm_ms,
                    "tool_latency_ms": tool_ms,
                    "prompt_tokens": usage_info.get("prompt_tokens", 0),
                    "completion_tokens": usage_info.get("completion_tokens", 0),
                    "total_tokens": usage_info.get("total_tokens", 0),
                    "inference_mode": usage_info.get("inference_mode", "LLM")
                })

                messages.append({
                    "role": "user",
                    "content": f"Observation: {observation}\nContinuá con el siguiente paso. Si ya tenés la respuesta completa, utilizá 'FINAL:'."
                })
                continue

            # Caso 3: Respuesta sin formato reconocido
            step_ms = round((time.perf_counter() - step_t0) * 1000, 1)
            trace.append({
                "step": step,
                "thought_and_output": llm_output,
                "action": None,
                "observation": None,
                "latency_ms": step_ms,
                "llm_latency_ms": llm_ms,
                "tool_latency_ms": 0.0,
                "prompt_tokens": usage_info.get("prompt_tokens", 0),
                "completion_tokens": usage_info.get("completion_tokens", 0),
                "total_tokens": usage_info.get("total_tokens", 0),
                "inference_mode": usage_info.get("inference_mode", "LLM")
            })
            total_ms = round((time.perf_counter() - t0) * 1000, 1)
            self._finalize_run_metrics(trace, total_ms)
            return sanitize_output(llm_output), trace

        total_ms = round((time.perf_counter() - t0) * 1000, 1)
        self._finalize_run_metrics(trace, total_ms)
        return "Se alcanzó el límite máximo de pasos sin obtener una respuesta final definitiva.", trace
