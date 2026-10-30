"""
Hub de Conocimiento Heterogéneo y RAG Local (Inspirado en Coach).
Permite la ingesta estructurada, particionado (chunking) y consulta semántica/léxica
sobre múltiples fuentes de información: archivos locales (Markdown, PDF, TXT, JSON, CSV, código),
exportaciones estructuradas (tipo Notion) y fuentes web.
"""
import os
import re
import math
import json
import hashlib
import urllib.request
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional, Union
from dataclasses import dataclass, asdict


@dataclass
class DocumentChunk:
    doc_id: str
    source_type: str  # 'local_file', 'web_url', 'notion_doc', 'raw_text'
    source_path: str
    title: str
    chunk_index: int
    text: str
    checksum: str
    created_at: str
    metadata: Dict[str, Any]


class HeterogeneousKnowledgeHub:
    """
    Motor de ingesta y recuperación documental estilo Coach:
    - Ingesta de fuentes heterogéneas con extracción de texto limpia.
    - Chunking adaptativo por párrafos y oraciones con solapamiento (overlap).
    - Detección de cambios mediante hash SHA-256 (re-indexación incremental inteligente).
    - Búsqueda híbrida (TF-IDF + Coseno + Coincidencia de Palabras Clave) en Python puro.
    - Formateo de citas con procedencia exacta para el LLM.
    """

    def __init__(self, storage_dir: Optional[Path] = None, chunk_size: int = 600, chunk_overlap: int = 100):
        self.storage_dir = storage_dir or (Path("data/memory") / "knowledge_hub")
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.index_file = self.storage_dir / "knowledge_index.json"
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

        self.chunks: List[DocumentChunk] = []
        self.file_checksums: Dict[str, str] = {}
        self.vocabulary: Dict[str, int] = {}
        self.idf: Dict[str, float] = {}

        self.load()

    def _tokenize(self, text: str) -> List[str]:
        return re.findall(r"\b[a-zA-Z0-9_\-\.]{2,}\b", text.lower())

    def _calculate_checksum(self, text: str) -> str:
        return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()

    def _chunk_text(self, text: str) -> List[str]:
        """Divide el texto en fragmentos con solapamiento respetando párrafos y frases."""
        clean_text = text.replace("\r\n", "\n").strip()
        if not clean_text:
            return []

        if len(clean_text) <= self.chunk_size:
            return [clean_text]

        paragraphs = clean_text.split("\n\n")
        chunks = []
        current_chunk = []
        current_len = 0

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue

            if current_len + len(para) <= self.chunk_size:
                current_chunk.append(para)
                current_len += len(para) + 2
            else:
                if current_chunk:
                    chunks.append("\n\n".join(current_chunk))
                # Manejar párrafos gigantes particionándolos por frases
                if len(para) > self.chunk_size:
                    sentences = re.split(r"(?<=[.!?])\s+", para)
                    sub_chunk = []
                    sub_len = 0
                    for sent in sentences:
                        if sub_len + len(sent) <= self.chunk_size:
                            sub_chunk.append(sent)
                            sub_len += len(sent) + 1
                        else:
                            if sub_chunk:
                                chunks.append(" ".join(sub_chunk))
                            sub_chunk = [sent]
                            sub_len = len(sent)
                    if sub_chunk:
                        current_chunk = sub_chunk
                        current_len = sub_len
                else:
                    current_chunk = [para]
                    current_len = len(para)

        if current_chunk:
            chunks.append("\n\n".join(current_chunk))

        return chunks

    def ingest_text(
        self,
        text: str,
        title: str,
        source_type: str = "raw_text",
        source_path: str = "in_memory",
        metadata: Optional[Dict[str, Any]] = None
    ) -> int:
        """Ingesta una cadena de texto arbitraria y la indexa."""
        checksum = self._calculate_checksum(text)
        if self.file_checksums.get(source_path) == checksum:
            return 0  # Ya indexado sin cambios

        # Remover chunks previos de este documento si existían
        self.chunks = [c for c in self.chunks if c.source_path != source_path]

        raw_chunks = self._chunk_text(text)
        now_iso = datetime.now().isoformat()
        doc_id = hashlib.sha256(source_path.encode()).hexdigest()[:12]

        for idx, chunk_content in enumerate(raw_chunks):
            chunk = DocumentChunk(
                doc_id=doc_id,
                source_type=source_type,
                source_path=source_path,
                title=title,
                chunk_index=idx + 1,
                text=chunk_content,
                checksum=checksum,
                created_at=now_iso,
                metadata=metadata or {}
            )
            self.chunks.append(chunk)

        self.file_checksums[source_path] = checksum
        self._recompute_vectors()
        self.save()
        return len(raw_chunks)

    def ingest_file(self, file_path: Union[str, Path], category: str = "general") -> int:
        """
        Ingesta un archivo local.
        Soporta: .md, .txt, .json, .csv, .py, .html, .rst y extracción de texto de .pdf.
        """
        path = Path(file_path).resolve()
        if not path.exists() or not path.is_file():
            return 0

        suffix = path.suffix.lower()
        content = ""

        try:
            if suffix in (".md", ".txt", ".json", ".csv", ".py", ".html", ".rst", ".yaml", ".yml"):
                content = path.read_text(encoding="utf-8", errors="ignore")
            elif suffix == ".pdf":
                # Extracción robusta de PDF (intento con pypdf / fallback a lector binario de streams)
                content = self._extract_text_from_pdf(path)
            else:
                # Intento genérico de lectura textual
                content = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            return 0

        if not content.strip():
            return 0

        source_type = "notion_doc" if "notion" in path.name.lower() else "local_file"
        title = path.stem.replace("_", " ").title()

        return self.ingest_text(
            text=content,
            title=title,
            source_type=source_type,
            source_path=str(path),
            metadata={"filename": path.name, "category": category, "extension": suffix}
        )

    def _extract_text_from_pdf(self, path: Path) -> str:
        """Extrae texto de un PDF con fallback seguro."""
        try:
            import pypdf
            reader = pypdf.PdfReader(str(path))
            pages_text = [page.extract_text() or "" for page in reader.pages]
            return "\n\n".join(pages_text)
        except Exception:
            pass

        # Fallback de emergencia para streams de texto estándar en PDF
        try:
            raw_bytes = path.read_bytes()
            # Buscar bloques de texto entre paréntesis en operadores BT ... ET
            text_matches = re.findall(rb"\((.*?)\)\s*Tj", raw_bytes)
            decoded = [b.decode("utf-8", errors="ignore") for b in text_matches]
            return " ".join(decoded)
        except Exception:
            return ""

    def ingest_directory(
        self,
        directory: Union[str, Path],
        extensions: Optional[List[str]] = None,
        recursive: bool = True
    ) -> Dict[str, int]:
        """Ingesta recursivamente una carpeta de documentos locales."""
        dir_p = Path(directory).resolve()
        if not dir_p.exists() or not dir_p.is_dir():
            return {}

        valid_exts = set(extensions or [".md", ".txt", ".json", ".py", ".pdf", ".rst"])
        results = {}

        pattern = "**/*" if recursive else "*"
        for f in dir_p.glob(pattern):
            if f.is_file() and f.suffix.lower() in valid_exts:
                chunks_count = self.ingest_file(f)
                if chunks_count > 0:
                    results[str(f)] = chunks_count

        return results

    def ingest_url(self, url: str, title: Optional[str] = None) -> int:
        """Descarga e ingesta el contenido de una URL web externa."""
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "MMAE-Agent-Knowledge-Hub/1.0"}
            )
            with urllib.request.urlopen(req, timeout=10.0) as resp:
                raw_html = resp.read().decode("utf-8", errors="ignore")

            # Limpiar etiquetas HTML básicas
            clean_text = re.sub(r"<script.*?</script>", "", raw_html, flags=re.DOTALL | re.IGNORECASE)
            clean_text = re.sub(r"<style.*?</style>", "", clean_text, flags=re.DOTALL | re.IGNORECASE)
            clean_text = re.sub(r"<[^>]+>", " ", clean_text)
            clean_text = re.sub(r"\s+", " ", clean_text).strip()

            t = title or url
            return self.ingest_text(
                text=clean_text,
                title=t,
                source_type="web_url",
                source_path=url,
                metadata={"url": url}
            )
        except Exception:
            return 0

    def _recompute_vectors(self) -> None:
        """Calcula IDF y normalizaciones para búsqueda semántica vectorial ligera."""
        total_docs = len(self.chunks)
        if total_docs == 0:
            return

        df: Dict[str, int] = {}
        for chunk in self.chunks:
            tokens = set(self._tokenize(chunk.text))
            for t in tokens:
                df[t] = df.get(t, 0) + 1

        self.idf = {t: math.log((total_docs + 1) / (cnt + 1)) + 1.0 for t, cnt in df.items()}

    def _vectorize(self, text: str) -> Dict[str, float]:
        tokens = self._tokenize(text)
        if not tokens:
            return {}
        tf: Dict[str, float] = {}
        for t in tokens:
            tf[t] = tf.get(t, 0.0) + 1.0

        vec: Dict[str, float] = {}
        for t, freq in tf.items():
            if t in self.idf:
                vec[t] = (freq / len(tokens)) * self.idf[t]

        norm = math.sqrt(sum(v * v for v in vec.values()))
        if norm > 0:
            vec = {k: v / norm for k, v in vec.items()}
        return vec

    def query(self, query_text: str, top_k: int = 3, threshold: float = 0.05) -> List[Dict[str, Any]]:
        """Búsqueda semántica + coincidencia léxica sobre todos los chunks indexados."""
        if not self.chunks:
            return []

        q_vec = self._vectorize(query_text)
        q_tokens = set(self._tokenize(query_text))
        scored: List[Tuple[float, DocumentChunk]] = []

        for chunk in self.chunks:
            c_vec = self._vectorize(chunk.text)
            # Coseno entre vectores normalizados
            sim = sum(q_vec[t] * c_vec.get(t, 0.0) for t in q_vec)

            # Bonus por coincidencia exacta de tokens clave
            c_tokens = set(self._tokenize(chunk.text))
            token_overlap = len(q_tokens.intersection(c_tokens)) / max(len(q_tokens), 1)
            total_score = (sim * 0.7) + (token_overlap * 0.3)

            if total_score >= threshold:
                scored.append((total_score, chunk))

        scored.sort(key=lambda x: x[0], reverse=True)
        results = []
        for score, chunk in scored[:top_k]:
            item = asdict(chunk)
            item["score"] = round(score, 4)
            results.append(item)
        return results

    def format_retrieval_context(self, query_text: str, top_k: int = 3) -> str:
        """Genera el bloque de citas documentales formateado para el agente."""
        matches = self.query(query_text, top_k=top_k)
        if not matches:
            return ""

        lines = ["[FUENTES DE CONOCIMIENTO DOCUMENTAL Y RAG LOCAL (Coach Hub)]:"]
        for m in matches:
            lines.append(
                f"- [Fuente: {m['source_path']} | Chunk #{m['chunk_index']} | Relevancia: {m['score']:.2f}]\n"
                f"  \"{m['text'][:350]}...\""
            )
        return "\n".join(lines)

    def save(self) -> None:
        data = {
            "checksums": self.file_checksums,
            "chunks": [asdict(c) for c in self.chunks]
        }
        self.index_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def load(self) -> None:
        if not self.index_file.exists():
            return
        try:
            data = json.loads(self.index_file.read_text(encoding="utf-8"))
            self.file_checksums = data.get("checksums", {})
            self.chunks = [DocumentChunk(**c) for c in data.get("chunks", [])]
            self._recompute_vectors()
        except Exception:
            pass
