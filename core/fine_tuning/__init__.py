"""
Módulo de Fine-Tuning Ligero y Post-Entrenamiento Local con Soup (soup-cli).
Permite a MMAE / JEV preparar datasets a partir de sus episodios exitosos y
ejecutar fine-tuning local (LoRA / QLoRA 4-bit) con soporte para GPUs < 4GB VRAM y CPU.
"""
from .dataset_preparer import DatasetPreparer
from .soup_pipeline import SoupPipeline

__all__ = ["DatasetPreparer", "SoupPipeline"]
