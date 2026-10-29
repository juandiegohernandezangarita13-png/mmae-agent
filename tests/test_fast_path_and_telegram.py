"""
Suite de Pruebas Automatizadas para la Interfaz Remota de Telegram y Enrutador Fast Path:
1. Gestor de Contactos y Normalización (ContactManager)
2. Despacho Modular de Mensajería (WhatsAppDispatcher)
3. Enrutador Determinista de Capa 1 (FastPathRouter: Comandos y Regex de Lenguaje Natural)
4. Interfaz y Seguridad de Telegram Bot (TelegramRemoteInterface: Filtro de ID, Concurrencia y Fallback)
"""
import unittest
from unittest.mock import MagicMock, AsyncMock, patch
from pathlib import Path
import tempfile
import asyncio
import shutil
import json
import os

from jev.core.fast_path import (
    FastPathRouter,
    FastPathResult,
    ContactManager,
    WhatsAppDispatcher,
    normalize_accents
)
from jev.interfaces.telegram_bot import TelegramRemoteInterface, MAX_MESSAGE_LENGTH


class TestContactManager(unittest.TestCase):
    """Pruebas del gestor de contactos JSON."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.contacts_file = Path(self.temp_dir) / "contacts.json"
        with open(self.contacts_file, "w", encoding="utf-8") as f:
            json.dump({
                "lider": "+521234567890",
                "admin": "+521987654321",
                "coordinación": "+521555555555"
            }, f)
        self.manager = ContactManager(contacts_path=self.contacts_file)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_get_phone_exact_and_case_insensitive(self):
        self.assertEqual(self.manager.get_phone("lider"), "+521234567890")
        self.assertEqual(self.manager.get_phone("LIDER"), "+521234567890")
        self.assertEqual(self.manager.get_phone("Admin"), "+521987654321")

    def test_get_phone_accent_tolerance(self):
        # "coordinacion" sin tilde debe coincidir con "coordinación"
        self.assertEqual(self.manager.get_phone("coordinacion"), "+521555555555")
        self.assertEqual(self.manager.get_phone("líder"), "+521234567890")

    def test_set_and_remove_contact(self):
        self.manager.set_contact("dev", "+34600000000")
        self.assertEqual(self.manager.get_phone("dev"), "+34600000000")

        # Verificar persistencia en disco
        with open(self.contacts_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.assertIn("dev", data)

        # Eliminar
        removed = self.manager.remove_contact("dev")
        self.assertTrue(removed)
        self.assertIsNone(self.manager.get_phone("dev"))


class TestWhatsAppDispatcher(unittest.TestCase):
    """Pruebas del despachador modular de WhatsApp."""

    def tearDown(self):
        WhatsAppDispatcher.set_custom_handler(None)

    def test_default_dispatch(self):
        res = WhatsAppDispatcher.dispatch("lider", "Alerta de prueba", "+521234567890")
        self.assertTrue(res.get("success"))
        self.assertIn("message_id", res)
        self.assertEqual(res.get("recipient"), "+521234567890")

    def test_custom_handler_injection(self):
        mock_handler = MagicMock(return_value={"success": True, "custom_sent": True, "message_id": "wa_custom_999"})
        WhatsAppDispatcher.set_custom_handler(mock_handler)

        res = WhatsAppDispatcher.dispatch("admin", "Mensaje con hook personalizado", "+521987654321")
        self.assertTrue(res.get("success"))
        self.assertTrue(res.get("custom_sent"))
        mock_handler.assert_called_once_with("admin", "Mensaje con hook personalizado", "+521987654321")


class TestFastPathRouter(unittest.TestCase):
    """Pruebas del enrutador determinista de capa 1."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.contacts_file = Path(self.temp_dir) / "contacts.json"
        with open(self.contacts_file, "w", encoding="utf-8") as f:
            json.dump({
                "lider": "+521234567890",
                "admin": "+521987654321"
            }, f)
        self.contact_mgr = ContactManager(contacts_path=self.contacts_file)
        self.router = FastPathRouter(contacts=self.contact_mgr)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_command_wa_known_contact(self):
        res = self.router.resolve("/wa lider Reporte completado")
        self.assertIsNotNone(res)
        self.assertEqual(res.action, "whatsapp_sent")
        self.assertIn("WhatsApp Despachado", res.response_text)
        self.assertIn("+521234567890", res.response_text)
        self.assertIn("Reporte completado", res.response_text)

    def test_command_wa_direct_phone_number(self):
        res = self.router.resolve("/wa +5215559998877 Hola directo")
        self.assertIsNotNone(res)
        self.assertEqual(res.action, "whatsapp_sent")
        self.assertIn("+5215559998877", res.response_text)

    def test_command_wa_unknown_contact(self):
        res = self.router.resolve("/wa desconocido Mensaje de prueba")
        self.assertIsNotNone(res)
        self.assertEqual(res.action, "whatsapp_error_not_found")
        self.assertIn("Contacto desconocido", res.response_text)
        self.assertIn("lider", res.response_text)

    def test_natural_language_whatsapp_regex(self):
        # 1. "envíale un mensaje a lider que diga Llego en 10 min"
        res1 = self.router.resolve("envíale un mensaje a lider que diga Llego en 10 min")
        self.assertIsNotNone(res1)
        self.assertEqual(res1.action, "whatsapp_sent")
        self.assertIn("Llego en 10 min", res1.response_text)

        # 2. "manda un whatsapp a admin diciendo Servidor reiniciado"
        res2 = self.router.resolve("manda un whatsapp a admin diciendo Servidor reiniciado")
        self.assertIsNotNone(res2)
        self.assertEqual(res2.action, "whatsapp_sent")
        self.assertIn("Servidor reiniciado", res2.response_text)

        # 3. "whatsapp a lider: Prueba directa"
        res3 = self.router.resolve("whatsapp a lider: Prueba directa")
        self.assertIsNotNone(res3)
        self.assertEqual(res3.action, "whatsapp_sent")
        self.assertIn("Prueba directa", res3.response_text)

    def test_command_status(self):
        mock_agent = MagicMock()
        mock_agent.is_running = False
        mock_agent.config.model_name = "gemini-3.8-flash"
        mock_agent.config.llm_provider = "gemini"

        res = self.router.resolve("/status", agent=mock_agent)
        self.assertIsNotNone(res)
        self.assertEqual(res.action, "status")
        self.assertIn("JEV Telemetría", res.response_text)
        self.assertIn("gemini-3.8-flash", res.response_text)

    def test_command_ping(self):
        res = self.router.resolve("/ping")
        self.assertIsNotNone(res)
        self.assertEqual(res.action, "ping")
        self.assertIn("PONG", res.response_text)

    def test_command_help(self):
        res = self.router.resolve("/help")
        self.assertIsNotNone(res)
        self.assertEqual(res.action, "help")
        self.assertIn("Fast Path", res.response_text)

    def test_command_contacts_and_addcontact(self):
        # Listar contactos
        res_list = self.router.resolve("/contacts")
        self.assertIsNotNone(res_list)
        self.assertIn("Lider", res_list.response_text)

        # Agregar contacto
        res_add = self.router.resolve("/addcontact dev +34123456789")
        self.assertIsNotNone(res_add)
        self.assertIn("Contacto guardado", res_add.response_text)
        self.assertEqual(self.contact_mgr.get_phone("dev"), "+34123456789")

    def test_command_stop(self):
        mock_agent = MagicMock()
        res = self.router.resolve("/stop", agent=mock_agent)
        self.assertIsNotNone(res)
        self.assertEqual(res.action, "stop_agent")
        self.assertTrue(res.should_stop_agent)
        mock_agent.stop.assert_called_once()

    def test_fallback_to_llm_on_complex_prompt(self):
        # Instrucciones complejas o abiertas deben devolver None (activando la Capa 2 LLM)
        complex_prompts = [
            "Escribe una función en Python para calcular números primos.",
            "Refactoriza el módulo de telemetría de radar.",
            "¿Cuál es la distancia entre la Tierra y Marte?",
            "Analiza el archivo workspace/reporte.csv y crea un resumen."
        ]
        for prompt in complex_prompts:
            res = self.router.resolve(prompt)
            self.assertIsNone(res, f"El prompt '{prompt}' debió retornar None para pasar al LLM")


