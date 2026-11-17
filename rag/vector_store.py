"""
Base de Conocimiento y Motor de Recuperación Documental (RAG)
"""
import re
import unicodedata
from typing import List, Dict, Any, Optional, Set
from pathlib import Path
from config import RAG_DATA_DIR

SPANISH_STOPWORDS: Set[str] = {
    "a", "al", "algo", "algunas", "algunos", "ante", "antes", "aquel", "aquella",
    "aquellas", "aquello", "aquellos", "aqui", "asi", "aun", "bajo", "bien",
    "cada", "casi", "como", "con", "contra", "cual", "cuales", "cuando",
    "cuanto", "cuantos", "de", "del", "desde", "donde", "dos", "el", "ella",
    "ellas", "ello", "ellos", "en", "entre", "era", "eramos", "eran", "eras",
    "eres", "es", "esa", "esas", "ese", "eso", "esos", "esta", "estaba",
    "estaban", "estado", "estamos", "estan", "estar", "estas", "este", "esto",
    "estos", "estoy", "etc", "fue", "fueron", "fui", "fuimos", "ha", "haber",
    "habia", "habian", "hace", "hacen", "hacer", "hacia", "han", "has", "hasta",
    "hay", "he", "hemos", "hizo", "la", "las", "le", "les", "lo", "los", "mas",
    "me", "mi", "mis", "mucho", "muchos", "muy", "nada", "ni", "no", "nos",
    "nosotros", "nuestra", "nuestro", "o", "os", "otra", "otras", "otro",
    "otros", "para", "pero", "poco", "por", "porque", "que", "quien",
    "quienes", "se", "sea", "segun", "ser", "si", "sin", "sobre", "sois",
    "solamente", "solo", "somos", "son", "soy", "su", "sus", "tal", "tambien",
    "tan", "tanto", "te", "tendria", "tener", "tengo", "ti", "tiene", "tienen",
    "toda", "todas", "todo", "todos", "tu", "tus", "u", "un", "una", "unas",
    "uno", "unos", "usted", "ustedes", "va", "vamos", "van", "varias", "varios",
    "vaya", "ver", "vez", "vos", "y", "ya", "yo",
}


def _normalize_text(text: str) -> str:
    """Convierte a minúsculas y elimina tildes/diacríticos para búsqueda robusta."""
    nfd = unicodedata.normalize("NFD", text.lower())
    return "".join(ch for ch in nfd if unicodedata.category(ch) != "Mn")


def _stem_spanish_token(token: str) -> str:
    """Normalización morfológica ligera para variantes plurales y derivadas comunes."""
    if len(token) <= 4:
        return token
    for suffix, min_root in (
        ("ciones", 4),
        ("siones", 4),
        ("dores", 4),
        ("doras", 4),
        ("orias", 4),
        ("orios", 4),
        ("oria", 4),
        ("orio", 4),
        ("ores", 4),
        ("oras", 4),
        ("es", 4),
        ("s", 4),
    ):
        if token.endswith(suffix) and len(token) - len(suffix) >= min_root:
            return token[: -len(suffix)]
    return token


def _tokenize(text: str, remove_stopwords: bool = True) -> Set[str]:
    """Extrae tokens normalizados y su raíz ligera, filtrando stopwords en español."""
    normalized = _normalize_text(text)
    raw_tokens = re.findall(r"[a-z0-9_]+", normalized)
    tokens: Set[str] = set()
    for tok in raw_tokens:
        if remove_stopwords and tok in SPANISH_STOPWORDS:
            continue
        if len(tok) <= 1:
            continue
        tokens.add(tok)
        stem = _stem_spanish_token(tok)
        if len(stem) >= 3:
            tokens.add(stem)
    return tokens


class SimpleKnowledgeBase:
    """
    Gestor de base de conocimiento local para documentación del proyecto,
    autoría/créditos, arquitectura del stack, normativas y guías técnicas.
    Implementa indexación por fragmentos [DOC_ID] y recuperación léxica ponderada.
    """

    def __init__(self, corpus_path: Optional[Path] = None):
        self.corpus_path = corpus_path or (RAG_DATA_DIR / "corpus_ejemplo.txt")
        self.documents: List[Dict[str, Any]] = []
        self._corpus_mtime: Optional[float] = None
        self._load_corpus()

    def _load_corpus(self) -> None:
        """Carga y parsea el archivo de corpus estructurado por bloques [DOC_ID]."""
        self.documents = []
        if not self.corpus_path.exists():
            self._corpus_mtime = None
            return

        self._corpus_mtime = self.corpus_path.stat().st_mtime
        with open(self.corpus_path, "r", encoding="utf-8") as f:
            raw_text = f.read()

        # Separar por documentos etiquetados con [DOC_ID: ...]
        chunks = re.split(r"\[DOC_ID:\s*([A-Za-z0-9_]+)\]", raw_text)

        # chunks[0] es texto anterior al primer tag
        for i in range(1, len(chunks), 2):
            doc_id = chunks[i].strip()
            content = chunks[i + 1].strip() if i + 1 < len(chunks) else ""
            title_match = re.search(r"^T[ií]tulo:\s*(.+)$", content, re.MULTILINE | re.IGNORECASE)
            title = title_match.group(1).strip() if title_match else ""
            header_text = f"{doc_id.replace('_', ' ')} {title}"
            self.documents.append({
                "doc_id": doc_id,
                "title": title,
                "content": content,
                "header_tokens": _tokenize(header_text),
                "body_tokens": _tokenize(content),
            })

    def _reload_if_changed(self) -> None:
        """Recarga el corpus automáticamente si el archivo en disco fue modificado."""
        if not self.corpus_path.exists():
            return
        current_mtime = self.corpus_path.stat().st_mtime
        if self._corpus_mtime != current_mtime:
            self._load_corpus()

    def search(self, query: str, top_k: int = 2) -> List[Dict[str, Any]]:
        """
        Búsqueda léxica ponderada: filtra stopwords en español y pondera
        coincidencias en identificador/título (x3) y cuerpo (x1).
        """
        self._reload_if_changed()
        if not self.documents:
            return [{"error": "Base de conocimiento vacía."}]

        query_tokens = _tokenize(query, remove_stopwords=True)
        if not query_tokens:
            query_tokens = _tokenize(query, remove_stopwords=False)
        if not query_tokens:
            return []

        scored_docs = []
        denom = len(query_tokens) + 1e-5

        for doc in self.documents:
            header_hits = len(query_tokens.intersection(doc["header_tokens"]))
            body_hits = len(query_tokens.intersection(doc["body_tokens"]))
            if header_hits == 0 and body_hits == 0:
                continue
            score = (3.0 * header_hits + 1.0 * body_hits) / denom
            scored_docs.append((score, doc))

        scored_docs.sort(key=lambda x: x[0], reverse=True)
        return [
            {"doc_id": doc["doc_id"], "content": doc["content"]}
            for _, doc in scored_docs[:top_k]
        ]
