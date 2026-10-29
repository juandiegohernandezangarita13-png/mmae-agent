"""
Interfaz de Control Remoto de JEV vía Telegram Bot (Long Polling Asíncrono).
Implementa un enrutamiento de dos capas:
1. Fast Path: Bypass determinista de latencia cero (comandos directos y regex).
2. Fallback al Agente: Derivación asíncrona al motor cognitivo ReAct de JEV.
"""
from typing import Optional, List
import asyncio
import logging
import time
import os
import sys

# Asegurar carga de variables de entorno
from jev.config import BASE_DIR, AgentConfig, default_config
from jev.core.agent import AgentCore
from jev.core.fast_path import FastPathRouter, FastPathResult

# Telegram Bot SDK
try:
    from telegram import Update
    from telegram.constants import ParseMode, ChatAction
    from telegram.ext import (
        Application,
        ApplicationBuilder,
        CommandHandler,
        MessageHandler,
        ContextTypes,
        filters
    )
except ImportError:
    raise ImportError(
        "El paquete 'python-telegram-bot' no está instalado. "
        "Por favor ejecuta: pip install python-telegram-bot>=20.0"
    )

logger = logging.getLogger("jev.telegram_bot")
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

MAX_MESSAGE_LENGTH = 4000


class TelegramRemoteInterface:
    """Controlador principal de la interfaz Telegram de JEV."""

    def __init__(
        self,
        token: Optional[str] = None,
        allowed_user_id: Optional[int] = None,
        agent: Optional[AgentCore] = None,
        router: Optional[FastPathRouter] = None
    ):
        self.token = token or os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        
        # ID numérico de seguridad
        raw_user_id = allowed_user_id or os.getenv("ALLOWED_TELEGRAM_USER_ID", "0").strip()
        try:
            self.allowed_user_id = int(raw_user_id)
        except ValueError:
            self.allowed_user_id = 0

        # Enrutador Fast Path
        self.router = router or FastPathRouter()

        # Agente JEV Autónomo
        if agent:
            self.agent = agent
        else:
            self.agent = AgentCore(config=default_config)

        self.app: Optional[Application] = None

    def is_authorized(self, user_id: Optional[int]) -> bool:
        """Valida si el remitente coincide con el ID de usuario autorizado."""
        if user_id is None:
            return False
        if not self.allowed_user_id:
            # Recarga en caliente desde .env si aún no estaba configurado
            env_file = BASE_DIR / ".env"
            if env_file.exists():
                try:
                    with open(env_file, "r", encoding="utf-8") as f:
                        for line in f:
                            if line.strip().startswith("ALLOWED_TELEGRAM_USER_ID="):
                                val = line.split("=", 1)[1].strip()
                                if val.isdigit() and int(val) > 0:
                                    self.allowed_user_id = int(val)
                                    logger.info(f"🔑 [Recarga en Caliente]: ALLOWED_TELEGRAM_USER_ID={self.allowed_user_id} cargado desde .env.")
                                    break
                except Exception:
                    pass

        if not self.allowed_user_id:
            return False
        return user_id == self.allowed_user_id

    async def _send_safe_message(self, update: Update, text: str) -> None:
        """
        Envía mensajes a Telegram fragmentando si superan el límite de 4096 caracteres
        y con fallback automático a texto plano si falla el parseo de Markdown.
        """
        if not update.effective_chat:
            return

        chunks = self._split_message(text)
        for chunk in chunks:
            try:
                await update.effective_chat.send_message(
                    chunk,
                    parse_mode=ParseMode.MARKDOWN
                )
            except Exception:
                # Fallback a texto plano si Markdown contiene caracteres no escapados
                try:
                    await update.effective_chat.send_message(chunk)
                except Exception as e:
                    logger.error(f"Fallo crítico al enviar mensaje a Telegram: {e}")

    @staticmethod
    def _split_message(text: str, max_len: int = MAX_MESSAGE_LENGTH) -> List[str]:
        """Divide un texto extenso en bloques compatibles con Telegram."""
        if len(text) <= max_len:
            return [text]

        chunks = []
        lines = text.split("\n")
        current_chunk = ""

        for line in lines:
            if len(current_chunk) + len(line) + 1 <= max_len:
                current_chunk += (line + "\n")
            else:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                # Si una sola línea excede el tamaño máximo
                if len(line) > max_len:
                    for i in range(0, len(line), max_len):
                        chunks.append(line[i:i + max_len])
                    current_chunk = ""
                else:
                    current_chunk = line + "\n"

        if current_chunk.strip():
            chunks.append(current_chunk.strip())

        return chunks or [text[:max_len]]

    async def _keep_typing(self, chat_id: int, stop_event: asyncio.Event) -> None:
        """Mantiene activo el estado 'escribiendo...' en Telegram mientras el LLM razona."""
        while not stop_event.is_set():
            try:
                if self.app:
                    await self.app.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
            except Exception:
                pass
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=4.0)
            except asyncio.TimeoutError:
                continue

    async def handle_unified_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Handler central y unificado para todo mensaje entrante:
        1. Filtro de seguridad por ALLOWED_TELEGRAM_USER_ID.
        2. Capa 1: Evaluación Fast Path (0 tokens, microsegundos).
        3. Capa 2: Fallback al Agente JEV con ejecución asíncrona en hilo no bloqueante.
        """
        if not update.effective_user or not update.message or not update.message.text:
            return

        user_id = update.effective_user.id
        raw_text = update.message.text.strip()

        # -----------------------------------------------------
        # 1. FILTRO DE SEGURIDAD
        # -----------------------------------------------------
        if not self.allowed_user_id:
            welcome_msg = (
                f"👋 ¡Hola @{update.effective_user.username or 'Usuario'}!\n\n"
                f"El bot *Polvora* está activo pero aún no tiene un dueño configurado en `.env`.\n\n"
                f"🔑 **Tu Telegram User ID es**: `{user_id}`\n\n"
                f"Añádelo a tu archivo `.env` en la laptop para desbloquear el control total:\n"
                f"`ALLOWED_TELEGRAM_USER_ID={user_id}`"
            )
            await self._send_safe_message(update, welcome_msg)
            logger.info(f"Aviso de configuración enviado a {user_id} (@{update.effective_user.username}).")
            return

        if not self.is_authorized(user_id):
            logger.warning(
                f"[Seguridad]: Mensaje descartado silenciosamente. "
                f"Usuario no autorizado: {user_id} (@{update.effective_user.username})"
            )
            return

        # -----------------------------------------------------
        # 2. CAPA 1: FAST PATH (Bypass Determinista / 0 Tokens)
        # -----------------------------------------------------
        fast_result: Optional[FastPathResult] = self.router.resolve(raw_text, agent=self.agent)
        if fast_result is not None:
            logger.info(f"⚡ [Fast Path Activado]: Acción '{fast_result.action}' resuelta sin invocar LLM.")
            await self._send_safe_message(update, fast_result.response_text)
            return

        # -----------------------------------------------------
        # 3. CAPA 2: FALLBACK AL AGENTE (Ruta LLM / ReAct Loop)
        # -----------------------------------------------------
        logger.info(f"🧠 [Ruta LLM]: Mensaje '{raw_text[:40]}...' derivado al bucle autónomo del agente.")
        
        # Iniciar indicador visual de escritura (typing)
        stop_typing = asyncio.Event()
        typing_task = asyncio.create_task(self._keep_typing(update.effective_chat.id, stop_typing))

        try:
            # Ejecutar el bucle del agente en un thread para NO congelar el event loop de Telegram
            start_time = time.time()
            agent_output = await asyncio.to_thread(self.agent.run_task, raw_text)
            elapsed = time.time() - start_time

            footer = f"\n\n⏱️ _[JEV Agente completado en {elapsed:.1f}s]_"
            full_response = str(agent_output) + footer
            await self._send_safe_message(update, full_response)

        except Exception as exc:
            logger.error(f"Error durante la ejecución del agente vía Telegram: {exc}", exc_info=True)
            error_response = (
                f"❌ *Error en la ejecución de JEV*:\n"
                f"```\n{str(exc)}\n```\n"
                f"El entorno del agente sigue operativo. Puedes enviar una nueva instrucción o consultar `/status`."
            )
            await self._send_safe_message(update, error_response)

        finally:
            stop_typing.set()
            await typing_task

    def build_application(self) -> Application:
        """Construye y configura la aplicación de Telegram con sus handlers."""
        if not self.token:
            raise ValueError(
                "Falta TELEGRAM_BOT_TOKEN. Configúralo en el archivo .env o pásalo al constructor."
            )
        if not self.allowed_user_id:
            logger.warning(
                "ALLOWED_TELEGRAM_USER_ID no está configurado o es 0. "
                "El bot descartará todos los mensajes por seguridad hasta configurarlo en .env."
            )

        self.app = ApplicationBuilder().token(self.token).build()

        # Handler unificado: captura tanto comandos como mensajes de texto
        self.app.add_handler(
            MessageHandler(filters.TEXT & (~filters.COMMAND), self.handle_unified_message)
        )
        self.app.add_handler(
            MessageHandler(filters.COMMAND, self.handle_unified_message)
        )

        return self.app

    def run(self) -> None:
        """Inicia el bot en modo Long Polling sin exponer puertos públicos."""
        app = self.build_application()
        logger.info(
            f"🚀 [JEV Telegram Remote]: Iniciando Long Polling (Usuario autorizado: {self.allowed_user_id})..."
        )
        app.run_polling(drop_pending_updates=True)


def run_bot() -> None:
    """Función de arranque por consola."""
    bot = TelegramRemoteInterface()
    bot.run()


if __name__ == "__main__":
    run_bot()
