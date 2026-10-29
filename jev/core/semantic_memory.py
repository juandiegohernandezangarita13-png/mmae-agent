"""
Memoria Semántica Asociativa y Vectorial en Python Puro para JEV.
Permite recuperar soluciones previas, snippets y episodios basados en similitud
semántica (TF-IDF + Coseno + BM25) sin requerir bases de datos vectoriales pesadas
ni compiladores de C++ externos.
"""
from typing import List, Dict, Any, Optional, Tuple
import math
import re
import json
from pathlib import Path


class SemanticMemoryIndex:
    """Índice de memoria semántica con vectorización de términos y similitud coseno."""

    def __init__(self, storage_path: Optional[Path] = None):
        self.storage_path = storage_path
        self.documents: List[Dict[str, Any]] = []
        self.vocabulary: Dict[str, int] = {}
        self.idf: Dict[str, float] = {}
        if self.storage_path and self.storage_path.exists():
            self.load()

    def _tokenize(self, text: str) -> List[str]:
        """Normaliza y divide el texto en tokens alfanuméricos."""
        return re.findall(r"\b[a-zA-Z0-9_\-\.]{2,}\b", text.lower())

    def add_entry(self, entry_id: str, title: str, content: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        """Añade un nuevo documento o episodio a la memoria semántica."""
        doc = {
            "id": entry_id,
            "title": title,
            "content": content,
            "metadata": metadata or {}
        }
        self.documents.append(doc)
        self._recompute_index()
        if self.storage_path:
            self.save()

    def _recompute_index(self) -> None:
        """Recalcula las frecuencias de documento (IDF) del corpus."""
        doc_count = len(self.documents)
        if doc_count == 0:
            return

        df: Dict[str, int] = {}
        for doc in self.documents:
            combined = f"{doc['title']} {doc['content']}"
            unique_terms = set(self._tokenize(combined))
            for term in unique_terms:
                df[term] = df.get(term, 0) + 1

        self.idf = {term: math.log((doc_count + 1) / (count + 1)) + 1.0 for term, count in df.items()}

    def _vectorize(self, text: str) -> Dict[str, float]:
        """Convierte una cadena de texto en un vector TF-IDF disperso."""
        tokens = self._tokenize(text)
        if not tokens:
            return {}

        tf: Dict[str, float] = {}
        for t in tokens:
            tf[t] = tf.get(t, 0.0) + 1.0

        vector: Dict[str, float] = {}
        for t, freq in tf.items():
            if t in self.idf:
                vector[t] = (freq / len(tokens)) * self.idf[t]

        # Normalización euclidiana L2
        norm = math.sqrt(sum(v * v for v in vector.values()))
        if norm > 0:
            vector = {k: v / norm for k, v in vector.items()}
        return vector

    def search(self, query: str, top_k: int = 3, threshold: float = 0.05) -> List[Dict[str, Any]]:
        """
        Recupera las memorias más relevantes mediante similitud coseno.
        """
        if not self.documents:
            return []

        q_vec = self._vectorize(query)
        if not q_vec:
            return []

        results: List[Tuple[float, Dict[str, Any]]] = []

        for doc in self.documents:
            doc_text = f"{doc['title']} {doc['content']}"
            doc_vec = self._vectorize(doc_text)
            # Producto punto (similitud coseno de vectores unitarios)
            score = sum(q_vec[term] * doc_vec.get(term, 0.0) for term in q_vec)
            if score >= threshold:
                res_item = doc.copy()
                res_item["similarity_score"] = round(score, 4)
                results.append((score, res_item))

        results.sort(key=lambda x: x[0], reverse=True)
        return [item for _, item in results[:top_k]]

    def save(self) -> None:
        """Persiste el índice en disco en formato JSON."""
        if not self.storage_path:
            return
        data = {
            "documents": self.documents,
            "idf": self.idf
        }
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self.storage_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    def load(self) -> None:
        """Carga el índice desde disco."""
        if not self.storage_path or not self.storage_path.exists():
            return
        try:
            data = json.loads(self.storage_path.read_text(encoding="utf-8"))
            self.documents = data.get("documents", [])
            self.idf = data.get("idf", {})
        except Exception:
            pass
