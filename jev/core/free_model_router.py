"""
Gestor y Enrutador Inteligente de Modelos Gratuitos (Free Model Cascade Router).
Implementa una cascada de modelos LLM ordenados de mayor a menor capacidad ("de la mejor a la menos mala")
aprovechando OpenRouter Free Tier, endpoints libres y fallback local.
Gestiona automáticamente el enfriamiento (cooldown) por rate-limiting (429) y conmutación por error (failover) transparente.
"""
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from pathlib import Path
import logging
import json
import time
import httpx
import os

from jev.config import BASE_DIR

logger = logging.getLogger("jev.free_model_router")

CACHE_FILE = BASE_DIR / "data" / "memory" / "free_models_cache.json"


@dataclass
class FreeModelInfo:
    id: str
    name: str
    tier: int  # 1: Frontier / 70B+ (Top Reasoning), 2: 24B-32B Coder, 3: 8B Fast, 4: Local
    quality_score: float
    context_length: int = 32768
    cooldown_until: float = 0.0
    consecutive_errors: int = 0
    total_calls: int = 0
    success_calls: int = 0

    @property
    def is_cooling_down(self) -> bool:
        return time.time() < self.cooldown_until


class FreeModelRouter:
    """
    Enrutador jerárquico de modelos gratuitos.
    Prueba los modelos en orden estricto de capacidad cognitiva y programación.
    Si un modelo devuelve HTTP 429 (límite de peticiones) o HTTP 503,
    lo pone en cooldown temporal y conmuta en milisegundos al siguiente mejor modelo.
    """

    DEFAULT_RANKED_MODELS: List[Dict[str, Any]] = [
        # Tier 1: Máximo razonamiento y capacidades avanzadas de código (70B+ / Frontier)
        {
            "id": "meta-llama/llama-3.3-70b-instruct:free",
            "name": "Llama 3.3 70B Instruct (Free)",
            "tier": 1,
            "quality_score": 98.0,
            "context_length": 131072
        },
        {
            "id": "google/gemini-2.0-flash-exp:free",
            "name": "Gemini 2.0 Flash Exp (Free)",
            "tier": 1,
            "quality_score": 97.0,
            "context_length": 1048576
        },
        {
            "id": "deepseek/deepseek-r1:free",
            "name": "DeepSeek R1 Reasoning (Free)",
            "tier": 1,
            "quality_score": 96.0,
            "context_length": 65536
        },
        {
            "id": "deepseek/deepseek-chat:free",
            "name": "DeepSeek V3 671B (Free)",
            "tier": 1,
            "quality_score": 95.0,
            "context_length": 65536
        },
        # Tier 2: Especialistas de programación y razonamiento medio (24B - 32B)
        {
            "id": "qwen/qwen-2.5-coder-32b-instruct:free",
            "name": "Qwen 2.5 Coder 32B Instruct (Free)",
            "tier": 2,
            "quality_score": 93.0,
            "context_length": 32768
        },
        {
            "id": "mistralai/mistral-small-24b-instruct-2501:free",
            "name": "Mistral Small 24B Instruct (Free)",
            "tier": 2,
            "quality_score": 90.0,
            "context_length": 32768
        },
        # Tier 3: Modelos rápidos y ligeros (8B - 9B) + Meta-Router OpenRouter
        {
            "id": "google/gemma-2-9b-it:free",
            "name": "Gemma 2 9B IT (Free)",
            "tier": 3,
            "quality_score": 83.0,
            "context_length": 8192
        },
        {
            "id": "meta-llama/llama-3.1-8b-instruct:free",
            "name": "Llama 3.1 8B Instruct (Free)",
            "tier": 3,
            "quality_score": 81.0,
            "context_length": 131072
        },
        {
            "id": "openrouter/free",
            "name": "OpenRouter Auto-Free Meta Router",
            "tier": 3,
            "quality_score": 75.0,
            "context_length": 32768
        }
    ]

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = "https://openrouter.ai/api/v1",
        fcc_base_url: str = "http://127.0.0.1:8082"
    ):
        self.api_key = api_key or os.getenv("OPENROUTER_API_KEY", "").strip()
        self.base_url = base_url.rstrip("/")
        self.fcc_base_url = fcc_base_url.rstrip("/")
        self.models: Dict[str, FreeModelInfo] = {}
        self._init_models()

    def _init_models(self) -> None:
        """Inicializa los modelos desde la lista por defecto y el caché persistente si existe."""
        for m in self.DEFAULT_RANKED_MODELS:
            self.models[m["id"]] = FreeModelInfo(
                id=m["id"],
                name=m["name"],
                tier=m["tier"],
                quality_score=m["quality_score"],
                context_length=m.get("context_length", 32768)
            )

        # Cargar métricas de caché si existen
        if CACHE_FILE.exists():
            try:
                with open(CACHE_FILE, "r", encoding="utf-8") as f:
                    cached_data = json.load(f)
                    for item in cached_data:
                        mid = item.get("id")
                        if mid in self.models:
                            self.models[mid].success_calls = item.get("success_calls", 0)
                            self.models[mid].total_calls = item.get("total_calls", 0)
            except Exception as e:
                logger.debug(f"No se pudo cargar caché de modelos gratuitos: {e}")

    def save_cache(self) -> None:
        """Persiste el estado y rendimiento de los modelos."""
        try:
            CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
            serializable = [
                {
                    "id": m.id,
                    "name": m.name,
                    "tier": m.tier,
                    "quality_score": m.quality_score,
                    "success_calls": m.success_calls,
                    "total_calls": m.total_calls
                }
                for m in self.models.values()
            ]
            with open(CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump(serializable, f, indent=2)
        except Exception as e:
            logger.debug(f"Error guardando caché de modelos: {e}")

    def get_ranked_candidates(self) -> List[FreeModelInfo]:
        """
        Retorna la lista de modelos ordenada de mayor a menor calidad ("de la mejor a la menos mala").
        Los modelos actualmente en cooldown se colocan al final.
        """
        now = time.time()
        active = []
        cooling = []

        for m in self.models.values():
            if m.cooldown_until > now:
                cooling.append(m)
            else:
                active.append(m)

        # Ordenar primero por tier (1 antes que 2), luego por quality_score descendente
        active.sort(key=lambda x: (x.tier, -x.quality_score))
        cooling.sort(key=lambda x: x.cooldown_until)

        return active + cooling

    def report_rate_limit(self, model_id: str, cooldown_seconds: int = 60) -> None:
        """Marca un modelo como saturado/rate-limited y le asigna un tiempo de enfriamiento."""
        if model_id in self.models:
            m = self.models[model_id]
            m.cooldown_until = time.time() + cooldown_seconds
            m.consecutive_errors += 1
            m.total_calls += 1
            logger.warning(
                f"⏳ [Rate Limit / 429] Modelo '{m.name}' en enfriamiento por {cooldown_seconds}s. "
                "Conmutando automáticamente al siguiente modelo de la lista..."
            )

    def report_error(self, model_id: str) -> None:
        """Registra un error transitorio o indisponibilidad en un modelo."""
        if model_id in self.models:
            m = self.models[model_id]
            m.consecutive_errors += 1
            m.total_calls += 1
            # Si acumula 2 errores seguidos, dar un breve cooldown de 30 segundos
            if m.consecutive_errors >= 2:
                m.cooldown_until = time.time() + 30
                logger.info(f"Modelo '{m.name}' acumuló fallos. Enfriamiento temporal por 30s.")

    def report_success(self, model_id: str) -> None:
        """Registra una llamada exitosa y reinicia contadores de error."""
        if model_id in self.models:
            m = self.models[model_id]
            m.consecutive_errors = 0
            m.cooldown_until = 0.0
            m.success_calls += 1
            m.total_calls += 1
            self.save_cache()

    def fetch_live_models_from_openrouter(self) -> int:
        """
        Consulta la API de OpenRouter de forma dinámica para descubrir nuevos modelos gratuitos (:free)
        y añadirlos al catálogo ordenados según tamaño de contexto y arquitectura.
        """
        url = f"{self.base_url}/models"
        headers = {"User-Agent": "JEV-Agent/2.0"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        try:
            with httpx.Client(timeout=10.0) as client:
                res = client.get(url, headers=headers)
            if res.status_code == 200:
                data = res.json().get("data", [])
                added_count = 0
                for item in data:
                    mid = item.get("id", "")
                    pricing = item.get("pricing", {})
                    # Verificar si es gratuito (:free en id o pricing 0)
                    is_free = mid.endswith(":free") or (
                        str(pricing.get("prompt", "")) == "0" and str(pricing.get("completion", "")) == "0"
                    )
                    if is_free and mid not in self.models:
                        name = item.get("name", mid)
                        context = item.get("context_length", 32768)
                        # Heurística de score según tamaño y proveedor
                        score = 80.0
                        tier = 3
                        mid_lower = mid.lower()
                        if "70b" in mid_lower or "r1" in mid_lower or "gemini" in mid_lower or "v3" in mid_lower:
                            tier = 1
                            score = 95.0
                        elif "coder" in mid_lower or "32b" in mid_lower or "24b" in mid_lower:
                            tier = 2
                            score = 90.0

                        self.models[mid] = FreeModelInfo(
                            id=mid,
                            name=f"{name} (Free)",
                            tier=tier,
                            quality_score=score,
                            context_length=context
                        )
                        added_count += 1
                if added_count > 0:
                    logger.info(f"Descubiertos {added_count} nuevos modelos gratuitos dinámicamente de OpenRouter.")
                    self.save_cache()
                return added_count
        except Exception as e:
            logger.debug(f"Error consultando modelos dinámicos de OpenRouter: {e}")
        return 0
