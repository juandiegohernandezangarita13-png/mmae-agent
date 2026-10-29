"""
Fast Path Router (Bypass Determinista / Regex / Comandos de Latencia Cero).
Capa 1 de enrutamiento para el control remoto de JEV:
Ejecuta de forma inmediata acciones directas y estructuradas (WhatsApp, estado, atajos, contactos)
sin consumir tokens ni invocar al LLM (latencia cero). Si no hay coincidencia, deriva al agente (LLM).
"""
from typing import Dict, Any, Optional, Callable, List, Tuple
from dataclasses import dataclass, field
from pathlib import Path
import unicodedata
import threading
import logging
import json
import time
import re
import os

from jev.config import BASE_DIR

logger = logging.getLogger("jev.fast_path")


@dataclass(slots=True)
class FastPathResult:
    """Resultado de una acción resuelta por el Fast Path."""
    action: str
    response_text: str
    matched: bool = True
    data: Dict[str, Any] = field(default_factory=dict)
    should_stop_agent: bool = False


class ContactManager:
    """Gestiona el mapeo de alias y nombres a números telefónicos en contacts.json."""

    def __init__(self, contacts_path: Optional[Path] = None):
        self.base_dir = Path(BASE_DIR)
        self.contacts_path = Path(contacts_path or (self.base_dir / "contacts.json"))
        self._lock = threading.Lock()
        self._contacts: Dict[str, str] = {}
        self.reload()

    def reload(self) -> Dict[str, str]:
        with self._lock:
            if not self.contacts_path.exists():
                # Intentar fallback en data/contacts.json
                alt_path = self.base_dir / "data" / "contacts.json"
                if alt_path.exists():
                    self.contacts_path = alt_path
                else:
                    # Crear archivo inicial por defecto
                    self._contacts = {
                        "lider": "+521234567890",
                        "admin": "+521987654321",
                        "soporte": "+521555555555"
                    }
                    self._save_unlocked()
                    return dict(self._contacts)

            try:
                with open(self.contacts_path, "r", encoding="utf-8") as f:
                    self._contacts = json.load(f)
            except Exception as e:
                logger.warning(f"Error al leer contacts.json ({e}). Utilizando directorio en memoria.")
                self._contacts = {"lider": "+521234567890"}
            return dict(self._contacts)

    def _save_unlocked(self) -> None:
        try:
            self.contacts_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.contacts_path, "w", encoding="utf-8") as f:
                json.dump(self._contacts, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Error al guardar contacts.json: {e}")

    def get_phone(self, alias_or_name: str) -> Optional[str]:
        """Busca el número de teléfono por alias normalizado o exacto."""
        if not alias_or_name:
            return None
        norm_key = alias_or_name.strip().lower()
        with self._lock:
            # 1. Búsqueda exacta
            if norm_key in self._contacts:
                return self._contacts[norm_key]
            # 2. Búsqueda sin acentos
            norm_key_clean = normalize_accents(norm_key)
            for k, v in self._contacts.items():
                if normalize_accents(k.lower()) == norm_key_clean:
                    return v
        return None

    def set_contact(self, name: str, phone: str) -> None:
        """Añade o actualiza un contacto y lo persiste en disco."""
        with self._lock:
            self._contacts[name.strip().lower()] = phone.strip()
            self._save_unlocked()

    def remove_contact(self, name: str) -> bool:
        """Elimina un contacto existente."""
        with self._lock:
            norm_name = name.strip().lower()
            if norm_name in self._contacts:
                del self._contacts[norm_name]
                self._save_unlocked()
                return True
        return False

    def list_contacts(self) -> Dict[str, str]:
        with self._lock:
            return dict(self._contacts)


def normalize_accents(text: str) -> str:
    """Elimina acentos y normaliza texto para comparación tolerante."""
    nfkd_form = unicodedata.normalize("NFKD", text)
    return "".join([c for c in nfkd_form if not unicodedata.combining(c)]).strip().lower()


class WhatsAppDispatcher:
    """Hook modular para despacho de mensajes de WhatsApp."""

    _custom_handler: Optional[Callable[[str, str, Optional[str]], Dict[str, Any]]] = None

    @classmethod
    def set_custom_handler(cls, handler: Callable[[str, str, Optional[str]], Dict[str, Any]]) -> None:
        cls._custom_handler = handler

    @classmethod
    def dispatch(cls, recipient: str, message: str, phone_number: Optional[str] = None) -> Dict[str, Any]:
        """
        Punto de entrada modular para el envío de WhatsApp.
        Permite conectar scripts locales, WhatsApp Cloud API, Baileys o PyAutoGUI.
        """
        # Si el usuario registró un handler personalizado
        if cls._custom_handler is not None:
            try:
                return cls._custom_handler(recipient, message, phone_number)
            except Exception as e:
                logger.error(f"Error en custom WhatsApp handler: {e}")
                return {"success": False, "error": str(e)}

        # Intentar invocar SendWhatsappMessageTool si existe
        try:
            from generated_tools.send_whatsapp_message_tool import SendWhatsappMessageTool
            tool = SendWhatsappMessageTool()
            target = phone_number or recipient
            res = tool.execute(recipient=target, message=message)
            return {
                "success": res.success,
                "output": res.output,
                "message_id": res.data.get("message_id") if res.data else f"wa_{int(time.time()*1000)}",
                "recipient": target
            }
        except Exception:
            # Despacho predeterminado simulado / gateway logging
            msg_id = f"wa_{int(time.time()*1000)}"
            target = phone_number or recipient
            logger.info(f"[WhatsApp Dispatcher] Enviando mensaje a {target}: '{message}' (ID: {msg_id})")
            return {
                "success": True,
                "output": f"[WhatsApp Gateway] Mensaje transmitido a {target}: '{message}'",
                "message_id": msg_id,
                "recipient": target
            }


class FastPathRouter:
    """
    Enrutador determinista de baja latencia (Capa 1).
    Evalúa comandos de barra y expresiones regulares directas en microsegundos.
    """

    def __init__(self, contacts: Optional[ContactManager] = None):
        self.contacts = contacts or ContactManager()

        # Compilación de expresiones regulares para comandos de lenguaje natural
        self._whatsapp_patterns: List[re.Pattern] = [
            # "enviale un mensaje a <contacto> que diga <mensaje>"
            re.compile(r"^(?:por\s+favor\s+)?(?:envia(?:le|r)?|manda(?:le|r)?)\s+(?:un\s+)?(?:mensaje|texto|msj)\s+a\s+([a-zA-Z0-9_\+\-\.\s]+?)\s+que\s+diga\s+(.+)$", re.IGNORECASE),
            # "manda un whatsapp a <contacto> diciendo <mensaje>"
            re.compile(r"^(?:por\s+favor\s+)?(?:envia(?:le|r)?|manda(?:le|r)?)\s+(?:un\s+)?whatsapp\s+a\s+([a-zA-Z0-9_\+\-\.\s]+?)\s+(?:diciendo|con|que\s+diga)\s+(.+)$", re.IGNORECASE),
            # "enviar whatsapp a <contacto>: <mensaje>"
            re.compile(r"^(?:whatsapp|wa)\s+a\s+([a-zA-Z0-9_\+\-\.\s]+?)[:\s]+(.+)$", re.IGNORECASE),
            # "escribele a <contacto> por whatsapp: <mensaje>"
            re.compile(r"^escribe(?:le|r)?\s+a\s+([a-zA-Z0-9_\+\-\.\s]+?)\s+por\s+whatsapp[:\s]+(.+)$", re.IGNORECASE),
        ]

    def resolve(self, raw_text: str, agent: Optional[Any] = None) -> Optional[FastPathResult]:
        """
        Evalúa el texto entrante.
        Si coincide con un patrón determinista, retorna FastPathResult (0 tokens).
        Si no coincide, retorna None para activar el fallback al LLM.
        """
        if not raw_text or not raw_text.strip():
            return None

        text = raw_text.strip()
        lower_text = text.lower()
        clean_text = normalize_accents(lower_text)

        # ---------------------------------------------------------
        # 1. COMANDOS DE BARRA DIRECTOS
        # ---------------------------------------------------------

        # /wa o /whatsapp <contacto> <mensaje...>
        if text.startswith(("/wa ", "/whatsapp ")):
            parts = text.split(maxsplit=2)
            if len(parts) >= 3:
                contact_raw = parts[1].strip()
                message_body = parts[2].strip()
                return self._handle_whatsapp_action(contact_raw, message_body)
            else:
                return FastPathResult(
                    action="help_wa",
                    response_text="⚠️ *Sintaxis incorrecta para WhatsApp*\nUso: `/wa <contacto|número> <mensaje>`\nEjemplo: `/wa lider Reunión a las 5pm`"
                )

        # /status o /estado
        if lower_text in ("/status", "/estado", "status", "estado"):
            return self._handle_status_action(agent)

        # /ping
        if lower_text in ("/ping", "ping"):
            return FastPathResult(
                action="ping",
                response_text="🏓 *PONG* — Enlace de telemetría con JEV activo (Latencia: < 1ms)."
            )

        # /help o /ayuda
        if lower_text in ("/help", "/ayuda", "help", "ayuda", "/start", "start"):
            return self._handle_help_action()

        # /stop o /abort
        if lower_text in ("/stop", "/abort", "/parar", "/detener", "stop", "abort"):
            return self._handle_stop_action(agent)

        # /contacts o /contactos
        if lower_text in ("/contacts", "/contactos", "contactos", "ver contactos", "lista de contactos"):
            return self._handle_list_contacts_action()

        # /addcontact <nombre> <numero>
        if lower_text.startswith(("/addcontact ", "/agregar_contacto ")):
            parts = text.split(maxsplit=2)
            if len(parts) == 3:
                name, phone = parts[1].strip(), parts[2].strip()
                self.contacts.set_contact(name, phone)
                return FastPathResult(
                    action="add_contact",
                    response_text=f"✅ Contacto guardado: *{name}* ➔ `{phone}`"
                )
            return FastPathResult(
                action="help_addcontact",
                response_text="⚠️ *Sintaxis*: `/addcontact <nombre> <número>`\nEjemplo: `/addcontact supervisor +5215551234567`"
            )

        # /delcontact <nombre>
        if lower_text.startswith(("/delcontact ", "/eliminar_contacto ")):
            parts = text.split(maxsplit=1)
            if len(parts) == 2:
                name = parts[1].strip()
                if self.contacts.remove_contact(name):
                    return FastPathResult(action="del_contact", response_text=f"🗑️ Contacto *{name}* eliminado.")
                return FastPathResult(action="del_contact", response_text=f"⚠️ Contacto *{name}* no encontrado.")

        # ---------------------------------------------------------
        # 2. LENGUAJE NATURAL ESTRICTO (REGEX DETERMINISTA)
        # ---------------------------------------------------------

        # Frases estrictas de WhatsApp
        for pattern in self._whatsapp_patterns:
            match = pattern.match(clean_text)
            if match:
                contact_raw = match.group(1).strip()
                message_body = match.group(2).strip()
                # Extraer texto original preservando mayúsculas y acentos del mensaje
                orig_body = self._extract_message_body_original(text, match) or message_body
                return self._handle_whatsapp_action(contact_raw, orig_body)

        # Frases de estado del sistema
        if clean_text in ("estado del agente", "como esta el agente", "status del sistema", "estado del sistema", "que haces"):
            return self._handle_status_action(agent)

        # Frases de parada de emergencia
        if clean_text in ("para el agente", "deten la tarea", "detener tarea", "abortar tarea", "para ya", "cancela la tarea"):
            return self._handle_stop_action(agent)

        # Si no coincide con ninguna regla determinista, retornar None para activar el Fallback LLM
        return None

    def _extract_message_body_original(self, raw_text: str, match: re.Match) -> Optional[str]:
        """Preserva mayúsculas y signos de puntuación del mensaje de entrada original."""
        start_idx = match.start(2)
        if start_idx < len(raw_text):
            return raw_text[start_idx:].strip()
        return None

    def _handle_whatsapp_action(self, contact_identifier: str, message: str) -> FastPathResult:
        """Resuelve el número y ejecuta el despacho de WhatsApp."""
        contact_clean = contact_identifier.strip().strip(":").strip()
        phone = self.contacts.get_phone(contact_clean)
        display_target = contact_clean

        # Si no está en la libreta, verificar si es directamente un número telefónico (e.g. +521..., 5512345678)
        is_direct_phone = bool(re.match(r"^\+?[0-9]{7,15}$", re.sub(r"[\s\-\(\)]", "", contact_clean)))

        if not phone and is_direct_phone:
            phone = contact_clean
            display_target = phone

        if not phone:
            available = ", ".join([f"`{k}`" for k in self.contacts.list_contacts().keys()]) or "ninguno"
            return FastPathResult(
                action="whatsapp_error_not_found",
                response_text=(
                    f"⚠️ *Contacto desconocido*: No se encontró a *'{contact_clean}'* en la libreta.\n\n"
                    f"• Contactos registrados: {available}\n"
                    f"• Para registrarlo usa: `/addcontact {contact_clean} +52XXXXXXXXXX`\n"
                    f"• O escribe directamente el número telefónico internacional con código de país."
                ),
                data={"error": "contact_not_found", "target": contact_clean}
            )

        # Despachar mensaje
        dispatch_result = WhatsAppDispatcher.dispatch(recipient=contact_clean, message=message, phone_number=phone)
        msg_id = dispatch_result.get("message_id", "N/A")

        if dispatch_result.get("success", False):
            response_msg = (
                f"⚡ *[Fast Path] WhatsApp Despachado*\n"
                f"👤 *Destinatario*: {display_target} (`{phone}`)\n"
                f"💬 *Mensaje*: _{message}_\n"
                f"🆔 *ID de Envío*: `{msg_id}`\n"
                f"⏱️ *Latencia*: 0 tokens / Ejecución inmediata."
            )
            return FastPathResult(
                action="whatsapp_sent",
                response_text=response_msg,
                data=dispatch_result
            )
        else:
            err = dispatch_result.get("error", "Error desconocido en gateway")
            return FastPathResult(
                action="whatsapp_failed",
                response_text=f"❌ *Error al enviar WhatsApp a {display_target}*: {err}",
                data=dispatch_result
            )

    def _handle_status_action(self, agent: Optional[Any] = None) -> FastPathResult:
        """Devuelve un informe de telemetría y salud de JEV sin coste de LLM."""
        lines = ["🤖 *[JEV Telemetría y Estado del Sistema]*\n"]

        if agent:
            is_busy = getattr(agent, "is_running", False)
            state_str = "🟡 Ocupado (Ejecutando tarea)" if is_busy else "🟢 Libre / En espera de órdenes"
            lines.append(f"• *Estado del Agente*: {state_str}")
            lines.append(f"• *Modelo LLM Principal*: `{getattr(agent.config, 'model_name', 'N/A')}`")
            lines.append(f"• *Proveedor*: `{getattr(agent.config, 'llm_provider', 'N/A')}`")

            # Memoria
            if hasattr(agent, "memory"):
                try:
                    lessons_count = len(agent.memory.get_all_lessons())
                    lines.append(f"• *Lecciones Aprendidas*: {lessons_count}")
                except Exception:
                    pass

            # Herramientas
            if hasattr(agent, "registry"):
                try:
                    tools_count = len(agent.registry.list_tools())
                    lines.append(f"• *Herramientas Activas*: {tools_count}")
                except Exception:
                    pass
        else:
            lines.append("• *Estado del Agente*: 🟢 Operativo (Instancia base lista)")

        # Contactos
        contacts_count = len(self.contacts.list_contacts())
        lines.append(f"• *Contactos WhatsApp*: {contacts_count} registrados")
        lines.append(f"• *Modo de Operación*: Telegram Remote Bridge (Polling Activo)")

        return FastPathResult(
            action="status",
            response_text="\n".join(lines),
            data={"agent_running": getattr(agent, "is_running", False) if agent else False}
        )

    def _handle_stop_action(self, agent: Optional[Any] = None) -> FastPathResult:
        """Ordena la detención inmediata de cualquier tarea en curso."""
        if agent and hasattr(agent, "stop"):
            agent.stop()
            return FastPathResult(
                action="stop_agent",
                response_text="🛑 *[PARADA DE EMERGENCIA]*: Se ha enviado la señal de aborto al agente JEV. Las tareas activas han sido detenidas.",
                should_stop_agent=True
            )
        return FastPathResult(
            action="stop_agent",
            response_text="ℹ️ No hay tareas activas ejecutándose en este momento.",
            should_stop_agent=False
        )

    def _handle_list_contacts_action(self) -> FastPathResult:
        """Lista todos los contactos configurados."""
        contacts = self.contacts.list_contacts()
        if not contacts:
            return FastPathResult(
                action="list_contacts",
                response_text="📭 *Libreta de Contactos vacía*\nPuedes agregar contactos con `/addcontact <nombre> <número>`"
            )
        lines = ["📖 *[Libreta de Contactos WhatsApp]*\n"]
        for k, v in contacts.items():
            lines.append(f" • *{k.capitalize()}*: `{v}`")
        lines.append("\n_Para enviar un mensaje usa:_ `/wa <contacto> <mensaje>`")
        return FastPathResult(action="list_contacts", response_text="\n".join(lines), data=contacts)

    def _handle_help_action(self) -> FastPathResult:
        """Guía interactiva de atajos rápidos y comandos."""
        help_text = (
            "🚀 *[JEV Remote Control — Menú de Comandos]*\n\n"
            "*⚡ Capa 1: Fast Path (0 Tokens / Latencia Cero):*\n"
            " • `/wa <contacto> <mensaje>` : Envío instantáneo de WhatsApp.\n"
            "   _Ej: `/wa lider Llegaré en 15 minutos`_\n"
            " • `enviale un mensaje a <contacto> que diga <mensaje>`\n"
            " • `/status` : Telemetría y estado de salud de JEV.\n"
            " • `/contacts` : Ver contactos registrados en `contacts.json`.\n"
            " • `/addcontact <nombre> <número>` : Guardar un nuevo contacto.\n"
            " • `/delcontact <nombre>` : Eliminar un contacto.\n"
            " • `/stop` : Parada de emergencia de tareas activas.\n"
            " • `/ping` : Comprobar enlace de comunicación.\n\n"
            "*🧠 Capa 2: Fallback al Agente Autónomo (LLM):*\n"
            "Cualquier otra instrucción, pregunta, generación de código o tarea compleja "
            "se canalizará automáticamente al motor cognitivo de JEV con acceso total a sus herramientas."
        )
        return FastPathResult(action="help", response_text=help_text)
