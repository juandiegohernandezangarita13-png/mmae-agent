"""
Puente Programático de Comunicación con Claude Code (Anthropic Messages API via FCC).
Permite a JEV enviar instrucciones de desarrollo, recibir razonamiento estructurado,
generar código y ejecutar llamadas a herramientas transparentemente a través del proxy local.
"""
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
import urllib.request
import urllib.error
import json
import time
import re

from jev.core.claude_code_service import FreeClaudeCodeService


@dataclass
class CodeSnippet:
    language: str
    code: str
    filename: Optional[str] = None


@dataclass
class ClaudeCodeResponse:
    content: str
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    thinking: str = ""
    code_blocks: List[CodeSnippet] = field(default_factory=list)
    model: str = ""
    usage: Dict[str, int] = field(default_factory=dict)
    is_success: bool = True
    error: Optional[str] = None
    raw_response: Dict[str, Any] = field(default_factory=dict)


class ClaudeCodeBridge:
    """Cliente HTTP de alta resiliencia para la Messages API de Claude Code."""

    def __init__(
        self,
        service: Optional[FreeClaudeCodeService] = None,
        base_url: Optional[str] = None,
        auth_token: str = "freecc",
        default_model: Optional[str] = None,
        timeout: float = 180.0
    ):
        self.service = service or FreeClaudeCodeService()
        self.base_url = (base_url or self.service.base_url).rstrip("/")
        self.auth_token = auth_token
        self.default_model = default_model or self.service.default_model
        self.timeout = timeout

    def send_message(
        self,
        messages: List[Dict[str, Any]],
        system: Optional[str] = None,
        model: Optional[str] = None,
        max_tokens: int = 4096,
        temperature: float = 0.2,
        tools: Optional[List[Dict[str, Any]]] = None,
        stream: bool = False
    ) -> ClaudeCodeResponse:
        """
        Envía una solicitud conformada según la especificación de Anthropic Messages API (/v1/messages).
        Levanta automáticamente el daemon si está inactivo.
        """
        # Garantizar que el servicio esté corriendo
        is_ok, msg = self.service.ensure_running()
        if not is_ok and not self.service.is_healthy():
            return ClaudeCodeResponse(
                content="",
                is_success=False,
                error=f"No se pudo conectar al servidor local de Claude Code: {msg}"
            )

        target_model = model or self.default_model
        endpoint = f"{self.base_url}/v1/messages"

        # Formatear mensajes compatibles con Anthropic
        anthropic_messages = []
        for m in messages:
            role = m.get("role", "user")
            # Anthropic solo acepta 'user' o 'assistant' en messages[]
            if role in ("system",):
                continue
            content = m.get("content", "")
            if isinstance(content, list):
                anthropic_messages.append({"role": role, "content": content})
            else:
                anthropic_messages.append({"role": role, "content": str(content)})

        if not anthropic_messages:
            anthropic_messages.append({"role": "user", "content": "Hola Claude Code."})

        payload: Dict[str, Any] = {
            "model": target_model,
            "messages": anthropic_messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": stream
        }

        if system:
            payload["system"] = system

        if tools:
            # Transformar o adjuntar herramientas
            payload["tools"] = tools

        headers = {
            "Content-Type": "application/json",
            "anthropic-version": "2023-06-01",
            "x-api-key": self.auth_token,
            "Authorization": f"Bearer {self.auth_token}",
            "User-Agent": "JEV-ClaudeCodeBridge/1.0"
        }

        try:
            req_data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(endpoint, data=req_data, headers=headers, method="POST")

            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                resp_text = resp.read().decode("utf-8")
                raw = json.loads(resp_text)
                return self._parse_anthropic_response(raw)

        except urllib.error.HTTPError as he:
            err_body = he.read().decode("utf-8", errors="ignore")
            err_msg = f"HTTP {he.code}: {err_body}"
            try:
                err_json = json.loads(err_body)
                if "error" in err_json and isinstance(err_json["error"], dict):
                    err_msg = err_json["error"].get("message", err_msg)
            except Exception:
                pass
            return ClaudeCodeResponse(content="", is_success=False, error=err_msg)

        except Exception as e:
            return ClaudeCodeResponse(content="", is_success=False, error=f"Error en comunicación con Claude Code: {str(e)}")

    def _parse_anthropic_response(self, raw: Dict[str, Any]) -> ClaudeCodeResponse:
        """Parsea la respuesta estándar de Anthropic Messages extraída de FCC."""
        text_parts = []
        thinking_parts = []
        tool_calls = []

        content_list = raw.get("content", [])
        if isinstance(content_list, list):
            for block in content_list:
                if isinstance(block, dict):
                    b_type = block.get("type")
                    if b_type == "text":
                        text_parts.append(block.get("text", ""))
                    elif b_type == "thinking":
                        thinking_parts.append(block.get("thinking", ""))
                    elif b_type == "tool_use":
                        tool_calls.append({
                            "id": block.get("id"),
                            "name": block.get("name"),
                            "arguments": block.get("input", {})
                        })
        elif isinstance(content_list, str):
            text_parts.append(content_list)

        full_text = "\n".join(text_parts).strip()
        thinking_text = "\n".join(thinking_parts).strip()

        # Extraer bloques de código Markdown estructurados
        code_blocks = self._extract_code_blocks(full_text)

        return ClaudeCodeResponse(
            content=full_text,
            tool_calls=tool_calls,
            thinking=thinking_text,
            code_blocks=code_blocks,
            model=raw.get("model", ""),
            usage=raw.get("usage", {}),
            is_success=True,
            raw_response=raw
        )

    @staticmethod
    def _extract_code_blocks(text: str) -> List[CodeSnippet]:
        """Extrae bloques de código ```lenguaje ... ``` del texto."""
        pattern = re.compile(r"```([a-zA-Z0-9_\-\.\+]*)\n(.*?)```", re.DOTALL)
        snippets = []
        for match in pattern.finditer(text):
            lang = match.group(1).strip() or "text"
            code = match.group(2)
            filename = None
            first_line = code.strip().split("\n")[0] if code.strip() else ""
            file_match = re.match(r"^(?:#|//|<!--|/\*)\s*(?:file|path):\s*([^\s\*]+)", first_line, re.IGNORECASE)
            if file_match:
                filename = file_match.group(1).strip()
            snippets.append(CodeSnippet(language=lang, code=code, filename=filename))
        return snippets

    def query(
        self,
        prompt: str,
        system: Optional[str] = None,
        model: Optional[str] = None
    ) -> ClaudeCodeResponse:
        """Consulta directa en una sola llamada sin estado."""
        messages = [{"role": "user", "content": prompt}]
        return self.send_message(messages=messages, system=system, model=model)

    def generate_code(
        self,
        task_description: str,
        context: str = "",
        language: str = "python",
        model: Optional[str] = None
    ) -> ClaudeCodeResponse:
        """Instrucción especializada para síntesis y arquitectura de código senior."""
        sys_prompt = (
            "Eres un Arquitecto de Software Senior y Desarrollador Especialista en Claude Code. "
            "Genera código de calidad de producción, altamente robusto, tipado estrictamente, "
            "sin valores hardcodeados y con control de excepciones exhaustivo. "
            "Entrega siempre el código completo en bloques markdown bien formateados."
        )

        user_content = f"Tarea de Programación: {task_description}\n"
        if context:
            user_content += f"\nContexto / Código previo relevante:\n{context}\n"
        user_content += f"\nPor favor genera la solución completa y lista para ejecutar en lenguaje: {language}."

        return self.send_message(
            messages=[{"role": "user", "content": user_content}],
            system=sys_prompt,
            model=model
        )
