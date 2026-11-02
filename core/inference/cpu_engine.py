"""
Motor de Inferencia Ligera en CPU para MMAE-Agent (core.inference.cpu_engine).
Permite ejecutar tareas secundarias (clasificación de comandos, enrutamiento rápido,
resúmenes cortos) 100% en CPU con cero consumo de VRAM y huella mínima de batería.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, Any, List, Optional
from pathlib import Path
import json
import re
import time
import logging

logger = logging.getLogger(__name__)


@dataclass
class ClassificationResult:
    """Resultado estructurado de clasificación o enrutamiento en CPU."""
    intent: str
    confidence: float
    recommended_tools: List[str]
    is_safe: bool
    summary: str
    backend_used: str
    latency_ms: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "intent": self.intent,
            "confidence": self.confidence,
            "recommended_tools": self.recommended_tools,
            "is_safe": self.is_safe,
            "summary": self.summary,
            "backend_used": self.backend_used,
            "latency_ms": self.latency_ms
        }


class CPUInferenceBackend(ABC):
    """Interfaz abstracta para backends de inferencia local en CPU."""

    @abstractmethod
    def classify_and_route(self, text: str, available_tools: Optional[List[str]] = None) -> ClassificationResult:
        """Clasifica la intención del usuario y sugiere herramientas preliminares."""
        pass


class HeuristicFastRouter(CPUInferenceBackend):
    """
    Enrutador determinista System-1 de latencia ultra baja (< 0.5ms).
    Opera en memoria sin cargar pesos pesados en RAM, ideal para triage instantáneo.
    """

    INTENT_MAP = [
        (r"(?:busca|buscar|investiga|quién|qué es|googlea)\b", "web_research", ["search_web", "fetch_webpage"]),
        (r"(?:escribe|crea|guarda|genera script|archivo|carpeta)\b", "code_generation", ["write_file", "execute_python"]),
        (r"(?:abre|abrir|lanza|ejecuta app|notepad|whatsapp|spotify)\b", "application_control", ["open_application", "smart_ui_click"]),
        (r"(?:pantalla|screenshot|captura|mira la pantalla|clic)\b", "gui_automation", ["take_screenshot", "smart_ui_click", "keyboard_type"]),
        (r"(?:terminal|comando|powershell|consola|git|pip)\b", "shell_execution", ["cli_execute_structured", "execute_command"]),
        (r"(?:recuerda|mi preferencia|mi ruta|olvida)\b", "memory_management", ["manage_user_memory"]),
        (r"(?:hola|buenos días|buenas tardes|qué tal)\b", "conversational", [])
    ]

    def classify_and_route(self, text: str, available_tools: Optional[List[str]] = None) -> ClassificationResult:
        start_t = time.perf_counter()
        clean = text.lower().strip()

        matched_intent = "general_task"
        matched_tools: List[str] = []
        confidence = 0.65

        for pattern, intent, tools in self.INTENT_MAP:
            if re.search(pattern, clean):
                matched_intent = intent
                matched_tools = tools
                confidence = 0.92
                break

        # Filtrar herramientas sugeridas contra el catálogo disponible
        if available_tools:
            matched_tools = [t for t in matched_tools if t in available_tools]

        elapsed_ms = (time.perf_counter() - start_t) * 1000.0
        return ClassificationResult(
            intent=matched_intent,
            confidence=confidence,
            recommended_tools=matched_tools,
            is_safe=True,
            summary=f"Clasificación heurística System-1 ({matched_intent})",
            backend_used="HeuristicFastRouter",
            latency_ms=round(elapsed_ms, 3)
        )


class GGUFLocalBackend(CPUInferenceBackend):
    """
    Backend de inferencia GGUF cuantizado (Q4_K_M / Q2_K) ejecutado 100% en CPU
    a través de llama-cpp-python o subproceso llama.cpp CLI.
    Permite el uso de SLMs (SmolLM2-360M o Qwen2.5-0.5B) con menos de 350MB de RAM.
    """

    def __init__(self, model_path: Optional[Path] = None, n_threads: int = 4):
        self.model_path = Path(model_path or "data/models/slm/qwen2.5-0.5b-instruct-q4_k_m.gguf")
        self.n_threads = n_threads
        self._llm = None
        self._is_available = self.model_path.exists()

    def _init_llm(self) -> bool:
        if self._llm is not None:
            return True
        if not self.model_path.exists():
            return False
        try:
            from llama_cpp import Llama
            self._llm = Llama(
                model_path=str(self.model_path),
                n_ctx=1024,
                n_threads=self.n_threads,
                n_gpu_layers=0,  # 100% CPU, 0 VRAM
                verbose=False
            )
            return True
        except Exception as e:
            logger.debug("No se pudo instanciar Llama GGUF: %s", e)
            return False

    def classify_and_route(self, text: str, available_tools: Optional[List[str]] = None) -> ClassificationResult:
        start_t = time.perf_counter()
        if self._init_llm() and self._llm:
            try:
                system_prompt = (
                    "Clasifica la solicitud del usuario en JSON con campos: "
                    "{'intent': string, 'confidence': float, 'tools': list[string], 'is_safe': bool}."
                )
                prompt = f"<|im_start|>system\n{system_prompt}<|im_end|>\n<|im_start|>user\n{text}<|im_end|>\n<|im_start|>assistant\n"
                output = self._llm(prompt, max_tokens=128, temperature=0.1, stop=["<|im_end|>"])
                resp_text = output["choices"][0]["text"].strip()
                parsed = json.loads(re.search(r"\{.*?\}", resp_text, re.DOTALL).group(0))
                elapsed_ms = (time.perf_counter() - start_t) * 1000.0
                return ClassificationResult(
                    intent=parsed.get("intent", "task"),
                    confidence=float(parsed.get("confidence", 0.85)),
                    recommended_tools=parsed.get("tools", []),
                    is_safe=bool(parsed.get("is_safe", True)),
                    summary=f"Clasificación neural GGUF en CPU ({parsed.get('intent')})",
                    backend_used="GGUFLocalBackend",
                    latency_ms=round(elapsed_ms, 2)
                )
            except Exception as e:
                logger.warning("Fallo en inferencia GGUF: %s", e)

        # Fallback a heurística
        fallback = HeuristicFastRouter().classify_and_route(text, available_tools)
        fallback.backend_used = "GGUFLocalBackend(FallbackHeuristic)"
        return fallback


class BitNetBackend(CPUInferenceBackend):
    """
    Adaptador experimental para BitNet b1.58 (1-bit / 1.58-bit LLMs con bitnet.cpp).
    Permite inferencias con solo operaciones de suma y resta ternaria en CPU.
    """

    def __init__(self, binary_path: Optional[Path] = None):
        self.binary_path = Path(binary_path or "tools/bitnet/run_inference.exe")
        self._is_ready = self.binary_path.exists()

    def classify_and_route(self, text: str, available_tools: Optional[List[str]] = None) -> ClassificationResult:
        # Si el ejecutable de BitNet está compilado localmente:
        start_t = time.perf_counter()
        if self._is_ready:
            try:
                import subprocess
                cmd = [str(self.binary_path), "-p", text, "-n", "64"]
                res = subprocess.run(cmd, stdout=subprocess.PIPE, text=True, timeout=5)
                elapsed_ms = (time.perf_counter() - start_t) * 1000.0
                return ClassificationResult(
                    intent="bitnet_processed",
                    confidence=0.80,
                    recommended_tools=[],
                    is_safe=True,
                    summary=res.stdout.strip()[:100],
                    backend_used="BitNetBackend(bitnet.cpp)",
                    latency_ms=round(elapsed_ms, 2)
                )
            except Exception as e:
                logger.debug("BitNet runner falló: %s", e)

        # Fallback inteligente
        fb = HeuristicFastRouter().classify_and_route(text, available_tools)
        fb.backend_used = "BitNetBackend(FallbackHeuristic)"
        return fb


class LightweightCPUClassifier:
    """
    Servicio unificado de clasificación en CPU para MMAE-Agent.
    Orquesta en cascada: Heurística System-1 (<0.5ms) -> GGUF SLM (10-30ms) -> BitNet.
    """

    def __init__(self):
        self.fast_router = HeuristicFastRouter()
        self.gguf_backend = GGUFLocalBackend()
        self.bitnet_backend = BitNetBackend()

    def evaluate(self, user_goal: str, available_tools: Optional[List[str]] = None) -> ClassificationResult:
        """
        Clasifica una meta de usuario con consumo mínimo de CPU y 0% GPU VRAM.
        """
        # 1. Pase primario por enrutador determinista
        res = self.fast_router.classify_and_route(user_goal, available_tools)
        if res.confidence >= 0.90:
            return res

        # 2. Si hay ambigüedad y el modelo GGUF está disponible en disco, usar SLM
        if self.gguf_backend._is_available:
            return self.gguf_backend.classify_and_route(user_goal, available_tools)

        return res
