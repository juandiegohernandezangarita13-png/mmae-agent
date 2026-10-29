
from jev.tools.base import BaseTool, ToolResult

class WordCounterTool(BaseTool):
    name = "count_words"
    description = "Cuenta el numero de palabras en un texto."
    parameters = {
        "type": "object",
        "properties": {
            "text": {"type": "string", "description": "Texto a analizar"}
        },
        "required": ["text"]
    }

    def execute(self, text: str, **kwargs) -> ToolResult:
        words = len(text.split())
        return ToolResult(success=True, output=f"Total de palabras: {words}", data={"words": words})
