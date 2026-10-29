"""
Pruebas Unitarias para el Enrutador de Modelos Gratuitos (FreeModelRouter)
Verifica:
1. Ordenación jerárquica de mayor a menor capacidad ("de la mejor a la menos mala").
2. Manejo de Rate Limit (HTTP 429) con cooldown temporal y conmutación automática.
3. Fallback y recuperación de estado en caché.
"""
import unittest
import time
from unittest.mock import patch, MagicMock

from jev.core.free_model_router import FreeModelRouter, FreeModelInfo
from jev.config import AgentConfig
from jev.core.llm_client import LocalLLMClient, LLMResponse


class TestFreeModelRouter(unittest.TestCase):

    def setUp(self):
        self.router = FreeModelRouter(api_key="mock-key")

    def test_default_ranking_order(self):
        """Verifica que los modelos de Tier 1 estén antes que los de Tier 2 y Tier 3."""
        candidates = self.router.get_ranked_candidates()
        self.assertGreater(len(candidates), 5)
        # Primer candidato debe ser de Tier 1 (Frontier/70B+)
        self.assertEqual(candidates[0].tier, 1)
        # El puntaje del primer modelo debe ser mayor o igual al siguiente
        self.assertGreaterEqual(candidates[0].quality_score, candidates[1].quality_score)

        # Validar que los tiers estén ordenados ascendentemente (1, luego 2, luego 3)
        tiers = [c.tier for c in candidates]
        self.assertEqual(tiers, sorted(tiers))

    def test_rate_limit_cooldown_and_failover(self):
        """Verifica que un modelo con 429 se mueva al final de la cola temporalmente."""
        candidates_before = self.router.get_ranked_candidates()
        best_model_id = candidates_before[0].id

        # Simular Rate Limit (429)
        self.router.report_rate_limit(best_model_id, cooldown_seconds=60)

        candidates_after = self.router.get_ranked_candidates()
        # El mejor modelo anterior ahora debe estar al final porque está en enfriamiento
        self.assertNotEqual(candidates_after[0].id, best_model_id)
        self.assertEqual(candidates_after[-1].id, best_model_id)
        self.assertTrue(candidates_after[-1].is_cooling_down)

    def test_report_success_resets_error_count(self):
        """Verifica que una llamada exitosa limpie contadores de error."""
        model_id = "meta-llama/llama-3.3-70b-instruct:free"
        initial_success = self.router.models[model_id].success_calls
        self.router.report_error(model_id)
        self.assertEqual(self.router.models[model_id].consecutive_errors, 1)

        self.router.report_success(model_id)
        self.assertEqual(self.router.models[model_id].consecutive_errors, 0)
        self.assertEqual(self.router.models[model_id].success_calls, initial_success + 1)

    def test_llm_client_free_cascade_failover(self):
        """Verifica que LocalLLMClient conmute al segundo modelo si el primero da 429."""
        config = AgentConfig(
            llm_provider="free_cascade",
            openrouter_api_key="test-key",
            use_free_model_cascade=True,
            llm_max_retries=1
        )
        client = LocalLLMClient(config=config)

        # Mock de httpx.Client.post: primera llamada 429, segunda llamada 200
        call_count = 0
        def mock_post(url, json=None, headers=None):
            nonlocal call_count
            call_count += 1
            resp = MagicMock()
            if call_count == 1:
                resp.status_code = 429
                resp.text = "Rate limit exceeded"
            else:
                resp.status_code = 200
                resp.json.return_value = {
                    "choices": [{"message": {"content": "Respuesta desde el segundo modelo"}}]
                }
            return resp

        with patch("httpx.Client.post", side_effect=mock_post):
            res = client.chat(messages=[{"role": "user", "content": "hola"}])
            self.assertEqual(res.content, "Respuesta desde el segundo modelo")
            self.assertGreaterEqual(call_count, 2)


if __name__ == "__main__":
    unittest.main()
