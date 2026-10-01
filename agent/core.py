"""
Motor Principal del Agente ReAct Geoambiental (GeoReActAgent)
Incluye Sintetizador Dinámico de Observaciones Reales (ESA WorldCover, Sentinel-2, NDVI, RAG)
"""
from typing import List, Dict, Any, Tuple, Optional
import os
import re
import json

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
        self.client = self._init_client()

    def _init_client(self) -> Optional[Any]:
        """Inicializa el cliente de API OpenAI o HuggingFace."""
        if not HAS_OPENAI or not LLM_API_KEY:
            return None
        return OpenAI(
            base_url=LLM_BASE_URL,
            api_key=LLM_API_KEY
        )

    def _call_llm(self, messages: List[Dict[str, str]]) -> str:
        """Invoca al modelo de lenguaje o genera una respuesta dinámica sobre datos reales."""
        if self.client is None:
            return self._mock_llm_reasoning(messages)

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=self.temperature
            )
            return response.choices[0].message.content or ""
        except Exception as e:
            return f"Error en la llamada al LLM: {str(e)}"

    def _extract_json_from_text(self, text: str) -> Optional[Dict[str, Any]]:
        """Intenta extraer un objeto JSON embebido en una cadena de texto."""
        match = re.search(r"(\{.*\})", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except Exception:
                pass
        return None

    def _synthesize_real_data(self, data: Dict[str, Any], context_normativa: str = "") -> str:
        """Genera una síntesis técnica y agroambiental rigurosa utilizando exactamente los números de la clasificación real."""
        # 1. Caso Modelo IA ESA WorldCover 10m
        if "ESA WorldCover" in str(data.get("modelo", "")) or any("codigo" in str(v) for v in data.get("coberturas", {}).values()):
            coberturas = data.get("coberturas", {})
            total_ha = data.get("superficie_total_ha", 0.0)
            total_px = data.get("total_pixeles_10m", 0)
            year = data.get("año_referencia", "2021")

            sorted_c = sorted(coberturas.values(), key=lambda x: x.get("hectareas", 0), reverse=True)
            desglose = []
            for c in sorted_c:
                desglose.append(f"• **{c['nombre']}:** {c['porcentaje']}% ({c['hectareas']:,.1f} ha)")

            # Ubicación administrativa si está disponible
            ub_info = data.get("ubicacion_administrativa", {})
            loc_line = f"📍 **Ubicación Territorial:** {ub_info.get('texto_formateado')}\n" if isinstance(ub_info, dict) and ub_info.get("texto_formateado") else ""

            lines = [
                f"### 📊 Diagnóstico de Coberturas - Modelo de IA ESA WorldCover 10m (Año {year})",
                f"{loc_line}Para el área de interés delimitada (**{total_ha:,.1f} ha**, {total_px:,} píxeles clasificados a 10m de resolución), los resultados son:",
                "",
                "\n".join(desglose),
                "",
                "**Interpretación Agroambiental e Hídrica:**",
            ]

            # Interpretación cuantitativa de coberturas
            bosque_ha = sum(c["hectareas"] for c in coberturas.values() if "Bosque" in c.get("nombre", "") or "Tree" in c.get("nombre", ""))
            cultivo_ha = sum(c["hectareas"] for c in coberturas.values() if "Cultivo" in c.get("nombre", "") or "Crop" in c.get("nombre", ""))
            pasturas_ha = sum(c["hectareas"] for c in coberturas.values() if "Pastizal" in c.get("nombre", "") or "Grassland" in c.get("nombre", ""))
            agua_ha = sum(c["hectareas"] for c in coberturas.values() if "Agua" in c.get("nombre", "") or "Humedal" in c.get("nombre", ""))

            lines.append(f"- **Masa Forestal / Leñosa:** Representa {round((bosque_ha/total_ha)*100, 1) if total_ha > 0 else 0}% ({bosque_ha:,.1f} ha), fundamental para la regulación del balance hídrico y la conservación del suelo.")
            if cultivo_ha > 0 or pasturas_ha > 0:
                lines.append(f"- **Área Productiva / Antrópica:** Ocupa {cultivo_ha:,.1f} ha de cultivos y {pasturas_ha:,.1f} ha de pastizales/sabanas.")
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

        return str(data.get("resumen_ejecutivo", "Datos procesados correctamente."))

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
        main_query_text = user_raw.split("[")[0].strip().lower()
        query_json = self._extract_json_from_text(user_raw)

        last_msg = messages[-1]["content"]

        # Paso inicial: razonar qué herramienta invocar según la intención
        if len(messages) == 2:
            # 1. Si el usuario solicita diagnóstico de coberturas y ya hay datos clasificados adjuntos
            if any(k in main_query_text for k in ["cobertura", "diagnostico", "diagnóstico", "proporcion", "proporción", "balance", "bosque", "cultivo"]):
                if query_json and ("coberturas" in query_json or "modelo" in query_json):
                    sintesis = self._synthesize_real_data(query_json)
                    return f"Thought: Cuento con los datos exactos obtenidos de la clasificación del modelo.\nFINAL: {sintesis}"

            # 2. Si el usuario pregunta por las fuentes de imágenes o diferencias entre IA y Umbralización
            if any(k in main_query_text for k in ["imagenes", "imágenes", "fuentes", "origen", "diferencia", "comparativa", "utiliza cada", "usa cada"]):
                return (
                    "Thought: El usuario consulta sobre las fuentes de imágenes satelitales y diferencias metodológicas entre el Modelo de IA y la Umbralización. Consultaré la base documental RAG.\n"
                    "Action: rag_documental_inta | comparativa fuentes imagenes modelo ia worldcover umbralizacion sentinel"
                )

            # 3. Si el usuario pregunta sobre la arquitectura, stack, tecnologías o cómo intervenir la app
            if any(k in main_query_text for k in ["stack", "arquitectura", "construida", "desarrollada", "tecnologias", "tecnologías", "librerias", "librerías", "funciona", "intervenir", "modificar", "código", "codigo"]):
                return (
                    "Thought: El usuario solicita información sobre el stack tecnológico, la arquitectura o la forma de intervenir la app. Consultaré la base documental RAG.\n"
                    "Action: rag_documental_inta | arquitectura stack tecnologias funcionamiento intervenir"
                )

            # 3. Si el usuario pregunta por coberturas pero no hay datos previos
            if any(k in main_query_text for k in ["cobertura", "diagnostico", "diagnóstico", "proporcion", "proporción", "bosque", "cultivo", "clasificar", "worldcover", "suelo"]):
                return (
                    "Thought: El usuario solicita evaluar la distribución de coberturas del suelo con el modelo de IA.\n"
                    "Action: clasificador_ia_worldcover | 2021 | [-62.2, -26.15, -61.9, -25.85]"
                )

            # 4. Si el usuario solicita series temporales
            if any(k in main_query_text for k in ["ndvi", "serie", "temporal", "tendencia"]):
                return (
                    "Thought: El usuario solicita analizar la serie temporal de NDVI para evaluar tendencias.\n"
                    "Action: series_temporales_ndvi | Copo_Bosque_Nativo"
                )

            # Fallback a RAG
            return (
                "Thought: Para responder la consulta técnica, consultaré la base documental RAG.\n"
                "Action: rag_documental_inta | arquitectura stack tecnologias guia"
            )

        # Pasos intermedios y síntesis final
        if "Observation:" in last_msg:
            # Si la observación provino de RAG documental
            if "rag_documental_inta" in str(messages) or "--- Documento" in last_msg:
                clean_obs = last_msg.replace("Observation:", "").split("Continuá")[0].strip()
                return f"Thought: He recuperado la información técnica de la base de conocimiento.\nFINAL: {clean_obs}"

            # Extraer los datos reales acumulados en los mensajes
            prev_classification_data = None
            for m in messages:
                if m["role"] == "user" and m["content"].startswith("Observation:"):
                    content = m["content"]
                    parsed = self._extract_json_from_text(content)
                    if parsed and ("coberturas" in parsed or "modelo" in parsed):
                        prev_classification_data = parsed

            # Si la consulta del usuario traía una clasificación activa previa
            if not prev_classification_data:
                prev_classification_data = self._extract_json_from_text(user_query)

            if prev_classification_data:
                sintesis = self._synthesize_real_data(prev_classification_data)
                return f"Thought: He analizado las observaciones numéricas reales generadas por el modelo de clasificación.\nFINAL: {sintesis}"

        # Si no hubo observación pero el user_query tenía JSON embebido
        query_json = self._extract_json_from_text(user_query)
        if query_json:
            sintesis = self._synthesize_real_data(query_json)
            return f"FINAL: {sintesis}"

        return "FINAL: Consulta procesada correctamente en base a los datos disponibles."

    def run(self, query: str) -> Tuple[str, List[Dict[str, Any]]]:
        """
        Ejecuta el ciclo ReAct completo para una consulta de usuario.
        Retorna (respuesta_final, traza_de_pasos).
        """
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": query}
        ]
        trace: List[Dict[str, Any]] = []

        for step in range(1, self.max_steps + 1):
            llm_output = self._call_llm(messages)
            messages.append({"role": "assistant", "content": llm_output})

            final_answer = parse_final_answer(llm_output)
            action = parse_action(llm_output)

            # Caso 1: El modelo finalizó
            if final_answer and not action:
                trace.append({
                    "step": step,
                    "thought_and_output": llm_output,
                    "action": None,
                    "observation": None
                })
                return final_answer, trace

            # Caso 2: El modelo solicitó una acción
            if action:
                tool_name, tool_input = action
                tool = self.registry.get(tool_name)

                if not tool:
                    available = list(self.registry.list_tools().keys())
                    observation = f"Error: Herramienta '{tool_name}' no existe. Disponibles: {available}"
                else:
                    observation = tool.run(tool_input)

                trace.append({
                    "step": step,
                    "thought_and_output": llm_output,
                    "action": tool_name,
                    "input": tool_input,
                    "observation": observation
                })

                messages.append({
                    "role": "user",
                    "content": f"Observation: {observation}\nContinuá con el siguiente paso. Si ya tenés la respuesta completa, utilizá 'FINAL:'."
                })
                continue

            # Caso 3: Respuesta sin formato reconocido
            trace.append({
                "step": step,
                "thought_and_output": llm_output,
                "action": None,
                "observation": None
            })
            return llm_output, trace

        return "Se alcanzó el límite máximo de pasos sin obtener una respuesta final definitiva.", trace