class TestTelegramRemoteInterface(unittest.IsolatedAsyncioTestCase):
    """Pruebas de la interfaz de Telegram, seguridad y flujo unificado."""

    def setUp(self):
        self.allowed_id = 123456789
        self.mock_agent = MagicMock()
        self.mock_agent.run_task.return_value = "Resultado exitoso del agente autónomo."
        self.bot = TelegramRemoteInterface(
            token="MOCK_BOT_TOKEN_123456:ABC",
            allowed_user_id=self.allowed_id,
            agent=self.mock_agent
        )

    def test_authorization_filter(self):
        self.assertTrue(self.bot.is_authorized(123456789))
        self.assertFalse(self.bot.is_authorized(987654321))
        self.assertFalse(self.bot.is_authorized(None))

    def test_split_message(self):
        short_text = "Hola mundo"
        self.assertEqual(self.bot._split_message(short_text), ["Hola mundo"])

        # Texto extenso
        long_text = "\n".join([f"Línea de log número {i:04d}" for i in range(250)])
        chunks = self.bot._split_message(long_text, max_len=1000)
        self.assertGreater(len(chunks), 1)
        for chunk in chunks:
            self.assertLessEqual(len(chunk), 1000)

    async def test_unauthorized_user_message_silently_discarded(self):
        update = MagicMock()
        update.effective_user.id = 999999999  # No autorizado
        update.message.text = "/status"

        context = MagicMock()
        await self.bot.handle_unified_message(update, context)

        # No debe enviar ningún mensaje ni llamar al agente
        update.effective_chat.send_message.assert_not_called()
        self.mock_agent.run_task.assert_not_called()

    async def test_fast_path_bypasses_llm(self):
        update = MagicMock()
        update.effective_user.id = self.allowed_id
        update.effective_chat.id = 999
        update.effective_chat.send_message = AsyncMock()
        update.message.text = "/ping"

        context = MagicMock()
        await self.bot.handle_unified_message(update, context)

        # Debe responder inmediatamente
        update.effective_chat.send_message.assert_called_once()
        sent_text = update.effective_chat.send_message.call_args[0][0]
        self.assertIn("PONG", sent_text)

        # El agente LLM NO debe ser invocado
        self.mock_agent.run_task.assert_not_called()

    async def test_fallback_executes_agent_asynchronously(self):
        update = MagicMock()
        update.effective_user.id = self.allowed_id
        update.effective_chat.id = 999
        update.effective_chat.send_message = AsyncMock()
        update.message.text = "Crea un script para respaldar la base de datos"

        context = MagicMock()
        await self.bot.handle_unified_message(update, context)

        # El agente LLM DEBE ser invocado
        self.mock_agent.run_task.assert_called_once_with("Crea un script para respaldar la base de datos")

        # El mensaje final debe ser enviado a Telegram
        update.effective_chat.send_message.assert_called_once()
        sent_text = update.effective_chat.send_message.call_args[0][0]
        self.assertIn("Resultado exitoso del agente autónomo", sent_text)

    async def test_agent_exception_handled_gracefully(self):
        self.mock_agent.run_task.side_effect = RuntimeError("Fallo simulado en LLM")

        update = MagicMock()
        update.effective_user.id = self.allowed_id
        update.effective_chat.id = 999
        update.effective_chat.send_message = AsyncMock()
        update.message.text = "Haz una tarea que fallará"

        context = MagicMock()
        await self.bot.handle_unified_message(update, context)

        # No debe colapsar; debe enviar un mensaje de error claro
        update.effective_chat.send_message.assert_called_once()
        sent_text = update.effective_chat.send_message.call_args[0][0]
        self.assertIn("Error en la ejecución de JEV", sent_text)
        self.assertIn("Fallo simulado en LLM", sent_text)


if __name__ == "__main__":
    unittest.main()
