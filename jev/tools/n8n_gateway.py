"""
Herramienta de Puerta de Enlace a Orquestadores de Integraciones (n8n / Activepieces Gateway).
Permite al agente ejecutar flujos de trabajo, disparar webhooks y acceder a más de 400 servicios SaaS
(Google Sheets, Slack, Jira, Notion, Discord, Airtable, HubSpot, GitHub) sin tener que programar
cada API individualmente en Python.
"""
from __future__ import annotations

import os
import json
from typing import Dict, Any, Optional
from pathlib import Path

from jev.tools.base import BaseTool, ToolResult
from jev.config import default_config


class N8nGatewayTool(BaseTool):
    """Puerta de enlace para ejecutar flujos de trabajo y webhooks en n8n o Activepieces."""
    name = "n8n_trigger_workflow"
    description = (
        "Dispara flujos de trabajo de automatización en n8n o Activepieces mediante Webhooks HTTP. "
        "Permite conectar al agente con más de 400 servicios externos (Google Sheets, Slack, Notion, "
        "Jira, Discord, GitHub, Correo) pasando parámetros en JSON y recibiendo el resultado del flujo."
    )
    parameters = {
        "type": "object",
        "properties": {
            "webhook_path_or_url": {
                "type": "string",
                "description": "Ruta del webhook en n8n local (ej: 'notificar-slack', 'guardar-lead') o URL completa (ej: 'http://localhost:5678/webhook/guardar-lead')."
            },
            "payload": {
                "type": "object",
                "description": "Diccionario JSON con los datos o parámetros a enviar al flujo de n8n."
            },
            "method": {
                "type": "string",
                "enum": ["POST", "GET"],
                "description": "Método HTTP para el webhook (defecto 'POST').",
                "default": "POST"
            },
            "timeout_seconds": {
                "type": "number",
                "description": "Tiempo límite de espera para la respuesta del flujo (defecto 30s).",
                "default": 30.0
            }
        },
        "required": ["webhook_path_or_url", "payload"]
    }

    def __init__(self, workspace_dir: Optional[Path] = None):
        self.workspace_dir = workspace_dir or default_config.workspace_dir
        self.n8n_base_url = os.getenv("N8N_BASE_URL", "http://localhost:5678").rstrip("/")

    def execute(
        self,
        webhook_path_or_url: str,
        payload: Dict[str, Any],
        method: str = "POST",
        timeout_seconds: float = 30.0,
        **kwargs
    ) -> ToolResult:
        import httpx

        target = (webhook_path_or_url or "").strip()
        if not target:
            return ToolResult(success=False, output="", error="Debes especificar webhook_path_or_url.")

        if target.startswith("http://") or target.startswith("https://"):
            full_url = target
        else:
            clean_path = target.lstrip("/")
            if not clean_path.startswith("webhook/"):
                clean_path = f"webhook/{clean_path}"
            full_url = f"{self.n8n_base_url}/{clean_path}"

        headers = {
            "Content-Type": "application/json",
            "User-Agent": "MMAE-Jeff-Agent/2.5"
        }
        api_key = os.getenv("N8N_API_KEY", "")
        if api_key:
            headers["X-N8N-API-KEY"] = api_key

        try:
            with httpx.Client(timeout=timeout_seconds) as client:
                if method.upper() == "POST":
                    resp = client.post(full_url, json=payload, headers=headers)
                else:
                    resp = client.get(full_url, params=payload, headers=headers)

                status_code = resp.status_code
                try:
                    res_json = resp.json()
                    res_body = json.dumps(res_json, indent=2, ensure_ascii=False)
                except Exception:
                    res_body = resp.text[:1000]

                if status_code in (200, 201, 202):
                    return ToolResult(
                        success=True,
                        output=f"✓ Flujo n8n ejecutado exitosamente (Código {status_code}) en {full_url}:\n{res_body}",
                        data={"url": full_url, "status_code": status_code, "response": res_body}
                    )
                else:
                    return ToolResult(
                        success=False,
                        output="",
                        error=f"El webhook n8n devolvió código de error HTTP {status_code} ({full_url}):\n{res_body}"
                    )
        except httpx.ConnectError:
            return ToolResult(
                success=False,
                output="",
                error=(
                    f"No se pudo conectar a n8n en '{full_url}'. "
                    "Asegúrate de que tu instancia de n8n o Activepieces esté corriendo localmente (ej: docker run -p 5678:5678 n8nio/n8n) "
                    "o configura N8N_BASE_URL en el archivo .env."
                )
            )
        except Exception as e:
            return ToolResult(success=False, output="", error=f"Error invocando flujo n8n: {e}")
