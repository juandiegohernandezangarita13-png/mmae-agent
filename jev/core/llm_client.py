"""
Cliente LLM para interactuar con motores locales (Ollama y LM Studio).
Soporta function calling nativo y fallback con parser inteligente de JSON/texto.
"""
from typing import List, Dict, Any, Optional, Tuple
import json
import re
import time
import logging
import httpx

from jev.config import AgentConfig, default_config

logger = logging.getLogger(__name__)


class LLMResponse:
    """Representa la respuesta procesada del modelo LLM."""
    def __init__(
        self,
        content: str,
        tool_calls: Optional[List[Dict[str, Any]]] = None,
        raw_response: Optional[Dict[str, Any]] = None
    ):
        self.content = content or ""
        self.tool_calls = tool_calls or []
        self.raw_response = raw_response or {}

    @property
    def has_tool_calls(self) -> bool:
        return len(self.tool_calls) > 0


class LocalLLMClient:
    """Cliente HTTP robusto para inferencia local con Ollama y LM Studio."""

    def __init__(self, config: Optional[AgentConfig] = None):
        self.config = config or default_config
        # 1. Configuración de Timeouts Granulares: connect=10.0s, read=300.0s (mínimo 5 min)
        self.connect_timeout = float(getattr(self.config, "connect_timeout", 10.0))
        self.read_timeout = max(float(getattr(self.config, "read_timeout", 300.0)), 300.0)
        self.timeout = httpx.Timeout(
            connect=self.connect_timeout,
            read=self.read_timeout,
            write=30.0,
            pool=10.0
        )
        self._sleep_fn = time.sleep
        from jev.core.free_model_router import FreeModelRouter
        self.free_router = FreeModelRouter(
            api_key=getattr(self.config, "openrouter_api_key", ""),
            fcc_base_url=getattr(self.config, "fcc_base_url", "http://127.0.0.1:8082")
        )

    def _get_endpoint_and_headers(self, model: str = "") -> Tuple[str, Dict[str, str]]:
        if "gemini" in model.lower() and getattr(self.config, "gemini_api_key", ""):
            url = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
            headers = {
                "Authorization": f"Bearer {self.config.gemini_api_key}",
                "Content-Type": "application/json"
            }
        elif "/" in model or ":free" in model or model.startswith("open_router"):
            url = "https://openrouter.ai/api/v1/chat/completions"
            headers = {
                "Authorization": f"Bearer {getattr(self.config, 'openrouter_api_key', '')}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://github.com/jev-agent",
                "X-Title": "JEV Agent"
            }
        elif self.config.llm_provider == "lmstudio":
            url = f"{self.config.lmstudio_base_url.rstrip('/')}/chat/completions"
            headers = {"Content-Type": "application/json"}
        else:
            url = f"{self.config.ollama_base_url.rstrip('/')}/v1/chat/completions"
            headers = {"Content-Type": "application/json"}
        return url, headers

    def _prune_messages_for_local_inference(
        self,
        messages: List[Dict[str, Any]],
        max_tool_chars: int = 1000
    ) -> List[Dict[str, Any]]:
        """
        Poda y compacta el contexto para acelerar la fase de prefill en inferencia local (Ollama).
        Conserva el prompt de sistema y la meta invariantes.
        Trunca salidas extensas de herramientas que saturan el búfer de tokens y la memoria VRAM.
        """
        if not messages:
            return []

        pruned = []
        for idx, m in enumerate(messages):
            role = m.get("role")
            if role == "tool":
                content = str(m.get("content", ""))
                limit = max_tool_chars if idx < len(messages) - 2 else max_tool_chars * 2
                if len(content) > limit:
                    truncated = content[:limit] + f"\n... [Truncado {len(content) - limit} caracteres para optimizar prefill VRAM]"
                    pruned.append({**m, "content": truncated})
                else:
                    pruned.append(m)
            elif role == "assistant" and m.get("content"):
                c = str(m.get("content", ""))
                if len(c) > max_tool_chars * 2 and idx < len(messages) - 2:
                    pruned.append({**m, "content": c[:max_tool_chars * 2] + "..."})
                else:
                    pruned.append(m)
            else:
                pruned.append(m)

        return pruned

    def think(self, user_goal: str, context: Optional[str] = None) -> str:
        """
        Utiliza el mejor modelo disponible en la cascada de razonamiento ("de la mejor a la menos mala")
        para descomponer la tarea y guiar al ejecutor.
        """
        prompt = f"""Actúa como el Cerebro Estratégico (Thinker) de JEV.
OBJETIVO DEL USUARIO: {user_goal}
{f'CONTEXTO ADICIONAL: {context}' if context else ''}

Analiza la meta, diseña el plan paso a paso y define exactamente qué herramientas y acciones (pantalla, archivos, web, github, código) debe ejecutar el modelo ejecutor en Windows.
Sé analítico, preciso y estructurado."""

        messages = [
            {"role": "system", "content": "Eres el módulo de pensamiento estratégico avanzado (Cerebro Senior) de JEV."},
            {"role": "user", "content": prompt}
        ]

        try:
            candidates = self.free_router.get_ranked_candidates()
            top_model = candidates[0].id if candidates else self.config.thinker_model
            res = self.chat(messages=messages, override_model=top_model)
            return res.content
        except Exception as e:
            return f"(Pensamiento estratégico local): Planificando ejecución para '{user_goal}'."

    def chat(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        override_model: Optional[str] = None
    ) -> LLMResponse:
        """
        Envía una solicitud de chat con cascada inteligente de modelos gratuitos
        ordenados de mayor a menor calidad ("de la mejor a la menos mala"),
        reintentos con backoff exponencial, persistencia en VRAM y conmutación automática.
        """
        # Determinar la lista jerárquica de modelos a probar
        if override_model:
            models_to_try = [override_model]
            if getattr(self.config, "use_free_model_cascade", True):
                cascade = [c.id for c in self.free_router.get_ranked_candidates()]
                models_to_try += [m for m in cascade if m != override_model]
        elif self.config.llm_provider == "gemini" and getattr(self.config, "gemini_api_key", ""):
            target_model = self.config.model_name or "gemini-2.5-flash"
            models_to_try = [target_model, "gemini-flash-latest"]
        elif self.config.llm_provider in ("ollama", "lmstudio"):
            target_model = self.config.model_name
            models_to_try = [target_model] + [m for m in self.config.fallback_models if m != target_model]
            if getattr(self.config, "use_free_model_cascade", True):
                cascade = [c.id for c in self.free_router.get_ranked_candidates()]
                models_to_try += [m for m in cascade if m not in models_to_try]
        else:
            if getattr(self.config, "use_free_model_cascade", True):
                cascade = [c.id for c in self.free_router.get_ranked_candidates()]
                models_to_try = cascade + [m for m in self.config.fallback_models if m not in cascade]
            else:
                target_model = self.config.model_name
                models_to_try = [target_model] + [m for m in self.config.fallback_models if m != target_model]

        last_error = None
        max_retries = max(getattr(self.config, "llm_max_retries", 2), 2)

        for model_candidate in models_to_try:
            # 0. Soporte para Claude Code (Free-Claude-Code local daemon)
            if self.config.llm_provider in ("claude_code", "fcc"):
                from jev.core.claude_code_bridge import ClaudeCodeBridge
                bridge = ClaudeCodeBridge(default_model=model_candidate)
                sys_content = None
                chat_msgs = []
                for m in messages:
                    if m.get("role") == "system" and sys_content is None:
                        sys_content = m.get("content")
                    else:
                        chat_msgs.append(m)
                res = bridge.send_message(
                    messages=chat_msgs,
                    system=sys_content,
                    model=model_candidate if "/" in model_candidate else None,
                    max_tokens=getattr(self.config, "max_tokens", 2048),
                    temperature=self.config.temperature,
                    tools=tools
                )
                if res.is_success:
                    self.free_router.report_success(model_candidate)
                    return LLMResponse(
                        content=res.content,
                        tool_calls=res.tool_calls,
                        raw_response=res.raw_response
                    )
                else:
                    self.free_router.report_error(model_candidate)
                    last_error = RuntimeError(res.error)
                    continue

            # Determinar endpoint y cabeceras
            url, headers = self._get_endpoint_and_headers(model_candidate)
            is_cloud = ("googleapis.com" in url) or ("openrouter.ai" in url)

            effective_messages = messages if is_cloud else self._prune_messages_for_local_inference(messages)

            # Normalizar nombre de modelo para OpenRouter si tiene prefijo interno open_router/
            clean_model = model_candidate.replace("open_router/", "")

            payload: Dict[str, Any] = {
                "model": clean_model,
                "messages": effective_messages,
                "temperature": self.config.temperature,
                "max_tokens": getattr(self.config, "max_tokens", 2048),
                "stream": False
            }

            if not is_cloud:
                payload["keep_alive"] = getattr(self.config, "ollama_keep_alive", "30m")

            if tools:
                payload["tools"] = tools
                payload["tool_choice"] = "auto"

            # Reintentos con backoff exponencial
            for attempt in range(max_retries + 1):
                try:
                    with httpx.Client(timeout=self.timeout) as client:
                        response = client.post(url, json=payload, headers=headers)

                    if response.status_code == 200:
                        data = response.json()
                        choices = data.get("choices", [])
                        if not choices:
                            return LLMResponse(content="", raw_response=data)

                        message = choices[0].get("message", {})
                        content = message.get("content", "") or ""
                        raw_tool_calls = message.get("tool_calls", [])

                        parsed_tool_calls: List[Dict[str, Any]] = []
                        if raw_tool_calls:
                            for tc in raw_tool_calls:
                                func = tc.get("function", {})
                                name = func.get("name", "")
                                args_str = func.get("arguments", "{}")
                                try:
                                    args = json.loads(args_str) if isinstance(args_str, str) else args_str
                                except Exception:
                                    args = {}
                                parsed_tool_calls.append({"name": name, "arguments": args, "id": tc.get("id")})

                        if not parsed_tool_calls and content:
                            fallback_calls = self._extract_tool_calls_from_text(content)
                            if fallback_calls:
                                parsed_tool_calls.extend(fallback_calls)

                        self.free_router.report_success(model_candidate)
                        return LLMResponse(
                            content=content,
                            tool_calls=parsed_tool_calls,
                            raw_response=data
                        )

                    # Manejo de Rate Limit (HTTP 429) -> Cooldown y cascada inmediata
                    if response.status_code == 429:
                        self.free_router.report_rate_limit(model_candidate, cooldown_seconds=60)
                        last_error = f"Rate Limit (429) en {model_candidate}"
                        break  # Pasar inmediatamente al siguiente modelo de la cascada

                    # Errores transitorios de servidor (502, 503, 504)
                    if response.status_code in (502, 503, 504) and attempt < max_retries:
                        backoff = min(0.5 * (2 ** attempt), 4.0)
                        logger.warning(f"Error {response.status_code} con {model_candidate}. Reintentando con backoff en {backoff:.1f}s (intento {attempt+1}/{max_retries})...")
                        self._sleep_fn(backoff)
                        continue

                    self.free_router.report_error(model_candidate)
                    last_error = f"Servidor {model_candidate} ({response.status_code}): {response.text[:150]}"
                    break

                except (httpx.TimeoutException, httpx.ConnectError, httpx.RemoteProtocolError) as net_err:
                    last_error = f"Error de red con {model_candidate}: {net_err}"
                    if attempt < max_retries:
                        backoff = min(0.5 * (2 ** attempt), 4.0)
                        logger.warning(f"Timeout o fallo de red con {model_candidate} ({net_err}). Reintentando con backoff en {backoff:.1f}s (intento {attempt+1}/{max_retries})...")
                        self._sleep_fn(backoff)
                        continue
                    self.free_router.report_error(model_candidate)
                    break

        # Si agotamos todos los candidatos, intentar con el modelo local Ollama directamente con keep_alive y reintentos
        try:
            local_url = f"{self.config.ollama_base_url.rstrip('/')}/v1/chat/completions"
            local_payload = {
                "model": self.config.executor_model,
                "messages": self._prune_messages_for_local_inference(messages),
                "temperature": self.config.temperature,
                "max_tokens": self.config.max_tokens,
                "stream": False,
                "keep_alive": getattr(self.config, "ollama_keep_alive", "30m")
            }
            if tools:
                local_payload["tools"] = tools
                local_payload["tool_choice"] = "auto"

            for attempt in range(max_retries + 1):
                try:
                    with httpx.Client(timeout=self.timeout) as client:
                        res_local = client.post(local_url, json=local_payload, headers={"Content-Type": "application/json"})
                    if res_local.status_code == 200:
                        data = res_local.json()
                        msg = data.get("choices", [{}])[0].get("message", {})
                        content = msg.get("content", "") or ""
                        tcs = msg.get("tool_calls", []) or self._extract_tool_calls_from_text(content)
                        return LLMResponse(content=content, tool_calls=tcs, raw_response=data)
                    elif res_local.status_code in (502, 503, 504) and attempt < max_retries:
                        self._sleep_fn(min(0.5 * (2 ** attempt), 4.0))
                        continue
                    break
                except (httpx.TimeoutException, httpx.ConnectError, httpx.RemoteProtocolError):
                    if attempt < max_retries:
                        self._sleep_fn(min(0.5 * (2 ** attempt), 4.0))
                        continue
                    break
        except Exception:
            pass

        raise RuntimeError(f"No se pudo completar la llamada con ningún modelo. Último fallo: {last_error}")

    def _extract_tool_calls_from_text(self, text: str) -> List[Dict[str, Any]]:
        """
        Detecta bloques de código o JSON estructurado en la salida de texto
        que representen una intención de llamar a una herramienta.
        Soporta múltiples llamadas consecutivas en un mismo turno.
        """
        calls = []
        decoder = json.JSONDecoder()
        idx = 0
        text_len = len(text)

        while idx < text_len:
            start = text.find("{", idx)
            if start == -1:
                break
            try:
                obj, end = decoder.raw_decode(text[start:])
                if isinstance(obj, dict):
                    name = obj.get("tool") or obj.get("name") or obj.get("action")
                    args = obj.get("arguments") or obj.get("parameters") or obj.get("args") or {}
                    if name and isinstance(name, str):
                        calls.append({"name": name, "arguments": args if isinstance(args, dict) else {}})
                idx = start + max(end, 1)
            except Exception:
                idx = start + 1

        return calls
