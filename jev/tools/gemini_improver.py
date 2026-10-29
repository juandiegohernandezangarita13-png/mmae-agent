"""
Herramienta de Introspección y Auto-Mejora Asistida por Gemini (ConsultGeminiAndSelfImproveTool).

Permite al agente consultar a la API de Gemini para analizar sus propias capacidades,
descubrir qué herramientas o funciones le faltan en su código, y autoprogramárselas
en tiempo de ejecución mediante Hot-Reloading sin requerir intervención humana.
"""
from typing import Dict, Any, Optional
from pathlib import Path

from jev.tools.base import BaseTool, ToolResult, ToolRegistry
from jev.config import AgentConfig, default_config


class ConsultGeminiAndSelfImproveTool(BaseTool):
    """
    Herramienta que conecta a JEV con la API de Gemini para auditar su propia suite
    de capacidades, diagnosticar vacíos y autoprogramar herramientas faltantes en caliente.
    """
    name = "consult_gemini_and_self_improve"
    description = (
        "Audita las herramientas y capacidades actuales del agente JEV, consulta a la API de Gemini "
        "para identificar qué funcionalidad de sistema o desarrollo falta en su código, y autoprograma, "
        "valida y carga en caliente (hot-reloading) la nueva herramienta en memoria sin reiniciar el proceso."
    )
    parameters = {
        "type": "object",
        "properties": {
            "focus_area": {
                "type": "string",
                "description": (
                    "Área o ámbito opcional en el que enfocar la mejora "
                    "(ej: 'clipboard', 'process_management', 'audio_tts', 'toast_notifications', "
                    "'git_automation', 'network_diagnostics', 'general')"
                )
            },
            "dry_run": {
                "type": "boolean",
                "description": "Si es True, únicamente consulta el diagnóstico de Gemini sin sintetizar ni inyectar el código."
            }
        },
        "required": []
    }

    def __init__(
        self,
        improver: Optional[Any] = None,
        registry: Optional[ToolRegistry] = None,
        config: Optional[AgentConfig] = None
    ):
        self.config = config or default_config
        self.registry = registry
        if improver is None:
            from jev.core.auto_improver import GeminiSelfImprover
            self.improver = GeminiSelfImprover(
                registry=registry or ToolRegistry(),
                config=self.config
            )
        else:
            self.improver = improver

    def execute(
        self,
        focus_area: Optional[str] = None,
        dry_run: bool = False,
        **kwargs
    ) -> ToolResult:
        try:
            if dry_run:
                # Sólo consulta diagnóstico
                proposal = self.improver.consult_gemini(focus_area=focus_area)
                output = (
                    f"🔍 [AUDITORÍA DE GEMINI - MODO DIAGNÓSTICO]\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"• Diagnóstico: {proposal.get('diagnosis')}\n"
                    f"• Capacidad Recomendada: {proposal.get('recommended_capability')}\n"
                    f"• Herramienta Propuesta: {proposal.get('tool_name')} ({proposal.get('class_name')})\n"
                    f"• Descripción: {proposal.get('description')}\n"
                    f"• Dependencias: {proposal.get('required_dependencies', [])}\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
                )
                return ToolResult(success=True, output=output, data=proposal)

            # Ejecución completa con síntesis y hot-reloading
            result = self.improver.run_cycle(focus_area=focus_area)

            if not result.get("success"):
                return ToolResult(
                    success=False,
                    output="",
                    error=result.get("error", "Fallo al autoprogramar la herramienta con Gemini."),
                    data=result
                )

            tool_name = result.get("tool_name")
            class_name = result.get("class_name")
            file_path = result.get("file_path")
            diagnosis = result.get("diagnosis")
            smoke_ok = result.get("smoke_test_success", False)
            smoke_out = result.get("smoke_test_output", "")

            report = (
                f"🚀 [AUTO-MEJORA CONCLUIDA CON ÉXITO]\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"1. AUDITORÍA GEMINI:\n"
                f"   {diagnosis}\n\n"
                f"2. HERRAMIENTA SINTETIZADA Y AUTOPROGRAMADA:\n"
                f"   • Nombre: `{tool_name}` (Clase: `{class_name}`)\n"
                f"   • Archivo persistente: `{file_path}`\n\n"
                f"3. ESTADO DE HOT-RELOADING:\n"
                f"   • Inyección en memoria: ✓ ACTIVA Y REGISTRADA EN TIEMPO DE EJECUCIÓN\n"
                f"   • Prueba de humo: {'✓ EXITOSA' if smoke_ok else '⚠️ REVISIÓN REQUERIDA'}\n"
                f"   • Salida de prueba: {smoke_out[:150]}\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"JEV ahora posee la capacidad `{tool_name}` y puede utilizarla inmediatamente."
            )

            return ToolResult(
                success=True,
                output=report,
                data=result
            )

        except Exception as e:
            return ToolResult(
                success=False,
                output="",
                error=f"Excepción en ConsultGeminiAndSelfImproveTool: {str(e)}"
            )
