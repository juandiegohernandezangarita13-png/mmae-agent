"""
Motor de Auto-Ajuste Fino (Self-Finetuning Engine) integrado en Jeff (JEV / MMAE).
Permite al agente automatizar su propio entrenamiento ligero (SFT / LoRA) con Layer Streaming
utilizando soup-cli sobre la GPU local de 4 GB (NVIDIA RTX 3050).
"""
from __future__ import annotations

import os
import sys
import json
import time
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional

from jev.tools.base import BaseTool, ToolResult
from jev.config import default_config


class SelfFineTuneTool(BaseTool):
    """Herramienta de auto-entrenamiento ligero local con Soup y Layer Streaming."""
    name = "trigger_self_finetuning"
    description = (
        "Inicia el proceso de auto-entrenamiento ligero (LoRA con Layer Streaming de Soup) "
        "utilizando las tareas, memoria y episodios exitosos registrados por el agente. "
        "Apto para ejecutarse en la GPU local RTX 3050 de 4 GB sin agotar la VRAM. "
        "Acciones disponibles: 'prepare_dataset', 'advise', 'start_train', 'status'."
    )
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["prepare_dataset", "advise", "start_train", "status"],
                "description": "Acción a ejecutar: 'prepare_dataset' (extrae y filtra datos), 'advise' (auditoría pre-vuelo), 'start_train' (lanza entrenamiento en GPU), 'status' (revisa avance).",
                "default": "status"
            },
            "epochs": {
                "type": "integer",
                "description": "Número de épocas para el entrenamiento (por defecto 3).",
                "default": 3
            }
        },
        "required": ["action"]
    }

    _current_process: Optional[subprocess.Popen] = None

    def __init__(self, workspace_dir: Optional[Path] = None):
        self.base_dir = default_config.base_dir
        self.finetune_dir = self.base_dir / "data" / "finetune"
        self.finetune_dir.mkdir(parents=True, exist_ok=True)
        self.prep_script = self.base_dir / "scripts" / "prepare_dataset.py"
        self.config_path = self.finetune_dir / "soup.yaml"
        self.log_path = self.finetune_dir / "training.log"
        self.train_data_path = self.finetune_dir / "train.jsonl"

    def execute(self, action: str = "status", epochs: int = 3, **kwargs) -> ToolResult:
        py_exe = sys.executable

        # -------------------------------------------------------------
        # 1. Preparar dataset
        # -------------------------------------------------------------
        if action == "prepare_dataset":
            if not self.prep_script.exists():
                return ToolResult(success=False, output="", error=f"No se encontró el script {self.prep_script}.")

            proc = subprocess.run([py_exe, str(self.prep_script)], capture_output=True, text=True, encoding="utf-8")
            if proc.returncode == 0:
                return ToolResult(
                    success=True,
                    output=f"✓ Dataset curado y exportado con éxito:\n{proc.stdout}",
                    data={"stdout": proc.stdout}
                )
            else:
                return ToolResult(success=False, output="", error=f"Error preparando dataset: {proc.stderr}")

        # -------------------------------------------------------------
        # 2. Auditoría pre-vuelo con Soup Advise
        # -------------------------------------------------------------
        elif action == "advise":
            if not self.train_data_path.exists():
                # Extraer primero si no existe
                subprocess.run([py_exe, str(self.prep_script)], capture_output=True)

            cmd = [py_exe, "-m", "soup_cli", "advise", "run", str(self.train_data_path)]
            proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
            return ToolResult(
                success=True,
                output=f"📋 [SOUP ADVISE AUDIT REPORT]:\n{proc.stdout}",
                data={"advise": proc.stdout}
            )

        # -------------------------------------------------------------
        # 3. Iniciar entrenamiento con Soup (Layer Streaming en GPU)
        # -------------------------------------------------------------
        elif action == "start_train":
            # Verificar si ya hay un entrenamiento corriendo
            if SelfFineTuneTool._current_process and SelfFineTuneTool._current_process.poll() is None:
                return ToolResult(
                    success=True,
                    output=f"⚠️ Ya existe un entrenamiento en ejecución activa (PID: {SelfFineTuneTool._current_process.pid}). Usa action='status' para ver el progreso.",
                    data={"pid": SelfFineTuneTool._current_process.pid}
                )

            # Preparar dataset si no está listo
            if not self.train_data_path.exists():
                subprocess.run([py_exe, str(self.prep_script)], capture_output=True)

            # Actualizar épocas en soup.yaml si se especificaron
            if epochs != 3 and self.config_path.exists():
                try:
                    txt = self.config_path.read_text(encoding="utf-8")
                    import re
                    txt = re.sub(r"epochs:\s*\d+", f"epochs: {epochs}", txt)
                    self.config_path.write_text(txt, encoding="utf-8")
                except Exception:
                    pass

            cmd = [py_exe, "-m", "soup_cli", "train", "--config", str(self.config_path)]

            log_file = open(self.log_path, "w", encoding="utf-8", errors="replace")
            proc = subprocess.Popen(
                cmd,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                cwd=str(self.base_dir)
            )
            SelfFineTuneTool._current_process = proc

            return ToolResult(
                success=True,
                output=(
                    f"🚀 [ENTRENAMIENTO SOUP LOCAL INICIADO]\n"
                    f"• PID: {proc.pid}\n"
                    f"• GPU: NVIDIA RTX 3050 (Layer Streaming: activado, VRAM contenida en < 4 GB)\n"
                    f"• Archivo de configuración: {self.config_path.name}\n"
                    f"• Archivo de log en vivo: {self.log_path}\n"
                    f"El modelo base se mantendrá en RAM y procesará capa por capa en la GPU de forma continua."
                ),
                data={"pid": proc.pid, "log": str(self.log_path)}
            )

        # -------------------------------------------------------------
        # 4. Consultar estado del entrenamiento
        # -------------------------------------------------------------
        elif action == "status":
            is_running = SelfFineTuneTool._current_process is not None and SelfFineTuneTool._current_process.poll() is None
            tail_lines = ""
            if self.log_path.exists():
                try:
                    lines = self.log_path.read_text(encoding="utf-8", errors="replace").splitlines()
                    tail_lines = "\n".join(lines[-15:])
                except Exception:
                    pass

            status_str = f"EN EJECUCIÓN (PID: {SelfFineTuneTool._current_process.pid})" if is_running else "DETENIDO / INACTIVO"
            msg = (
                f"📊 [ESTADO DEL ENTRENAMIENTO LOCAL]:\n"
                f"• Proceso: {status_str}\n"
                f"• Dataset disponible: {'Sí' if self.train_data_path.exists() else 'No generado aún'}\n"
                f"• Últimas líneas de registro:\n{tail_lines or '(Sin logs recientes)'}"
            )
            return ToolResult(success=True, output=msg, data={"is_running": is_running, "tail": tail_lines})

        return ToolResult(success=False, output="", error=f"Acción '{action}' desconocida para trigger_self_finetuning.")
