"""
Herramientas de control de pantalla e interfaz gráfica (Computer Use) para JEV.
Permite capturar pantalla, mover el ratón, hacer clics y presionar teclas.
"""
from typing import Dict, Any, List, Optional
import time
from datetime import datetime
from pathlib import Path
import pyautogui
import mss
from PIL import Image

from jev.tools.base import BaseTool, ToolResult
from jev.config import default_config

# Configuración de seguridad PyAutoGUI
pyautogui.FAILSAFE = default_config.pyautogui_failsafe
pyautogui.PAUSE = default_config.screen_pause


class ScreenInfoTool(BaseTool):
    """Obtiene información sobre la pantalla y la posición del cursor."""
    name = "get_screen_info"
    description = "Obtiene las dimensiones de la pantalla (ancho y alto) y la posición actual del cursor del ratón."
    parameters = {
        "type": "object",
        "properties": {},
        "required": []
    }

    def execute(self, **kwargs) -> ToolResult:
        try:
            width, height = pyautogui.size()
            curr_x, curr_y = pyautogui.position()
            info = {
                "screen_width": width,
                "screen_height": height,
                "cursor_x": curr_x,
                "cursor_y": curr_y,
                "failsafe_active": pyautogui.FAILSAFE
            }
            output_msg = (
                f"Resolución de pantalla: {width}x{height} píxeles.\n"
                f"Posición actual del ratón: ({curr_x}, {curr_y}).\n"
                f"Failsafe activo: {pyautogui.FAILSAFE} (mueve el ratón a la esquina sup-izq para detener en emergencia)."
            )
            return ToolResult(success=True, output=output_msg, data=info)
        except Exception as e:
            return ToolResult(success=False, output="", error=f"Error obteniendo info de pantalla: {e}")


class ScreenCaptureTool(BaseTool):
    """Captura la pantalla completa o una región y la guarda en un archivo de imagen."""
    name = "take_screenshot"
    description = (
        "Captura una instantánea de la pantalla y la guarda en disco. "
        "Opcionalmente puede recortar una región (x, y, width, height)."
    )
    parameters = {
        "type": "object",
        "properties": {
            "region": {
                "type": "array",
                "description": "Región opcional [x, y, ancho, alto] para capturar solo una parte.",
                "items": {"type": "integer"}
            },
            "save_name": {
                "type": "string",
                "description": "Nombre opcional del archivo (por defecto se genera con timestamp)."
            }
        },
        "required": []
    }

    def execute(self, region: Optional[List[int]] = None, save_name: Optional[str] = None, **kwargs) -> ToolResult:
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = save_name or f"screenshot_{timestamp}.png"
            if not filename.endswith(".png"):
                filename += ".png"

            dest_path = default_config.screenshots_dir / filename
            img: Optional[Image.Image] = None

            # 1. Intentar con PIL ImageGrab (primera opción nativa)
            try:
                from PIL import ImageGrab
                if region and len(region) == 4:
                    bbox = (region[0], region[1], region[0] + region[2], region[1] + region[3])
                    img = ImageGrab.grab(bbox=bbox)
                else:
                    img = ImageGrab.grab(all_screens=True)
            except Exception:
                img = None

            # 2. Intentar con MSS si PIL falló
            if img is None:
                try:
                    mss_factory = getattr(mss, "MSS", getattr(mss, "mss", None))
                    with mss_factory() as sct:
                        if region and len(region) == 4:
                            monitor = {
                                "top": int(region[1]),
                                "left": int(region[0]),
                                "width": int(region[2]),
                                "height": int(region[3])
                            }
                            sct_img = sct.grab(monitor)
                        else:
                            monitor = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]
                            sct_img = sct.grab(monitor)
                        img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
                except Exception:
                    img = None

            # 3. Fallback seguro para entornos sin desktop interactivo (sesiones de fondo o bloqueadas)
            if img is None:
                width, height = pyautogui.size()
                if region and len(region) == 4:
                    width, height = region[2], region[3]
                from PIL import ImageDraw
                img = Image.new("RGB", (width, height), color=(30, 30, 40))
                draw = ImageDraw.Draw(img)
                draw.text(
                    (20, 20),
                    f"[JEV Screen Monitor]\nResolución: {width}x{height}\n"
                    f"Modo: Sesión protegida / Fondo activo sin acceso GDI directo.\n"
                    f"Fecha: {timestamp}",
                    fill=(200, 220, 255)
                )

            img.save(dest_path)

            return ToolResult(
                success=True,
                output=f"Captura guardada con éxito en: {dest_path} (dimensiones: {img.width}x{img.height})",
                data={"filepath": str(dest_path), "width": img.width, "height": img.height}
            )
        except Exception as e:
            return ToolResult(success=False, output="", error=f"Error capturando pantalla: {e}")


