"""
Herramienta de Búsqueda RAG sobre Documentación Técnica de INTA y Normativas Ambientales
"""
import json
from rag.vector_store import SimpleKnowledgeBase

# Instancia singleton de la base de conocimiento
_kb = SimpleKnowledgeBase()

def search_technical_rag(tool_input: str) -> str:
    """
    Busca información en manuales de INTA, leyes de bosques (Ley 26.331) y reportes de zonificación.
    Input: consulta en texto libre (ej: 'categoría rojo ley de bosques', 'comportamiento ndvi chaco seco').
    """
    query = tool_input.strip()
    if not query:
        return "Debe ingresar una consulta para la búsqueda documental."

    results = _kb.search(query, top_k=2)
    
    if not results:
        return "No se encontraron documentos relevantes para la consulta."

    formatted_outputs = []
    for r in results:
        doc_id = r.get("doc_id", "DESCONOCIDO")
        content = r.get("content", "")
        formatted_outputs.append(f"--- Documento [{doc_id}] ---\n{content}")

    return "\n\n".join(formatted_outputs)
