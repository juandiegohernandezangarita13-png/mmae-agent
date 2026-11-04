"""
Biblioteca de Experiencia Persistente R por Dominios.
Inspirado en Harness² (Google Research, 2026: arXiv:2610.14224).

Estructura en disco:
    data/library/<domain>/INDEX.md
    data/library/<domain>/harnesses/<task_id>/harness/   (árbol completo de componentes c1..c8)
    data/library/<domain>/harnesses/<task_id>/EXPERIENCE.md (tupla transferible: cue, lesson, evidence)

Cada entrada representa una tarea real superada exitosamente en este dominio.
Permite retrieval estructurado de lecciones transferibles previas para acelerar
la resolución de nuevas misiones en el mismo dominio.
"""
from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from config import BASE_DIR
from core.harness.tree import HarnessTree
from utils.logger import log

DEFAULT_LIBRARY_ROOT = BASE_DIR / "data" / "library"


def slugify(text: str) -> str:
    """Convierte texto en un identificador seguro para carpetas."""
    text = re.sub(r"[^\w\s-]", "", text.strip()).strip()
    return re.sub(r"[-\s]+", "_", text).lower() or "general"


def has_valid_experience(experience: Optional[Dict[str, Any]]) -> bool:
    """Verifica que la experiencia contenga la tríada estricta (cue, lesson, evidence)."""
    if not isinstance(experience, dict):
        return False
    return all(
        isinstance(experience.get(k), str) and experience[k].strip()
        for k in ("cue", "lesson", "evidence")
    )


def assert_no_rubric_leak(text_or_dict: Any) -> None:
    """Salvaguarda Answer-Free: previene la infiltración de rúbricas o falsas auto-evaluaciones."""
    forbidden = ["grader expects", "the rubric", "answer key", "criterio de corrección"]
    raw = json.dumps(text_or_dict, ensure_ascii=False).lower() if isinstance(text_or_dict, (dict, list)) else str(text_or_dict).lower()
    for phrase in forbidden:
        if phrase in raw:
            raise ValueError(f"Violación de salvaguarda Answer-Free: detección de frase prohibida '{phrase}'")


@dataclass
class ExperienceEntry:
    task_id: str
    domain: str
    cue: str
    lesson: str
    evidence: str
    confidence: float
    adopted_label: str = ""
    why: str = ""


