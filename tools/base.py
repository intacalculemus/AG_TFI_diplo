"""
Módulo Base de Definición y Registro de Herramientas (Tools) con Sandbox Integrado
"""
from dataclasses import dataclass
from typing import Callable, Dict, Any, Optional
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
import json

@dataclass
class Tool:
    name: str
    description: str
    func: Callable[[str], str]
    usage_example: str = ""
    timeout_seconds: float = 45.0
    max_area_ha: float = 100000.0

    def run(self, tool_input: str) -> str:
        """
        Ejecuta la función asociada dentro del Sandbox de Aplicación:
        1. Valida parámetros contra Path Traversal, geometría BBox y cuota máxima de hectáreas (RAM).
        2. Controla el tiempo máximo de ejecución (timeout).
        3. Sanitiza la salida para prevenir fuga de secretos.
        """
        from agent.security import validate_tool_execution, sanitize_output

        is_valid, validated_or_err = validate_tool_execution(
            tool_name=self.name,
            tool_input=tool_input,
            max_area_ha=self.max_area_ha
        )
        if not is_valid:
            return validated_or_err

        try:
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(self.func, validated_or_err)
                raw_result = future.result(timeout=self.timeout_seconds)
            return sanitize_output(str(raw_result))
        except FuturesTimeoutError:
            return json.dumps({
                "status": "sandbox_timeout",
                "mensaje": f"El Sandbox interrumpió la herramienta '{self.name}' por superar el tiempo máximo permitido ({self.timeout_seconds}s)."
            }, ensure_ascii=False)
        except Exception as e:
            return sanitize_output(f"Error al ejecutar la herramienta '{self.name}': {str(e)}")


class ToolRegistry:
    """Registro centralizado de herramientas para el agente."""

    def __init__(self):
        self._tools: Dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        """Registra una nueva herramienta."""
        self._tools[tool.name] = tool

    def get(self, name: str) -> Optional[Tool]:
        """Obtiene una herramienta por nombre."""
        return self._tools.get(name)

    def list_tools(self) -> Dict[str, Tool]:
        """Retorna todas las herramientas registradas."""
        return self._tools

    def build_system_description(self) -> str:
        """Genera el texto estructurado de descripción para el System Prompt."""
        lines = []
        for tool in self._tools.values():
            lines.append(f"### Herramienta: `{tool.name}`")
            lines.append(f"Descripción: {tool.description}")
            if tool.usage_example:
                lines.append(f"Formato de uso:\n{tool.usage_example}")
            lines.append("-" * 40)
        return "\n".join(lines)


# Registro global por defecto
default_registry = ToolRegistry()
