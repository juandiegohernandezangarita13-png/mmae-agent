"""
Herramienta de Portapapeles para Windows.
Autogenerada por el módulo de auto-mejora de JEV.
"""
from typing import Dict, Any, Optional
import subprocess

from jev.tools.base import BaseTool, ToolResult


class SystemClipboardTool(BaseTool):
    """Lee y escribe contenido en el portapapeles nativo de Windows."""
    name = "system_clipboard_tool"
    description = "Lee y escribe contenido en el portapapeles nativo de Windows."
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "Acción a realizar: 'read' (leer portapapeles) o 'write' (escribir texto al portapapeles)",
                "enum": ["read", "write"]
            },
            "text": {
                "type": "string",
                "description": "Texto a copiar al portapapeles cuando action='write'."
            }
        },
        "required": ["action"]
    }

    def execute(self, action: str = "read", text: Optional[str] = None, **kwargs) -> ToolResult:
        try:
            if action == "read":
                cmd = "Get-Clipboard"
                proc = subprocess.run(["powershell", "-NoProfile", "-Command", cmd], capture_output=True, text=True, timeout=10)
                content = proc.stdout.strip()
                return ToolResult(
                    success=True,
                    output=f"[Portapapeles]: {content}" if content else "[Portapapeles vacío]",
                    data={"clipboard_content": content}
                )
            elif action == "write":
                if text is None:
                    return ToolResult(success=False, output="", error="Parámetro 'text' requerido para escribir.")
                # Escribir usando powershell Set-Clipboard
                proc = subprocess.run(["powershell", "-NoProfile", "-Command", "$input | Set-Clipboard"], input=text, capture_output=True, text=True, timeout=10)
                return ToolResult(
                    success=True,
                    output=f"Texto ({len(text)} caracteres) copiado exitosamente al portapapeles.",
                    data={"copied_length": len(text)}
                )
            else:
                return ToolResult(success=False, output="", error=f"Acción '{action}' no soportada.")
        except Exception as exc:
            return ToolResult(success=False, output="", error=f"Fallo en SystemClipboardTool: {exc}")