"""
Herramienta de integración de Fine-Tuning Local con Soup para MMAE / JEV.
Permite preparar datasets desde la memoria del agente, perfilar hardware y lanzar
entrenamientos LoRA/QLoRA autónomos.
"""
from __future__ import annotations

import json
from typing import Any, Dict, Optional
from jev.tools.base import BaseTool
from core.fine_tuning.dataset_preparer import DatasetPreparer
from core.fine_tuning.soup_pipeline import SoupPipeline


class SoupFineTunerTool(BaseTool):
    """
    Herramienta para preparar datasets, perfilar recursos y ejecutar fine-tuning local con Soup.
    """

    def __init__(self):
        super().__init__()
        self.preparer = DatasetPreparer()
        self.pipeline = SoupPipeline()

    @property
    def name(self) -> str:
        return "soup_fine_tuner"

    @property
    def description(self) -> str:
        return (
            "Prepara datasets desde la memoria de MMAE, genera configuraciones soup.yaml "
            "optimizadas para <4GB VRAM (QLoRA 4-bit) y ejecuta entrenamientos o exportaciones a GGUF."
        )

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["prepare_dataset", "profile", "train", "export", "status"],
                    "description": "Acción a realizar: prepare_dataset, profile, train, export o status"
                },
                "base_model": {
                    "type": "string",
                    "description": "Modelo base de HuggingFace (ej: Qwen/Qwen2.5-Coder-1.5B-Instruct o meta-llama/Llama-3.2-1B-Instruct)",
                    "default": "Qwen/Qwen2.5-Coder-1.5B-Instruct"
                },
                "epochs": {
                    "type": "integer",
                    "description": "Número de épocas de entrenamiento",
                    "default": 3
                },
                "async_train": {
                    "type": "boolean",
                    "description": "Si es True, ejecuta el entrenamiento en segundo plano sin bloquear el agente",
                    "default": True
                },
                "export_format": {
                    "type": "string",
                    "enum": ["gguf", "bitnet", "onnx"],
                    "description": "Formato para exportar modelo final",
                    "default": "gguf"
                }
            },
            "required": ["action"]
        }

    def execute(self, **kwargs) -> str:
        action = kwargs.get("action", "").lower().strip()
        base_model = kwargs.get("base_model", "Qwen/Qwen2.5-Coder-1.5B-Instruct")
        epochs = int(kwargs.get("epochs", 3))
        async_train = bool(kwargs.get("async_train", True))
        export_format = kwargs.get("export_format", "gguf")

        if action == "status":
            available = self.pipeline.is_available()
            return json.dumps({
                "soup_cli_installed": available,
                "soup_binary": self.pipeline.soup_bin,
                "workspace_dir": str(self.pipeline.workspace_dir),
                "ready_for_training": available
            }, ensure_ascii=False, indent=2)

        elif action == "prepare_dataset":
            res = self.preparer.build_tool_calling_dataset(min_steps=1)
            return json.dumps(res, ensure_ascii=False, indent=2)

        elif action == "profile":
            data_res = self.preparer.build_tool_calling_dataset(min_steps=1)
            cfg_path = self.pipeline.generate_soup_config(
                dataset_path=data_res["dataset_path"],
                base_model=base_model,
                epochs=epochs
            )
            prof_res = self.pipeline.profile_hardware(cfg_path)
            return json.dumps(prof_res, ensure_ascii=False, indent=2)

        elif action == "train":
            data_res = self.preparer.build_tool_calling_dataset(min_steps=1)
            cfg_path = self.pipeline.generate_soup_config(
                dataset_path=data_res["dataset_path"],
                base_model=base_model,
                epochs=epochs
            )
            train_res = self.pipeline.run_training(
                config_path=cfg_path,
                wait=not async_train
            )
            return json.dumps(train_res, ensure_ascii=False, indent=2)

        elif action == "export":
            export_res = self.pipeline.export_model(export_format=export_format)
            return json.dumps(export_res, ensure_ascii=False, indent=2)

        return json.dumps({"status": "error", "message": f"Acción desconocida: {action}"})