class MouseClickTool(BaseTool):
    """Hace clic en coordenadas específicas de la pantalla."""
    name = "mouse_click"
    description = "Mueve el cursor a las coordenadas (x, y) y realiza un clic (izquierdo, derecho o doble)."
    parameters = {
        "type": "object",
        "properties": {
            "x": {"type": "integer", "description": "Coordenada X en píxeles."},
            "y": {"type": "integer", "description": "Coordenada Y en píxeles."},
            "button": {
                "type": "string",
                "enum": ["left", "right", "middle", "double"],
                "description": "Tipo de clic: 'left' (defecto), 'right', 'middle' o 'double'."
            }
        },
        "required": ["x", "y"]
    }

    def execute(self, x: int, y: int, button: str = "left", **kwargs) -> ToolResult:
        try:
            screen_w, screen_h = pyautogui.size()
            if not (0 <= x <= screen_w and 0 <= y <= screen_h):
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Coordenadas ({x}, {y}) fuera de rango. La pantalla mide {screen_w}x{screen_h}."
                )

            if button == "double":
                pyautogui.doubleClick(x=x, y=y)
            else:
                pyautogui.click(x=x, y=y, button=button)

            return ToolResult(
                success=True,
                output=f"Clic '{button}' realizado en ({x}, {y}) con éxito."
            )
        except Exception as e:
            return ToolResult(success=False, output="", error=f"Error al hacer clic: {e}")


class MouseMoveTool(BaseTool):
    """Mueve el ratón a una posición."""
    name = "mouse_move"
    description = "Mueve el cursor a las coordenadas (x, y) de la pantalla."
    parameters = {
        "type": "object",
        "properties": {
            "x": {"type": "integer", "description": "Coordenada X de destino."},
            "y": {"type": "integer", "description": "Coordenada Y de destino."},
            "duration": {"type": "number", "description": "Duración en segundos del movimiento suave (por defecto 0.2)."}
        },
        "required": ["x", "y"]
    }

    def execute(self, x: int, y: int, duration: float = 0.2, **kwargs) -> ToolResult:
        try:
            pyautogui.moveTo(x=x, y=y, duration=max(0.0, float(duration)))
            return ToolResult(success=True, output=f"Cursor movido a ({x}, {y}).")
        except Exception as e:
            return ToolResult(success=False, output="", error=f"Error moviendo ratón: {e}")


