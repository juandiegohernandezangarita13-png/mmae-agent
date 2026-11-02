"""
Pipeline de Fine-Tuning y Post-Entrenamiento Local con Soup (soup-cli).
Optimizado para hardware de bajos recursos (hasta 4GB VRAM o CPU).
Automatiza la generación de soup.yaml, perfilado de memoria, ejecución de entrenamiento y exportación a GGUF/BitNet.
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("jev.fine_tuning.soup")


class SoupPipeline:
    """
    Controlador y orquestador local para soup-cli.
    """

    def __init__(self, workspace_dir: Optional[Path] = None):
        self.base_dir = Path(__file__).resolve().parent.parent.parent
        self.workspace_dir = workspace_dir or (self.base_dir / "data" / "fine_tuning")
        self.workspace_dir.mkdir(parents=True, exist_ok=True)
        self.output_dir = self.workspace_dir / "output"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.soup_bin = self._resolve_soup_binary()

    def _resolve_soup_binary(self) -> str:
        """Encuentra la ruta al ejecutable de soup.exe."""
        which_path = shutil.which("soup")
        if which_path:
            return which_path

        # Buscar en Scripts de Python uv
        py_scripts = Path(sys.executable).parent / "Scripts" / "soup.exe"
        if py_scripts.exists():
            return str(py_scripts)

        # Ruta fija estándar en Windows
        fixed_path = Path(r"C:\Users\juand\AppData\Roaming\uv\python\cpython-3.11.16-windows-x86_64-none\Scripts\soup.exe")
        if fixed_path.exists():
            return str(fixed_path)

        return "soup"

    def is_available(self) -> bool:
        """Verifica si soup-cli está disponible en el entorno."""
        try:
            res = subprocess.run(
                [self.soup_bin, "--version"],
                capture_output=True,
                text=True,
                timeout=5
            )
            return res.returncode == 0
        except Exception:
            return False

    def generate_soup_config(
        self,
        dataset_path: str,
        base_model: str = "Qwen/Qwen2.5-Coder-1.5B-Instruct",
        output_config_path: Optional[str] = None,
        epochs: int = 3,
        learning_rate: float = 2e-4,
        max_length: int = 2048,
        use_4bit_quant: bool = True
    ) -> str:
        """
        Genera un archivo soup.yaml hermético y optimizado para hardware de consumo (<4GB VRAM).
        """
        config_path = Path(output_config_path) if output_config_path else (self.workspace_dir / "soup.yaml")
        dataset_rel = str(Path(dataset_path).resolve()).replace("\\", "/")
        out_rel = str(self.output_dir.resolve()).replace("\\", "/")

        yaml_content = f"""# Configuración de Fine-Tuning MMAE / JEV vía Soup-CLI
base: {base_model}
task: sft

data:
  train: "{dataset_rel}"
  format: tool-calling
  val_split: 0.1
  max_length: {max_length}

training:
  epochs: {epochs}
  lr: {learning_rate}
  batch_size: auto
  gradient_accumulation_steps: 4
  lora:
    r: 16
    alpha: 32
    target_modules: auto
  quantization: {"4bit" if use_4bit_quant else "none"}

output: "{out_rel}"
"""
        with open(config_path, "w", encoding="utf-8") as f:
            f.write(yaml_content)

        logger.info(f"soup.yaml generado en: {config_path}")
        return str(config_path)

    def profile_hardware(self, config_path: str) -> Dict[str, Any]:
        """
        Ejecuta `soup profile` para estimar memoria y compatibilidad VRAM antes de entrenar.
        """
        if not self.is_available():
            return {"status": "error", "message": "soup-cli no está instalado o no se encuentra en PATH."}

        try:
            res = subprocess.run(
                [self.soup_bin, "profile", "--config", str(config_path)],
                capture_output=True,
                text=True,
                timeout=30
            )
            return {
                "status": "success" if res.returncode == 0 else "warning",
                "stdout": res.stdout,
                "stderr": res.stderr,
                "exit_code": res.returncode
            }
        except Exception as e:
            return {"status": "error", "message": f"Error ejecutando perfilado: {str(e)}"}

    def run_training(
        self,
        config_path: str,
        wait: bool = True,
        timeout_seconds: int = 3600
    ) -> Dict[str, Any]:
        """
        Inicia el entrenamiento con `soup train --config <config_path>`.
        """
        if not self.is_available():
            return {"status": "error", "message": "soup-cli no está instalado."}

        cmd = [self.soup_bin, "train", "--config", str(config_path)]
        logger.info(f"Iniciando entrenamiento Soup: {' '.join(cmd)}")

        if not wait:
            # Ejecución en segundo plano sin bloquear el agente
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            return {
                "status": "started_async",
                "pid": proc.pid,
                "config": str(config_path),
                "message": f"Entrenamiento iniciado en segundo plano con PID {proc.pid}."
            }

        try:
            res = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout_seconds
            )
            return {
                "status": "success" if res.returncode == 0 else "failed",
                "exit_code": res.returncode,
                "output": res.stdout[-2000:] if res.stdout else "",
                "error": res.stderr[-2000:] if res.stderr else "",
                "output_dir": str(self.output_dir)
            }
        except subprocess.TimeoutExpired:
            return {"status": "timeout", "message": f"Entrenamiento superó el límite de {timeout_seconds}s."}
        except Exception as e:
            return {"status": "error", "message": f"Fallo al ejecutar soup train: {str(e)}"}

    def export_model(
        self,
        export_format: str = "gguf",
        quantization: str = "q4_k_m"
    ) -> Dict[str, Any]:
        """
        Exporta el modelo entrenado a formato ligero (GGUF, BitNet, ONNX).
        """
        if not self.is_available():
            return {"status": "error", "message": "soup-cli no está disponible."}

        export_dir = self.workspace_dir / "exports"
        export_dir.mkdir(parents=True, exist_ok=True)

        cmd = [
            self.soup_bin,
            "export",
            "--model", str(self.output_dir),
            "--format", export_format,
            "--quantization", quantization,
            "--output", str(export_dir)
        ]

        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            return {
                "status": "success" if res.returncode == 0 else "failed",
                "exit_code": res.returncode,
                "export_dir": str(export_dir),
                "stdout": res.stdout,
                "stderr": res.stderr
            }
        except Exception as e:
            return {"status": "error", "message": f"Error exportando modelo: {str(e)}"}