class ExperienceLibrary:
    """
    Gestor de la Biblioteca de Experiencia por dominio.
    Mantiene la memoria procedimental de nivel metacognitivo.
    """

    def __init__(self, domain: str = "general", root: Optional[Path] = None) -> None:
        self.domain = slugify(domain)
        self.root = Path(root) if root else DEFAULT_LIBRARY_ROOT
        self.dir = self.root / self.domain
        self.harnesses_dir = self.dir / "harnesses"
        self.index_file = self.dir / "INDEX.md"

        self.dir.mkdir(parents=True, exist_ok=True)
        self.harnesses_dir.mkdir(parents=True, exist_ok=True)

        if not self.index_file.exists():
            self.rebuild_index()

    def entry_dir(self, task_id: str) -> Path:
        return self.harnesses_dir / slugify(task_id)

    def entries(self) -> List[str]:
        if not self.harnesses_dir.is_dir():
            return []
        return sorted(p.name for p in self.harnesses_dir.iterdir() if p.is_dir())

    def get_tree(self, task_id: str) -> Optional[HarnessTree]:
        target = self.entry_dir(task_id) / "harness"
        if not target.is_dir():
            return None
        return HarnessTree.read_from_dir(target)

    def get_experience(self, task_id: str) -> Optional[ExperienceEntry]:
        exp_file = self.entry_dir(task_id) / "EXPERIENCE.md"
        if not exp_file.is_file():
            return None

        content = exp_file.read_text(encoding="utf-8")
        cue = self._extract_field(content, "cue")
        lesson = self._extract_field(content, "lesson")
        evidence = self._extract_field(content, "evidence")
        conf_str = self._extract_field(content, "confidence")
        conf = float(conf_str) if conf_str else 0.85

        return ExperienceEntry(
            task_id=task_id,
            domain=self.domain,
            cue=cue,
            lesson=lesson,
            evidence=evidence,
            confidence=conf,
        )

    def add(
        self,
        task_id: str,
        harness: HarnessTree,
        experience: Dict[str, Any],
        why: str = "",
        label: str = "harness_v1",
        run_id: str = "",
    ) -> Path:
        """
        Almacena una experiencia con su árbol de componentes completo c1..c8
        y regenera INDEX.md.
        """
        assert_no_rubric_leak(why)
        assert_no_rubric_leak(experience)

        target = self.entry_dir(task_id)
        if target.exists():
            shutil.rmtree(target, ignore_errors=True)

        harness_path = target / "harness"
        harness_path.mkdir(parents=True, exist_ok=True)
        harness.write_to_dir(harness_path)

        cue = str(experience.get("cue", "")).strip()
        lesson = str(experience.get("lesson", "")).strip()
        evidence = str(experience.get("evidence", "")).strip()
        confidence = float(experience.get("confidence", 0.9))

        lines = [
            f"# Tarea: {task_id}",
            "",
            f"- **Dominio**: `{self.domain}`",
            f"- **Harness Adoptado**: `{label}`" + (f" (run: `{run_id}`)" if run_id else ""),
            f"- **Componentes**: {harness.inventory()}",
            "",
            "## Transferable lesson",
            f"- **cue**: {cue}",
            f"- **lesson**: {lesson}",
            f"- **evidence**: {evidence}",
            f"- **confidence**: {confidence:.2f}",
            "",
        ]
        if why.strip():
            lines += ["## Justificación de Adopción", why.strip(), ""]

        (target / "EXPERIENCE.md").write_text("\n".join(lines), encoding="utf-8")
        self.rebuild_index()
        log.info(f"📚 [ExperienceLibrary]: Guardada experiencia para tarea '{task_id}' en dominio '{self.domain}'.")
        return target

    def rebuild_index(self) -> Path:
        """Regenera INDEX.md a partir del estado físico en disco."""
        rows = [
            f"# Biblioteca de Experiencia — Dominio: `{self.domain}`",
            "",
            "Catálogo formal de harnesses adoptados y lecciones transferibles demostradas mediante",
            "evidencia física determinista (código de salida, archivos verificados, logs).",
            "",
        ]
        entries = self.entries()
        if not entries:
            rows.append("_(Dominio vacío — aún no se han registrado experiencias para este dominio)_")
        else:
            for name in entries:
                ed = self.harnesses_dir / name
                exp = self.get_experience(name)
                tree = self.get_tree(name)
                inv = tree.inventory() if tree else "árbol no disponible"

                rows += [
                    f"### `harnesses/{name}/`",
                    f"- **Componentes**: `{inv}`",
                ]
                if exp and exp.cue:
                    rows.append(f"- **Cue (Detonante)**: {exp.cue}")
                if exp and exp.lesson:
                    rows.append(f"- **Lección**: {exp.lesson}")
                if exp and exp.confidence:
                    rows.append(f"- **Confianza**: {exp.confidence:.2f}")
                rows.append("")

        self.index_file.write_text("\n".join(rows), encoding="utf-8")
        return self.index_file

    def find_relevant(self, query_text: str, top_k: int = 3) -> List[ExperienceEntry]:
        """
        Recupera lecciones transferibles basadas en coincidencia de términos clave del detonante (cue).
        """
        tokens = set(re.findall(r"\w+", query_text.lower()))
        if not tokens:
            return []

        scored: List[Tuple[float, ExperienceEntry]] = []
        for name in self.entries():
            exp = self.get_experience(name)
            if not exp or not exp.cue:
                continue

            cue_tokens = set(re.findall(r"\w+", exp.cue.lower()))
            overlap = tokens.intersection(cue_tokens)
            if overlap:
                # Puntuación basada en cobertura de términos y nivel de confianza
                score = (len(overlap) / max(1, len(cue_tokens))) * exp.confidence
                scored.append((score, exp))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [entry for _, entry in scored[:top_k]]

    def export_prompt_injection(self, query_text: str, top_k: int = 3) -> str:
        """
        Genera un bloque formateado en Markdown para inyectar en el contexto del LLM.
        """
        relevant = self.find_relevant(query_text, top_k=top_k)
        if not relevant:
            return ""

        lines = [
            "### [Biblioteca de Experiencias Previas - Dominio: " + self.domain.upper() + "]",
            "Las siguientes lecciones fueron validadas físicamente en tareas previas similares:",
        ]
        for i, exp in enumerate(relevant, 1):
            lines.append(f"{i}. **Cuando detectes (Cue)**: {exp.cue}")
            lines.append(f"   - **Lección Aplicable**: {exp.lesson}")
            lines.append(f"   - **Evidencia Previa**: {exp.evidence}")
            lines.append(f"   - **Confianza**: {exp.confidence:.2f}")

        lines.append("Aplica estas directivas para evitar errores ya superados.\n")
        return "\n".join(lines)

    @staticmethod
    def _extract_field(content: str, name: str) -> str:
        pattern = rf"-\s+\*\*{re.escape(name)}\*\*:\s*(.+)$"
        match = re.search(pattern, content, re.MULTILINE)
        return match.group(1).strip() if match else ""
