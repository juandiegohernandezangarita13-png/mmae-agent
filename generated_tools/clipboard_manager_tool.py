from jev.tools.base import BaseTool, ToolResult

class ClipboardManagerTool(BaseTool):
    name = "clipboard_manager_tool"
    description = "Esta herramienta permite leer y escribir en el portapapeles del sistema con formato y texto, facilitando la compartición de información entre diferentes herramientas y procesos."
    parameters = {
        "action": {
            "type": "string",
            "enum": ["read", "write"],
            "description": "Acción a realizar: leer o escribir en el portapapeles."
        },
        "text": {
            "type": "string",
            "description": "Texto a escribir en el portapapeles (requerido solo para la acción 'write')."
        }
    }

    def execute(self, **kwargs) -> ToolResult:
        try:
            import pyperclip
            action = kwargs.get("action")
            text = kwargs.get("text")

            if action == "read":
                clipboard_content = pyperclip.paste()
                return ToolResult(success=True, output=clipboard_content)
            elif action == "write":
                if text is None:
                    return ToolResult(success=False, output="", error="El parámetro 'text' es requerido para la acción 'write'.")
                pyperclip.copy(text)
                return ToolResult(success=True, output="Texto escrito en el portapapeles.")
            else:
                return ToolResult(success=False, output="", error="Acción no reconocida. Use 'read' o 'write'.")
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))