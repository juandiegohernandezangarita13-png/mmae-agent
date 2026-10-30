"""
Módulo de Enrutamiento y Toma de Decisiones Rápidas System-1: 'Jev' (TypeSafe AI).
Diseñado para tomar decisiones estructuradas en ultra-baja latencia (<200ms) antes
de invocar LLMs pesados o ejecutar herramientas críticas del sistema.

Primitivas de decisión implementadas:
1. Choice: Clasificación de intención o selección de herramienta con distribución de probabilidad y confianza.
2. Score: Evaluación de métricas continuas (complejidad, riesgo, urgencia).
3. Noul: Filtro de seguridad binario estricto (True/False) pre-ejecución de comandos y archivos.
"""
from __future__ import annotations

import os
import re
import time
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional, Tuple, Union

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False
    import urllib.request
    import urllib.error
    import json

logger = logging.getLogger("JevRouter")
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter("[%(asctime)s] [%(name)s] [%(levelname)s]: %(message)s", "%Y-%m-%d %H:%M:%S")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)


# =====================================================================
# Modelos de Datos Tipados para las Primitivas de Jev (TypeSafe AI)
# =====================================================================

@dataclass(slots=True)
class ChoiceResult:
    """Resultado de la primitiva Choice de Jev."""
    selected: str
    confidence: float
    probabilities: Dict[str, float]
    rationale: Optional[str] = None
    latency_ms: float = 0.0
    source: str = "typesafe_api"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "selected": self.selected,
            "confidence": self.confidence,
            "probabilities": self.probabilities,
            "rationale": self.rationale,
            "latency_ms": self.latency_ms,
            "source": self.source,
        }


@dataclass(slots=True)
class ScoreResult:
    """Resultado de la primitiva Score de Jev."""
    score: float
    confidence: float
    metric: str
    rationale: Optional[str] = None
    latency_ms: float = 0.0
    source: str = "typesafe_api"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "score": self.score,
            "confidence": self.confidence,
            "metric": self.metric,
            "rationale": self.rationale,
            "latency_ms": self.latency_ms,
            "source": self.source,
        }


@dataclass(slots=True)
class NoulResult:
    """Resultado de la primitiva Noul (Filtro Binario de Seguridad) de Jev."""
    allowed: bool
    confidence: float
    violation_reason: Optional[str] = None
    latency_ms: float = 0.0
    source: str = "typesafe_api"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "allowed": self.allowed,
            "confidence": self.confidence,
            "violation_reason": self.violation_reason,
            "latency_ms": self.latency_ms,
            "source": self.source,
        }


@dataclass(slots=True)
class PreFlightDecision:
    """Decisión integral de pre-vuelo antes de invocar inferencia pesada."""
    action: str  # "proceed_llm", "fast_deterministic", "blocked_security"
    safety: NoulResult
    complexity: ScoreResult
    choice: ChoiceResult
    total_latency_ms: float
    recommended_tool: Optional[str] = None
    direct_response: Optional[str] = None


# =====================================================================
# Cliente de Conexión a la API de TypeSafe AI System-1
# =====================================================================

