"""
Base de Conocimiento y Motor de Recuperación Documental (RAG)
"""
import os
import re
from typing import List, Dict, Any, Optional
from pathlib import Path
from config import RAG_DATA_DIR

class SimpleKnowledgeBase:
    """
    Gestor de base de conocimiento local para normativas, manuales INTA y reportes técnicos.
    Implementa indexación por fragmentos (chunks) y recuperación semántica/léxica.
    """

    def __init__(self, corpus_path: Optional[Path] = None):
        self.corpus_path = corpus_path or (RAG_DATA_DIR / "corpus_ejemplo.txt")
        self.documents: List[Dict[str, str]] = []
        self._load_corpus()

    def _load_corpus(self) -> None:
        """Carga y parsea el archivo de corpus."""
        if not self.corpus_path.exists():
            return

        with open(self.corpus_path, "r", encoding="utf-8") as f:
            raw_text = f.read()

        # Separar por documentos etiquetados con [DOC_ID: ...]
        chunks = re.split(r"\[DOC_ID:\s*([A-Za-z0-9_]+)\]", raw_text)
        
        # chunks[0] es texto anterior al primer tag
        for i in range(1, len(chunks), 2):
            doc_id = chunks[i].strip()
            content = chunks[i+1].strip() if i+1 < len(chunks) else ""
            self.documents.append({
                "doc_id": doc_id,
                "content": content
            })

    def search(self, query: str, top_k: int = 2) -> List[Dict[str, Any]]:
        """
        Búsqueda por coincidencia de términos y relevancia de palabras clave.
        Retorna los mejores fragmentos documentales.
        """
        if not self.documents:
            return [{"error": "Base de conocimiento vacía."}]

        query_tokens = set(re.findall(r"\w+", query.lower()))
        scored_docs = []

        for doc in self.documents:
            text = (doc["doc_id"] + " " + doc["content"]).lower()
            doc_tokens = set(re.findall(r"\w+", text))
            
            # Cálculo de superposición de términos clave
            intersection = query_tokens.intersection(doc_tokens)
            score = len(intersection) / (len(query_tokens) + 1e-5)
            
            scored_docs.append((score, doc))

        # Ordenar por mayor score
        scored_docs.sort(key=lambda x: x[0], reverse=True)
        top_results = [doc for score, doc in scored_docs[:top_k] if score > 0]
        
        # Fallback: Si no hubo coincidencias exactas, retornar el primer documento relevante
        if not top_results and self.documents:
            top_results = [self.documents[0]]

        return top_results
