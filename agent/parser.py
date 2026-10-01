"""
Módulo de Parseo Robusto para Respuestas del Agente ReAct
"""
import re
from typing import Optional, Tuple

ACTION_REGEX = re.compile(r"^\s*Action:\s*([\w\-]+)\s*\|\s*(.*)\s*$", re.MULTILINE | re.IGNORECASE)
FINAL_REGEX = re.compile(r"FINAL:\s*(.*)", re.DOTALL | re.IGNORECASE)

def parse_action(llm_output: str) -> Optional[Tuple[str, str]]:
    """
    Extrae (tool_name, tool_input) del texto generado por el LLM.
    Retorna None si no se detecta una invocación válida de Action.
    """
    match = ACTION_REGEX.search(llm_output)
    if not match:
        return None
    tool_name = match.group(1).strip()
    tool_input = match.group(2).strip()
    return tool_name, tool_input

def parse_final_answer(llm_output: str) -> Optional[str]:
    """
    Extrae la respuesta final cuando el modelo emite 'FINAL: ...'.
    """
    match = FINAL_REGEX.search(llm_output)
    if not match:
        return None
    return match.group(1).strip()