class TypeSafeSystemOneClient:
    """
    Cliente HTTP optimizado con pooling de conexiones y timeout estricto
    para interactuar con el endpoint System-1 de TypeSafe AI.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        api_url: Optional[str] = None,
        timeout_seconds: float = 0.200
    ):
        self.api_key = api_key or os.getenv("TYPESAFE_API_KEY", "")
        self.api_url = (api_url or os.getenv("TYPESAFE_API_URL", "https://api.typesafe.ai/v1/systemone")).rstrip("/")
        self.timeout_seconds = float(os.getenv("TYPESAFE_TIMEOUT_SECONDS", str(timeout_seconds)))

        self._session = None
        if HAS_REQUESTS:
            self._session = requests.Session()
            adapter = requests.adapters.HTTPAdapter(pool_connections=10, pool_maxsize=20, max_retries=0)
            self._session.mount("https://", adapter)
            self._session.mount("http://", adapter)

    def is_configured(self) -> bool:
        """Verifica si el cliente cuenta con API Key configurada."""
        return bool(self.api_key and not self.api_key.startswith("tu_clave_"))

    def post(self, primitive: str, payload: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], float]:
        """
        Ejecuta una llamada POST a la API de TypeSafe AI System-1.
        Devuelve (respuesta_json, latencia_en_ms).
        """
        start = time.perf_counter()
        if not self.is_configured():
            return None, (time.perf_counter() - start) * 1000.0

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "User-Agent": "MMAE-Agent-JevRouter/2.0"
        }
        url = f"{self.api_url}/{primitive}"

        try:
            if HAS_REQUESTS and self._session is not None:
                resp = self._session.post(
                    url,
                    json=payload,
                    headers=headers,
                    timeout=self.timeout_seconds
                )
                latency = (time.perf_counter() - start) * 1000.0
                if resp.status_code == 200:
                    return resp.json(), latency
                logger.warning(f"TypeSafe API devolvió status {resp.status_code}: {resp.text[:120]}")
                return None, latency
            else:
                data_bytes = json.dumps(payload).encode("utf-8")
                req = urllib.request.Request(url, data=data_bytes, headers=headers, method="POST")
                with urllib.request.urlopen(req, timeout=self.timeout_seconds) as response:
                    latency = (time.perf_counter() - start) * 1000.0
                    body = response.read().decode("utf-8")
                    return json.loads(body), latency
        except Exception as e:
            latency = (time.perf_counter() - start) * 1000.0
            logger.debug(f"Fallo en llamada a TypeSafe AI ({primitive}): {str(e)} ({latency:.1f}ms)")
            return None, latency


# =====================================================================
# Enrutador Cognitivo System-1 JEV (TypeSafe AI)
# =====================================================================

class JevRouter:
    """
    Enrutador System-1 'Jev' de TypeSafe AI.
    Evalúa intenciones, filtra seguridad crítica y clasifica rutas operativas
    con latencia garantizada inferior a 200 milisegundos.
    """

    # Patrones críticos para la heurística local de Noul (Seguridad)
    DANGEROUS_PATTERNS = [
        (r"\brm\s+-[rRfF]{1,3}\s+[/~]", "Borrado destructivo de raíz o directorio personal"),
        (r"\brmdir\s+/[sS]\s+/[qQ]\s+[a-zA-Z]:\\", "Destrucción recursiva de unidad de disco"),
        (r"\bformat\s+[a-zA-Z]:", "Comando de formateo de disco"),
        (r"\bdel\s+/[fF]\s+/[sS]\s+/[qQ]\s+[a-zA-Z]:\\Windows", "Borrado de archivos de sistema de Windows"),
        (r"\bcurl\b.*\|\s*(?:bash|sh|powershell|cmd)", "Ejecución de script remoto ciego mediante pipe"),
        (r"\b(?:wget|irm|iex)\b.*\|\s*(?:bash|powershell|iex)", "Descarga y ejecución remota no verificada"),
        (r":\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;\s*:", "Fork bomb detectada"),
        (r"\bcat\s+.*(?:\.env|id_rsa|id_ed25519)\b", "Intento de exfiltración de credenciales sensibles"),
        (r"\btype\s+.*(?:\.env|id_rsa)\b", "Lectura no autorizada de archivo de credenciales en terminal"),
    ]

    # Palabras clave de intención conversacional
    CONVERSATIONAL_KEYWORDS = {
        "hola", "buenos dias", "buenas tardes", "buenas noches", "hey", "saludos",
        "como estas", "que tal", "quien eres", "que eres", "gracias", "adios", "chao"
    }

    def __init__(
        self,
        api_key: Optional[str] = None,
        api_url: Optional[str] = None,
        timeout_seconds: float = 0.200,
        client: Optional[TypeSafeSystemOneClient] = None
    ):
        self.client = client or TypeSafeSystemOneClient(
            api_key=api_key,
            api_url=api_url,
            timeout_seconds=timeout_seconds
        )

    # -----------------------------------------------------------------
    # Primitiva 1: Choice (Clasificación / Selección Estructurada)
    # -----------------------------------------------------------------
    def choice(
        self,
        prompt: str,
        options: List[str],
        context: Optional[Dict[str, Any]] = None
    ) -> ChoiceResult:
        """
        Clasifica una intención o selecciona la siguiente herramienta/estrategia
        de una lista predefinida con distribución de probabilidad y confianza.
        """
        if not options:
            return ChoiceResult(selected="", confidence=0.0, probabilities={}, rationale="Lista de opciones vacía")

        start = time.perf_counter()
        payload = {
            "prompt": prompt,
            "options": options,
            "context": context or {}
        }

        # Intento de invocación a TypeSafe AI System-1
        api_data, api_latency = self.client.post("choice", payload)
        if api_data and isinstance(api_data, dict):
            selected = api_data.get("selected") or options[0]
            confidence = float(api_data.get("confidence", 0.9))
            probs = api_data.get("probabilities")
            if not isinstance(probs, dict):
                probs = {opt: (confidence if opt == selected else (1.0 - confidence) / max(1, len(options) - 1)) for opt in options}
            return ChoiceResult(
                selected=selected,
                confidence=confidence,
                probabilities=probs,
                rationale=api_data.get("rationale"),
                latency_ms=api_latency,
                source="typesafe_api"
            )

        # Fallback local determinista de ultra-alta velocidad (<1ms)
        local_result = self._local_choice_heuristic(prompt, options, context)
        latency = (time.perf_counter() - start) * 1000.0
        local_result.latency_ms = latency
        return local_result

    def _local_choice_heuristic(
        self,
        prompt: str,
        options: List[str],
        context: Optional[Dict[str, Any]] = None
    ) -> ChoiceResult:
        """Heurística local de elección System-1 para contingencia o modo offline."""
        prompt_clean = prompt.strip().lower()
        scores: Dict[str, float] = {opt: 0.1 for opt in options}

        # Detección de parada de emergencia
        if any(w in prompt_clean for w in ["detener", "parar", "cancela", "stop", "abortar"]):
            for opt in options:
                if "stop" in opt or "abort" in opt or "detener" in opt:
                    scores[opt] += 10.0

        # Detección de charla conversacional vs tarea operativa
        is_conv = any(prompt_clean.startswith(kw) or kw in prompt_clean.split() for kw in self.CONVERSATIONAL_KEYWORDS)
        if is_conv and len(prompt_clean.split()) <= 6:
            for opt in options:
                if "chat" in opt or "conversational" in opt or "direct" in opt:
                    scores[opt] += 5.0

        # Detección de tareas de archivos
        if any(w in prompt_clean for w in ["crear archivo", "escribir", "guardar", "editar", "patch", "leer archivo"]):
            for opt in options:
                if "file" in opt or "archivo" in opt or "filesystem" in opt:
                    scores[opt] += 4.0

        # Detección de terminal / comandos
        if any(w in prompt_clean for w in ["ejecutar", "terminal", "comando", "shell", "powershell", "instalar"]):
            for opt in options:
                if "terminal" in opt or "command" in opt or "execute" in opt:
                    scores[opt] += 4.0

        # Detección de navegación web / búsqueda
        if any(w in prompt_clean for w in ["buscar", "investigar", "google", "web", "internet"]):
            for opt in options:
                if "web" in opt or "search" in opt or "internet" in opt:
                    scores[opt] += 4.0

        # Normalización softmax / proporcional de probabilidades
        total_score = sum(scores.values())
        if total_score <= 0:
            total_score = 1.0
        probabilities = {opt: round(scores[opt] / total_score, 4) for opt in options}
        selected = max(probabilities, key=lambda k: probabilities[k])
        confidence = probabilities[selected]

        return ChoiceResult(
            selected=selected,
            confidence=confidence,
            probabilities=probabilities,
            rationale=f"Heurística local System-1: coincidencia ponderada para '{selected}'",
            latency_ms=0.0,
            source="local_heuristic"
        )

    # -----------------------------------------------------------------
    # Primitiva 2: Score (Evaluación Numérica de Métricas de Estado)
    # -----------------------------------------------------------------
    def score(
        self,
        prompt: str,
        metric: str = "risk",
        min_val: float = 0.0,
        max_val: float = 1.0,
        context: Optional[Dict[str, Any]] = None
    ) -> ScoreResult:
        """
        Evalúa numéricamente una métrica de estado (ej: nivel de riesgo,
        complejidad de tarea, o urgencia) en la escala especificada.
        """
        start = time.perf_counter()
        payload = {
            "prompt": prompt,
            "metric": metric,
            "min_val": min_val,
            "max_val": max_val,
            "context": context or {}
        }

        # Intento de invocación a TypeSafe AI System-1
        api_data, api_latency = self.client.post("score", payload)
        if api_data and isinstance(api_data, dict) and "score" in api_data:
            val = float(api_data["score"])
            clamped = max(min_val, min(max_val, val))
            return ScoreResult(
                score=clamped,
                confidence=float(api_data.get("confidence", 0.92)),
                metric=metric,
                rationale=api_data.get("rationale"),
                latency_ms=api_latency,
                source="typesafe_api"
            )

        # Fallback local determinista de ultra-alta velocidad
        local_result = self._local_score_heuristic(prompt, metric, min_val, max_val, context)
        latency = (time.perf_counter() - start) * 1000.0
        local_result.latency_ms = latency
        return local_result

    def _local_score_heuristic(
        self,
        prompt: str,
        metric: str,
        min_val: float,
        max_val: float,
        context: Optional[Dict[str, Any]] = None
    ) -> ScoreResult:
        """Heurística local para cálculo de riesgo o complejidad."""
        p_lower = prompt.lower()
        normalized_score = 0.2  # Base moderada

        if metric in ("risk", "peligro", "safety_risk"):
            # Evaluar indicadores de riesgo
            for pat, _ in self.DANGEROUS_PATTERNS:
                if re.search(pat, prompt, re.IGNORECASE):
                    normalized_score = 0.95
                    break
            if normalized_score < 0.9:
                if any(w in p_lower for w in ["delete", "remove", "drop", "truncate", "kill", "borrar", "eliminar"]):
                    normalized_score = 0.70
                elif any(w in p_lower for w in ["write", "modify", "patch", "modificar", "sobreescribir"]):
                    normalized_score = 0.45
                elif any(w in p_lower for w in ["read", "get", "status", "ls", "dir", "leer", "consultar"]):
                    normalized_score = 0.10

        elif metric in ("complexity", "complejidad"):
            # Evaluar complejidad por longitud, pasos requeridos y dependencias
            words = len(prompt.split())
            clauses = prompt.count(",") + prompt.count(";") + prompt.count(" y ") + prompt.count(" then ")
            if words < 6 and clauses == 0:
                normalized_score = 0.10  # Muy simple / conversacional
            elif words > 40 or clauses >= 3:
                normalized_score = 0.85  # Tarea multi-etapa compleja
            else:
                normalized_score = min(0.75, 0.25 + (words / 50.0) + (clauses * 0.12))

        else:
            normalized_score = 0.50

        # Escalar a [min_val, max_val]
        scaled = min_val + normalized_score * (max_val - min_val)
        return ScoreResult(
            score=round(scaled, 4),
            confidence=0.88,
            metric=metric,
            rationale=f"Heurística System-1 calculada ({metric}={scaled:.2f})",
            latency_ms=0.0,
            source="local_heuristic"
        )

    # -----------------------------------------------------------------
    # Primitiva 3: Noul (Filtro Binario Estricto de Seguridad)
    # -----------------------------------------------------------------
    def noul(
        self,
        prompt: str,
        check_type: str = "safety",
        context: Optional[Dict[str, Any]] = None
    ) -> NoulResult:
        """
        Filtro binario de seguridad (True/False) pre-ejecución.
        Bloquea de inmediato comandos destructivos o modificaciones de archivos críticos.
        """
        start = time.perf_counter()
        payload = {
            "prompt": prompt,
            "check_type": check_type,
            "context": context or {}
        }

        # Intento de invocación a TypeSafe AI System-1
        api_data, api_latency = self.client.post("noul", payload)
        if api_data and isinstance(api_data, dict) and "allowed" in api_data:
            return NoulResult(
                allowed=bool(api_data["allowed"]),
                confidence=float(api_data.get("confidence", 0.99)),
                violation_reason=api_data.get("violation_reason"),
                latency_ms=api_latency,
                source="typesafe_api"
            )

        # Fallback local determinista estricto (Zero-Tolerance)
        local_result = self._local_noul_heuristic(prompt, check_type, context)
        latency = (time.perf_counter() - start) * 1000.0
        local_result.latency_ms = latency
        return local_result

    def _local_noul_heuristic(
        self,
        prompt: str,
        check_type: str,
        context: Optional[Dict[str, Any]] = None
    ) -> NoulResult:
        """Heurística local de verificación binaria de seguridad."""
        # Comprobar lista de patrones peligrosos
        for pattern, reason in self.DANGEROUS_PATTERNS:
            if re.search(pattern, prompt, re.IGNORECASE):
                logger.warning(f"🚨 [Noul Security Block]: {reason} detectado en '{prompt[:80]}'")
                return NoulResult(
                    allowed=False,
                    confidence=0.99,
                    violation_reason=f"Violación de seguridad detectada: {reason}",
                    latency_ms=0.0,
                    source="local_heuristic"
                )

        # Bloquear intentos de escribir en archivos de sistema críticos protegidos
        if check_type in ("filesystem", "file_modification", "safety"):
            blocked_files = [".env", "id_rsa", "id_ed25519", "sam", "system32"]
            p_lower = prompt.lower()
            for bf in blocked_files:
                if re.search(rf"\b{re.escape(bf)}\b", p_lower) and any(w in p_lower for w in ["write", "delete", "rm", "overwrite", "truncate"]):
                    return NoulResult(
                        allowed=False,
                        confidence=0.98,
                        violation_reason=f"Modificación bloqueada sobre archivo o ruta crítica: '{bf}'",
                        latency_ms=0.0,
                        source="local_heuristic"
                    )

        return NoulResult(
            allowed=True,
            confidence=0.95,
            violation_reason=None,
            latency_ms=0.0,
            source="local_heuristic"
        )

    # -----------------------------------------------------------------
    # Optimización del Loop del Agente: Pre-Flight Check Completo
    # -----------------------------------------------------------------
    def pre_flight_check(
        self,
        user_goal_or_command: str,
        available_tools: Optional[List[str]] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> PreFlightDecision:
        """
        Orquesta las 3 primitivas (Noul, Score, Choice) en paralelo o secuencia rápida
        antes de decidir si se gasta inferencia pesada (LLM generativo) o si se resuelve
        de forma determinista o se bloquea.
        """
        start = time.perf_counter()

        # 1. Filtro Noul: Seguridad binaria de entrada
        safety = self.noul(user_goal_or_command, check_type="safety", context=context)
        if not safety.allowed:
            total_latency = (time.perf_counter() - start) * 1000.0
            return PreFlightDecision(
                action="blocked_security",
                safety=safety,
                complexity=ScoreResult(score=1.0, confidence=1.0, metric="risk", rationale="Bloqueado por Noul"),
                choice=ChoiceResult(selected="security_block", confidence=1.0, probabilities={"security_block": 1.0}),
                total_latency_ms=total_latency,
                direct_response=f"⛔ Acción bloqueada por seguridad System-1 (Jev Noul): {safety.violation_reason}"
            )

        # 2. Score: Evaluación de complejidad de la tarea
        complexity = self.score(user_goal_or_command, metric="complexity", context=context)

        # 3. Choice: Clasificación de intención estratégica
        routing_options = ["conversational_chat", "deterministic_tool", "heavy_llm_agent", "emergency_stop"]
        choice_res = self.choice(user_goal_or_command, options=routing_options, context=context)

        total_latency = (time.perf_counter() - start) * 1000.0

        # Determinación de acción óptima
        if choice_res.selected == "emergency_stop":
            return PreFlightDecision(
                action="blocked_security",
                safety=safety,
                complexity=complexity,
                choice=choice_res,
                total_latency_ms=total_latency,
                direct_response="⛔ PARADA DE EMERGENCIA solicitada por el usuario."
            )
        elif choice_res.selected == "conversational_chat" and complexity.score < 0.35:
            return PreFlightDecision(
                action="fast_deterministic",
                safety=safety,
                complexity=complexity,
                choice=choice_res,
                total_latency_ms=total_latency,
                direct_response="¡Hola! Soy JEV, tu asistente autónomo local. ¿En qué puedo ayudarte hoy?"
            )
        else:
            # Seleccionar herramienta recomendada si se pasaron herramientas
            rec_tool = None
            if available_tools:
                tool_choice = self.choice(user_goal_or_command, options=available_tools, context=context)
                rec_tool = tool_choice.selected

            return PreFlightDecision(
                action="proceed_llm",
                safety=safety,
                complexity=complexity,
                choice=choice_res,
                total_latency_ms=total_latency,
                recommended_tool=rec_tool
            )


# Instancia singleton predeterminada
default_jev_router = JevRouter()

__all__ = [
    "ChoiceResult",
    "ScoreResult",
    "NoulResult",
    "PreFlightDecision",
    "TypeSafeSystemOneClient",
    "JevRouter",
    "default_jev_router",
]
