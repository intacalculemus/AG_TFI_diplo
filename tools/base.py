"""
Módulo Base de Definición y Registro de Herramientas (Tools)
"""
from dataclasses import dataclass
from typing import Callable, Dict, Any, Optional
import json

@dataclass
class Tool:
    name: str
    description: str
    func: Callable[[str], str]
    usage_example: str = ""

    def run(self, tool_input: str) -> str:
        """Ejecuta la función asociada capturando errores de runtime."""
        try:
            return self.func(tool_input)
        except Exception as e:
            return f"Error al ejecutar la herramienta '{self.name}': {str(e)}"


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
