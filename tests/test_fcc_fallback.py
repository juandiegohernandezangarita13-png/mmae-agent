import unittest
from unittest.mock import patch, MagicMock
from config import AgentConfig
from jev.core.llm_client import LocalLLMClient, LLMResponse
from jev.core.claude_code_bridge import ClaudeCodeResponse

class TestFCCFallback(unittest.TestCase):
    def setUp(self):
        self.config = AgentConfig(
            llm_provider="gemini",
            gemini_api_key="mock_gemini_key",
            enable_fcc_fallback=True,
            fcc_model="open_router/meta-llama/llama-3.3-70b-instruct:free"
        )
        self.client = LocalLLMClient(config=self.config)

    @patch("jev.core.claude_code_bridge.ClaudeCodeBridge.send_message")
    @patch("httpx.Client.post")
    def test_fallback_to_fcc_when_gemini_fails(self, mock_http_post, mock_bridge_send):
        # Simular que todas las llamadas de Gemini dan Rate Limit 429
        mock_gemini_resp = MagicMock()
        mock_gemini_resp.status_code = 429
        mock_gemini_resp.text = '{"error": {"code": 429, "message": "Resource exhausted", "details": [{"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "10s"}]}}'
        mock_http_post.return_value = mock_gemini_resp

        # Simular que ClaudeCodeBridge (FCC) responde con éxito
        mock_bridge_send.return_value = ClaudeCodeResponse(
            content="Respuesta exitosa desde Free-Claude-Code (Llama 3.3 70B)",
            tool_calls=[],
            is_success=True,
            raw_response={"status": "ok"}
        )

        messages = [{"role": "user", "content": "Hola mundo"}]
        resp = self.client.chat(messages=messages)

        self.assertIsInstance(resp, LLMResponse)
        self.assertEqual(resp.content, "Respuesta exitosa desde Free-Claude-Code (Llama 3.3 70B)")
        self.assertTrue(mock_bridge_send.called)

if __name__ == "__main__":
    unittest.main()
