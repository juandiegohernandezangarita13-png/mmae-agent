"""
Herramienta de Integración con Claude Code (Free-Claude-Code + OpenRouter) para JEV.
Permite delegar tareas de programación avanzada, refactorización, razonamiento
y generación de código senior a Claude Code operando sobre el proxy local.
"""
from typing import Dict, Any, Optional, List
from pathlib import Path
import json
import os

from jev.tools.base import BaseTool, ToolResult
from jev.core.claude_code_service import FreeClaudeCodeService
from jev.core.claude_code_bridge import ClaudeCodeBridge
from jev.config import default_config


class ClaudeCodeTool(BaseTool):
    """
    Herramienta oficial para interactuar con Claude Code local a través del proxy Free-Claude-Code.
    Aprovecha OpenRouter (incluyendo modelos gratuitos) y modelos de última generación.
    """
    name = "skill_claude_code"
    description = (
        "Conector profundo con Claude Code (Free-Claude-Code) conectado a OpenRouter. "
        "Permite: 1. query (consultas de razonamiento), 2. generate_code (generación y refactorización de software senior), "
        "3. server_status (monitoreo del proxy y modelos), 4. start_server / stop_server, 5. configure (actualizar API key de OpenRouter y modelo)."
    )
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "Acción a ejecutar",
                "enum": ["query", "generate_code", "server_status", "start_server", "stop_server", "configure"],
                "default": "query"
            },
            "prompt": {
                "type": "string",
                "description": "Instrucción, pregunta o descripción de la tarea a resolver",
                "default": ""
            },
            "context": {
                "type": "string",
                "description": "Contexto de código previo o archivos del proyecto relevantes",
                "default": ""
            },
            "language": {
                "type": "string",
                "description": "Lenguaje de programación objetivo para generate_code",
                "default": "python"
            },
            "model": {
                "type": "string",
                "description": "Modelo objetivo en formato provider/model (ej. 'open_router/anthropic/claude-3.5-sonnet', 'open_router/meta-llama/llama-3.3-70b-instruct:free')",
                "default": ""
            },
            "openrouter_key": {
                "type": "string",
                "description": "Clave API de OpenRouter (para acción 'configure')",
                "default": ""
            },
            "system_prompt": {
                "type": "string",
                "description": "Directiva o prompt de sistema personalizado",
                "default": ""
            },
            "output_path": {
                "type": "string",
                "description": "Ruta de archivo relativa a workspace para guardar automáticamente el código generado",
                "default": ""
            }
        },
        "required": ["action"]
    }

    def __init__(self, workspace_dir: Optional[str] = None):
        super().__init__()
        self.workspace_dir = Path(workspace_dir or default_config.workspace_dir)
        self.service = FreeClaudeCodeService()
        self.bridge = ClaudeCodeBridge(service=self.service)

    def execute(self, **kwargs) -> ToolResult:
        action = kwargs.get("action", "query")
        prompt = kwargs.get("prompt", "").strip()
        context = kwargs.get("context", "").strip()
        language = kwargs.get("language", "python").strip()
        model = kwargs.get("model", "").strip() or None
        openrouter_key = kwargs.get("openrouter_key", "").strip()
        system_prompt = kwargs.get("system_prompt", "").strip() or None
        output_path = kwargs.get("output_path", "").strip()

        try:
            # 1. SERVER_STATUS
            if action == "server_status":
                status = self.service.get_status()
                healthy_str = "OPERATIVO ✅" if status["is_healthy"] else ("ARRANCADO (Inicializando) ⏳" if status["is_running"] else "DETENIDO ⛔")
                out = (
                    f"🤖 [Estado de Free-Claude-Code Proxy]: {healthy_str}\n"
                    f" • Endpoint Base: {status['base_url']}\n"
                    f" • Puerto: {status['port']}\n"
                    f" • Modelo por defecto: {status['configured_model']}\n"
                    f" • OpenRouter configurado: {'Sí' if status['openrouter_configured'] else 'No (requiere API key)'}\n"
                    f" • Log: {status['log_path']}"
                )
                if status.get("providers_status"):
                    out += "\n • Proveedores detectados:\n"
                    for pid, pdata in status["providers_status"].items():
                        out += f"    - {pid}: {pdata.get('label', pdata.get('status'))} ({pdata.get('kind')})\n"
                return ToolResult(success=True, output=out.strip(), data=status)

            # 2. START_SERVER
            elif action == "start_server":
                ok, msg = self.service.start()
                status = self.service.get_status()
                return ToolResult(success=ok, output=f"🚀 [Claude Code Server]: {msg}", data=status)

            # 3. STOP_SERVER
            elif action == "stop_server":
                ok, msg = self.service.stop()
                return ToolResult(success=ok, output=f"🛑 [Claude Code Server]: {msg}", data={"stopped": ok})

            # 4. CONFIGURE
            elif action == "configure":
                if not openrouter_key and not model:
                    return ToolResult(success=False, output="", error="Debes especificar 'openrouter_key' o 'model' para configurar.")
                
                updated = self.service.sync_openrouter_key(api_key=openrouter_key, model=model)
                out = "⚙️ [Configuración de Claude Code actualizada]:\n"
                if openrouter_key:
                    out += " • Clave OpenRouter sincronizada y persistida en .env y ~/.fcc/.env.\n"
                if model:
                    out += f" • Modelo predeterminado asignado: '{model}'.\n"
                out += "Para aplicar cambios en caliente, reinicia el servidor si ya estaba activo."
                return ToolResult(success=updated, output=out.strip(), data={"configured": True, "model": self.service.default_model})

            # 5. GENERATE_CODE
            elif action == "generate_code":
                if not prompt:
                    return ToolResult(success=False, output="", error="Debes proporcionar 'prompt' con la descripción del código a generar.")

                resp = self.bridge.generate_code(
                    task_description=prompt,
                    context=context,
                    language=language,
                    model=model
                )
                if not resp.is_success:
                    return ToolResult(success=False, output="", error=f"Fallo al generar código con Claude Code: {resp.error}")

                saved_file = None
                code_to_save = ""
                if resp.code_blocks:
                    code_to_save = resp.code_blocks[0].code
                else:
                    code_to_save = resp.content

                if output_path and code_to_save:
                    dest = self.workspace_dir / output_path
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_text(code_to_save, encoding="utf-8")
                    saved_file = str(dest)

                out = f"💻 [Código generado por Claude Code ({resp.model or self.service.default_model})]:\n\n{resp.content}"
                if saved_file:
                    out += f"\n\n📁 Archivo guardado con éxito en: `{saved_file}`"

                data = {
                    "content": resp.content,
                    "code": code_to_save,
                    "language": language,
                    "code_blocks_count": len(resp.code_blocks),
                    "saved_file": saved_file,
                    "model": resp.model,
                    "usage": resp.usage
                }
                return ToolResult(success=True, output=out, data=data)

            # 6. QUERY
            elif action == "query":
                if not prompt:
                    return ToolResult(success=False, output="", error="Debes proporcionar 'prompt' para la consulta.")

                resp = self.bridge.query(prompt=prompt, system=system_prompt, model=model)
                if not resp.is_success:
                    return ToolResult(success=False, output="", error=f"Fallo en consulta a Claude Code: {resp.error}")

                out = f"🧠 [Respuesta de Claude Code]:\n{resp.content}"
                if resp.thinking:
                    out = f"💭 [Pensamiento]:\n{resp.thinking}\n\n" + out

                data = {
                    "content": resp.content,
                    "thinking": resp.thinking,
                    "model": resp.model,
                    "usage": resp.usage,
                    "code_blocks": [b.code for b in resp.code_blocks]
                }
                return ToolResult(success=True, output=out, data=data)

            return ToolResult(success=False, output="", error=f"Acción '{action}' no reconocida en ClaudeCodeTool.")

        except Exception as e:
            return ToolResult(success=False, output="", error=f"Error en ClaudeCodeTool: {str(e)}")
