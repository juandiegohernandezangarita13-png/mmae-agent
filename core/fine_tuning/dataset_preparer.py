"""
Preparador de datasets de entrenamiento a partir de la memoria episódica de MMAE.
Convierte experiencias exitosas, acciones de herramientas y lecciones aprendidas
en formato JSONL estructurado (ShareGPT / Tool-Calling) compatible con Soup.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("jev.fine_tuning.preparer")


class DatasetPreparer:
    """
    Extrae, valida y formatea episodios de la memoria local para entrenamiento LoRA/QLoRA.
    """

    DEFAULT_SYSTEM_PROMPT = (
        "Eres MMAE / JEV, un agente autónomo de ingeniería de software y automatización "
        "de sistemas en Windows. Razonas paso a paso, planificas con DAG y ejecutas "
        "herramientas de forma segura y precisa sin bucles innecesarios."
    )

    def __init__(self, memory_dir: Optional[Path] = None):
        self.base_dir = Path(__file__).resolve().parent.parent.parent
        self.memory_dir = memory_dir or (self.base_dir / "data" / "memory")
        self.episodes_file = self.memory_dir / "episodes.jsonl"
        self.lessons_file = self.memory_dir / "lessons_learned.json"
        self.output_dir = self.base_dir / "data" / "fine_tuning"
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def extract_successful_episodes(self, min_steps: int = 1) -> List[Dict[str, Any]]:
        """Recupera únicamente episodios con éxito confirmado."""
        if not self.episodes_file.exists():
            logger.warning(f"Archivo de episodios no encontrado: {self.episodes_file}")
            return []

        successful = []
        try:
            with open(self.episodes_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        record = json.loads(line)
                        if record.get("success") is True and record.get("steps_count", 0) >= min_steps:
                            successful.append(record)
                    except json.JSONDecodeError:
                        continue
        except Exception as e:
            logger.error(f"Error leyendo episodios: {e}")

        return successful

    def build_tool_calling_dataset(
        self,
        output_filename: str = "train_tool_calling.jsonl",
        min_steps: int = 1,
        include_synthetic_bootstrap: bool = True
    ) -> Dict[str, Any]:
        """
        Genera el dataset en formato Tool-Calling compatible con `soup-cli`.
        """
        episodes = self.extract_successful_episodes(min_steps=min_steps)
        out_path = self.output_dir / output_filename
        samples: List[Dict[str, Any]] = []

        # 1. Muestras reales desde la memoria episódica
        for ep in episodes:
            task = ep.get("task", "").strip()
            summary = ep.get("summary", "").strip()
            tools_used = ep.get("tools_used", [])

            if not task:
                continue

            tool_calls = []
            for tool_name in tools_used:
                tool_calls.append({
                    "function": {
                        "name": tool_name,
                        "arguments": json.dumps({"action": "execute", "task": task})
                    }
                })

            sample = {
                "messages": [
                    {"role": "system", "content": self.DEFAULT_SYSTEM_PROMPT},
                    {"role": "user", "content": task},
                    {
                        "role": "assistant",
                        "content": summary or f"Completando tarea con herramientas: {', '.join(tools_used)}",
                        "tool_calls": tool_calls if tool_calls else None
                    }
                ]
            }
            # Limpiar campos nulos
            if not sample["messages"][2]["tool_calls"]:
                del sample["messages"][2]["tool_calls"]

            samples.append(sample)

        # 2. Si hay pocos episodios reales, añadir muestras bootstrap de alta calidad
        if include_synthetic_bootstrap and len(samples) < 50:
            bootstrap_samples = self._generate_bootstrap_samples()
            samples.extend(bootstrap_samples)

        # 3. Guardar en JSONL
        with open(out_path, "w", encoding="utf-8") as f:
            for s in samples:
                f.write(json.dumps(s, ensure_ascii=False) + "\n")

        return {
            "status": "success",
            "dataset_path": str(out_path),
            "total_samples": len(samples),
            "real_episodes": len(episodes),
            "bootstrap_samples": len(samples) - len(episodes)
        }

    def _generate_bootstrap_samples(self) -> List[Dict[str, Any]]:
        """Muestras curadas de alto valor para garantizar formato de entrenamiento."""
        curated = [
            {
                "task": "Crea un nuevo repositorio en GitHub llamado mmae-dashboard en modo privado",
                "tool": "create_github_repo",
                "args": {"name": "mmae-dashboard", "private": True, "description": "Dashboard local para MMAE"},
                "response": "Repositorio 'mmae-dashboard' creado exitosamente y vinculado como remote origin."
            },
            {
                "task": "Ejecuta un diagnóstico de memoria RAM y almacenamiento en Windows",
                "tool": "cli_execute_structured",
                "args": {"command": "powershell -Command \"Get-CimInstance Win32_OperatingSystem | Select-Object TotalVisibleMemorySize,FreePhysicalMemory\""},
                "response": "Diagnóstico de hardware completado: memoria y discos dentro de parámetros normales."
            },
            {
                "task": "Lee el archivo config.py y extrae la lista de modelos configurados",
                "tool": "read_file",
                "args": {"path": "config.py"},
                "response": "Modelos identificados en config.py: gemini-flash-lite-latest, gemini-2.5-flash y gemini-3.1-flash-lite."
            },
            {
                "task": "Captura la pantalla actual para inspeccionar la interfaz de la terminal",
                "tool": "skill_screenshot",
                "args": {},
                "response": "Captura de pantalla almacenada correctamente en data/screenshots/."
            },
            {
                "task": "Busca una habilidad para interactuar con Docker y contenedores",
                "tool": "find_skill",
                "args": {"query": "docker containers orchestrator", "category": "devops"},
                "response": "Habilidad encontrada: devops/docker-cli con directivas para despliegue de contenedores aislados."
            }
        ]

        result = []
        for c in curated:
            result.append({
                "messages": [
                    {"role": "system", "content": self.DEFAULT_SYSTEM_PROMPT},
                    {"role": "user", "content": c["task"]},
                    {
                        "role": "assistant",
                        "content": c["response"],
                        "tool_calls": [
                            {
                                "function": {
                                    "name": c["tool"],
                                    "arguments": json.dumps(c["args"])
                                }
                            }
                        ]
                    }
                ]
            })
        return result
