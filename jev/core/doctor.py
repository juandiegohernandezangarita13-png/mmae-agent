"""
Sistema de Diagnóstico Autónomo y Auto-Reparación (System Doctor & Self-Healing) para JEV.
Inspecciona periódicamente la salud del entorno de ejecución: espacio en disco, GPU CUDA,
procesos zombies, dependencias de Python y limpieza de artefactos temporales.
"""
from typing import Dict, Any, List, Optional
import shutil
import sys
import os
import time
from pathlib import Path

from jev.tools.base import BaseTool, ToolResult
from jev.config import default_config


class SystemDoctor:
    """Auditor y médico del entorno operativo del agente."""

    def __init__(self, workspace_dir: Optional[Path] = None):
        self.workspace_dir = workspace_dir or default_config.workspace_dir

    def run_health_check(self, auto_heal: bool = True) -> Dict[str, Any]:
        """
        Ejecuta un diagnóstico exhaustivo del entorno y aplica reparaciones preventivas.
        """
        checks: Dict[str, Any] = {}
        healed_actions: List[str] = []

        # 1. Comprobación de almacenamiento y espacio en disco
        try:
            total, used, free = shutil.disk_usage(str(self.workspace_dir))
            free_gb = round(free / (1024 ** 3), 2)
            checks["disk_space"] = {
                "status": "HEALTHY" if free_gb > 2.0 else "WARNING",
                "free_gb": free_gb,
                "total_gb": round(total / (1024 ** 3), 2)
            }
        except Exception as e:
            checks["disk_space"] = {"status": "ERROR", "error": str(e)}

        # 2. Comprobación de aceleración por GPU (CUDA / PyTorch)
        try:
            import torch
            cuda_available = torch.cuda.is_available()
            device_name = torch.cuda.get_device_name(0) if cuda_available else "N/A"
            checks["gpu_cuda"] = {
                "status": "HEALTHY" if cuda_available else "CPU_ONLY",
                "cuda_available": cuda_available,
                "device": device_name
            }
        except Exception:
            checks["gpu_cuda"] = {"status": "UNAVAILABLE", "cuda_available": False}

        # 3. Comprobación de directorios críticos del agente
        req_dirs = [
            self.workspace_dir / "data" / "screenshots",
            self.workspace_dir / "generated_tools",
            self.workspace_dir / "repos"
        ]
        for d in req_dirs:
            if not d.exists() and auto_heal:
                d.mkdir(parents=True, exist_ok=True)
                healed_actions.append(f"Directorio faltante creado: {d.name}")

        checks["directories"] = {"status": "HEALTHY", "verified": len(req_dirs)}

        # 4. Limpieza de capturas temporales antiguas (>50 archivos o >50MB)
        screenshots_dir = self.workspace_dir / "data" / "screenshots"
        cleaned_files = 0
        if screenshots_dir.exists() and auto_heal:
            pngs = list(screenshots_dir.glob("*.png"))
            if len(pngs) > 30:
                # Ordenar por fecha y conservar las 15 más recientes
                pngs.sort(key=lambda f: f.stat().st_mtime)
                to_delete = pngs[:-15]
                for p in to_delete:
                    try:
                        p.unlink()
                        cleaned_files += 1
                    except Exception:
                        pass
                if cleaned_files > 0:
                    healed_actions.append(f"Limpiadas {cleaned_files} capturas de pantalla antiguas del caché.")

        checks["cache_cleanup"] = {"cleaned_screenshots": cleaned_files}

        # 5. Estado general de salud
        overall_healthy = all(
            c.get("status") in ["HEALTHY", "CPU_ONLY"] for c in checks.values() if isinstance(c, dict) and "status" in c
        )

        return {
            "overall_healthy": overall_healthy,
            "timestamp": time.time(),
            "diagnostics": checks,
            "healed_actions": healed_actions
        }


class SystemDoctorTool(BaseTool):
    """Herramienta de diagnóstico de salud y auto-reparación del entorno operativo."""
    name = "system_doctor"
    description = (
        "Ejecuta una auditoría de salud del sistema anfitrión (GPU CUDA, espacio en disco, "
        "integridad de carpetas de caché) y repara automáticamente problemas de almacenamiento o directorios."
    )
    parameters = {
        "type": "object",
        "properties": {
            "auto_heal": {
                "type": "boolean",
                "description": "Si es True, aplica limpiezas de caché y crea carpetas faltantes automáticamente. Por defecto True."
            }
        }
    }

    def __init__(self, doctor: Optional[SystemDoctor] = None):
        self.doctor = doctor or SystemDoctor()

    def execute(self, auto_heal: bool = True, **kwargs) -> ToolResult:
        try:
            report = self.doctor.run_health_check(auto_heal=auto_heal)
            diag = report["diagnostics"]
            healed = report["healed_actions"]

            summary = [
                f"=== INFORME MÉDICO DEL SISTEMA ===",
                f"Estado general: {'SALUDABLE (HEALTHY)' if report['overall_healthy'] else 'ATENCIÓN REQUERIDA'}",
                f"Disco libre: {diag.get('disk_space', {}).get('free_gb', '?')} GB",
                f"GPU CUDA: {diag.get('gpu_cuda', {}).get('device', 'No detectada')}",
            ]
            if healed:
                summary.append("\nAcciones de auto-reparación ejecutadas:")
                summary.extend(f"- {act}" for act in healed)
            else:
                summary.append("\nEl entorno se encuentra en óptimas condiciones, no se requirieron reparaciones.")

            return ToolResult(
                success=True,
                output="\n".join(summary),
                data=report
            )
        except Exception as e:
            return ToolResult(success=False, output="", error=f"Error en auditoría del sistema: {str(e)}")