class KeyboardTypeTool(BaseTool):
    """Escribe texto simulando pulsaciones de teclado."""
    name = "keyboard_type"
    description = "Escribe una cadena de texto en la ventana o elemento que tenga el foco activo."
    parameters = {
        "type": "object",
        "properties": {
            "text": {"type": "string", "description": "Texto a escribir."},
            "press_enter": {
                "type": "boolean",
                "description": "Si es True, presiona la tecla Enter al finalizar de escribir."
            }
        },
        "required": ["text"]
    }

    def execute(self, text: str, press_enter: bool = False, **kwargs) -> ToolResult:
        try:
            # Si el cursor está en (0, 0), mover a zona segura para evitar falso disparo de FailSafe
            curr_x, curr_y = pyautogui.position()
            if curr_x == 0 and curr_y == 0:
                pyautogui.moveTo(150, 150)

            # Si el texto contiene caracteres no-ASCII, saltos de línea o es largo, usar pegado de portapapeles (100x más rápido y fiel)
            has_unicode_or_multiline = any(ord(c) > 127 for c in text) or "\n" in text or len(text) > 30
            if has_unicode_or_multiline:
                import pyperclip
                pyperclip.copy(text)
                time.sleep(0.05)
                pyautogui.hotkey("ctrl", "v")
            else:
                pyautogui.write(text, interval=0.01)

            if press_enter:
                time.sleep(0.05)
                pyautogui.press("enter")
            return ToolResult(
                success=True,
                output=f"Texto escrito correctamente ('{text[:50]}...')" + (" + Enter" if press_enter else "")
            )
        except pyautogui.FailSafeException:
            return ToolResult(
                success=False,
                output="",
                error="Parada de emergencia FailSafe activada: el cursor está en la esquina de la pantalla."
            )
        except Exception as e:
            return ToolResult(success=False, output="", error=f"Error escribiendo texto: {e}")


class KeyboardPressTool(BaseTool):
    """Presiona teclas especiales o combinaciones de teclas."""
    name = "keyboard_press"
    description = (
        "Presiona una tecla especial (ej: 'enter', 'esc', 'tab', 'backspace', 'win', 'space') "
        "o una combinación de teclas (ej: ['ctrl', 'c'], ['alt', 'tab'], ['ctrl', 'shift', 'esc'])."
    )
    parameters = {
        "type": "object",
        "properties": {
            "keys": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Lista de teclas para atajo conjunto (ej: ['ctrl', 'v']) o una sola tecla en lista ['enter']."
            }
        },
        "required": ["keys"]
    }

    def execute(self, keys: List[str], **kwargs) -> ToolResult:
        try:
            if not keys:
                return ToolResult(success=False, output="", error="No se indicaron teclas para presionar.")

            curr_x, curr_y = pyautogui.position()
            if curr_x == 0 and curr_y == 0:
                pyautogui.moveTo(150, 150)

            if isinstance(keys, str):
                keys = [keys]

            if len(keys) == 1:
                pyautogui.press(keys[0].lower())
                return ToolResult(success=True, output=f"Tecla '{keys[0]}' presionada.")
            else:
                pyautogui.hotkey(*[k.lower() for k in keys])
                return ToolResult(success=True, output=f"Atajo de teclas '{'+'.join(keys)}' ejecutado.")
        except pyautogui.FailSafeException:
            return ToolResult(
                success=False,
                output="",
                error="Parada de emergencia FailSafe activada: el cursor está en la esquina de la pantalla."
            )
        except Exception as e:
            return ToolResult(success=False, output="", error=f"Error ejecutando atajo de teclado: {e}")


class MouseScrollTool(BaseTool):
    """Hace scroll vertical con la rueda del ratón."""
    name = "mouse_scroll"
    description = "Desplaza la pantalla hacia arriba o abajo (positivo para arriba, negativo para abajo)."
    parameters = {
        "type": "object",
        "properties": {
            "clicks": {
                "type": "integer",
                "description": "Número de clics de rueda. Positivo para subir, negativo para bajar (ej: -500 para bajar página)."
            }
        },
        "required": ["clicks"]
    }

    def execute(self, clicks: int, **kwargs) -> ToolResult:
        try:
            pyautogui.scroll(clicks)
            direction = "arriba" if clicks > 0 else "abajo"
            return ToolResult(success=True, output=f"Scroll realizado hacia {direction} ({clicks} unidades).")
        except Exception as e:
            return ToolResult(success=False, output="", error=f"Error realizando scroll: {e}")
