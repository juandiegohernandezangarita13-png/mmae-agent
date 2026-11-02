"""
Extractor y Curador Automático de Datasets para Fine-Tuning de Jeff (JEV / MMAE).
Procesa:
  1. data/memory/episodes.jsonl (385+ tareas y respuestas reales verificadas)
  2. data/memory/knowledge_base.db (soluciones procedimentales y llamadas a herramientas)
  3. data/memory/learned_lessons.json (reglas aprendidas y directivas de ingeniería)

Genera:
  - data/finetune/train.jsonl
  - data/finetune/val.jsonl
en formato Alpaca/ShareGPT estándar compatible con soup-cli.
"""
from __future__ import annotations

import os
import sys
import json
import sqlite3
from pathlib import Path
from typing import List, Dict, Any

# Reconfigurar stdout a UTF-8 para consola de Windows
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

BASE_DIR = Path(__file__).resolve().parent.parent
MEMORY_DIR = BASE_DIR / "data" / "memory"
OUTPUT_DIR = BASE_DIR / "data" / "finetune"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

SYSTEM_PROMPT = (
    "Eres Jeff (JEV), una IA autónoma local en Windows de nivel sénior. "
    "Operas directamente en la máquina del usuario mediante control visual de escritorio, "
    "diseño 3D CAD paramétrico con OpenSCAD, desarrollo full-stack, automatización de software "
    "y ejecución de herramientas estructuradas. Tu comunicación es siempre 100% en español impecable, "
    "entregando soluciones de código completas listas para producción."
)


def extract_from_episodes() -> List[Dict[str, Any]]:
    """Extrae ejemplos de entrenamiento de los episodios exitosos registrados."""
    episodes_file = MEMORY_DIR / "episodes.jsonl"
    if not episodes_file.exists():
        return []

    samples = []
    with open(episodes_file, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                ep = json.loads(line)
                task = (ep.get("task") or "").strip()
                summary = (ep.get("summary") or "").strip()
                success = ep.get("success", False)

                # Filtrar solo casos exitosos con respuestas ricas y bien estructuradas
                if success and task and summary and len(summary) >= 30:
                    tools = ep.get("tools_used", [])
                    tools_ctx = f"Herramientas ejecutadas en el entorno: {', '.join(tools)}" if tools else ""

                    samples.append({
                        "instruction": task,
                        "input": tools_ctx,
                        "output": summary,
                        "system": SYSTEM_PROMPT
                    })
            except Exception:
                continue
    return samples


def extract_from_procedural_solutions() -> List[Dict[str, Any]]:
    """Extrae pares instrucción-código de la base de datos procedimental SQLite."""
    db_file = MEMORY_DIR / "knowledge_base.db"
    if not db_file.exists():
        return []

    samples = []
    try:
        with sqlite3.connect(db_file) as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT category, trigger_keywords, problem_description, solution_summary, working_snippet
                FROM procedural_solutions
            """)
            rows = cur.fetchall()
            for cat, kw, prob, summary, snippet in rows:
                if not prob or not summary:
                    continue

                user_prompt = f"¿Cómo resolver la siguiente necesidad en Windows?: {prob}"
                if kw:
                    user_prompt += f"\nContexto / Palabras clave: {kw}"

                output_text = f"{summary.strip()}\n\n"
                if snippet and len(snippet.strip()) > 10:
                    output_text += f"```python\n{snippet.strip()}\n```"

                samples.append({
                    "instruction": user_prompt,
                    "input": f"Categoría de ingeniería: {cat or 'general'}",
                    "output": output_text,
                    "system": SYSTEM_PROMPT
                })
    except Exception as e:
        print(f"[prepare_dataset] Advertencia leyendo SQLite: {e}")

    return samples


def extract_from_learned_lessons() -> List[Dict[str, Any]]:
    """Extrae reglas y directivas aprendidas de learned_lessons.json."""
    lessons_file = MEMORY_DIR / "learned_lessons.json"
    if not lessons_file.exists():
        return []

    samples = []
    try:
        with open(lessons_file, "r", encoding="utf-8", errors="replace") as f:
            lessons = json.load(f)
            if isinstance(lessons, list):
                for item in lessons:
                    cat = item.get("category", "General")
                    rule = item.get("rule", "")
                    context = item.get("context", "")
                    if rule:
                        samples.append({
                            "instruction": f"¿Cuáles son las directivas y reglas maestras para '{cat}'?",
                            "input": f"Contexto operativo: {context}",
                            "output": f"Directiva obligatoria para {cat}:\n\n{rule}",
                            "system": SYSTEM_PROMPT
                        })
    except Exception:
        pass
    return samples


def curate_and_export():
    print("=" * 60)
    print("🚀 [JEFF DATASET BUILDER]: Extrayendo trayectorias y memoria...")
    print("=" * 60)

    episodes_samples = extract_from_episodes()
    print(f"• Muestras de episodios reales (episodes.jsonl): {len(episodes_samples)}")

    procedural_samples = extract_from_procedural_solutions()
    print(f"• Muestras procedimentales (knowledge_base.db): {len(procedural_samples)}")

    lessons_samples = extract_from_learned_lessons()
    print(f"• Muestras de lecciones aprendidas (learned_lessons.json): {len(lessons_samples)}")

    all_samples = episodes_samples + procedural_samples + lessons_samples

    # Deduplicación por combinación (instruction + output)
    unique_samples = []
    seen = set()
    for s in all_samples:
        key = (s["instruction"].strip().lower(), s["output"][:100].strip().lower())
        if key not in seen:
            seen.add(key)
            unique_samples.append(s)

    total = len(unique_samples)
    print(f"✓ Total muestras únicas y curadas: {total}")

    if total == 0:
        print("⚠️ No se encontraron muestras válidas en la memoria. Abortando.")
        return

    # Partición 90% entrenamiento, 10% validación
    val_count = max(1, int(total * 0.10))
    train_count = total - val_count

    train_data = unique_samples[:train_count]
    val_data = unique_samples[train_count:]

    train_path = OUTPUT_DIR / "train.jsonl"
    val_path = OUTPUT_DIR / "val.jsonl"

    with open(train_path, "w", encoding="utf-8") as f:
        for entry in train_data:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    with open(val_path, "w", encoding="utf-8") as f:
        for entry in val_data:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    print(f"\n📂 Archivos exportados listos para soup-cli:")
    print(f"   -> {train_path} ({len(train_data)} registros)")
    print(f"   -> {val_path} ({len(val_data)} registros)")
    print("=" * 60)


if __name__ == "__main__":
    curate_and_export()
