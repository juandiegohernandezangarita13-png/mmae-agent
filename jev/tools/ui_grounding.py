"""
Herramientas de Anclaje Visual Inteligente (Smart Visual Grounding) y Automatización UI para JEV.
Permite al agente interactuar con la pantalla localizando texto, botones, iconos o campos
mediante una arquitectura multi-nivel:
  1. Windows UI Automation (UIA nativo en milisegundos)
  2. Windows 11 Native Media OCR (WinRT OcrEngine)
  3. Visión Multimodal con Gemini Vision (Localización semántica de iconos y gráficos)
"""
from __future__ import annotations

import os
import sys
import time
import json
import base64
import subprocess
import io
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple

import pyautogui
from jev.tools.base import BaseTool, ToolResult
from jev.config import default_config

pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.02


class FindUIElementTool(BaseTool):
    """Localiza elementos en pantalla mediante UIA nativo, OCR de Windows o Visión Multimodal."""
    name = "find_ui_element"
    description = (
        "Busca una palabra, botón, icono o campo visible en la pantalla "
        "y devuelve sus coordenadas exactas (x, y), dimensiones y método de detección. "
        "Utiliza inspección nativa de Windows (UIA), OCR y Gemini Vision."
    )
    parameters = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Texto, botón, icono o descripción visual a localizar (ej: 'Buscar', 'Guardar', 'Zuzi', 'icono de lupa', 'botón enviar')."
            },
            "only_focused_window": {
                "type": "boolean",
                "description": "Si es True, busca primero dentro de la ventana en primer plano; si es False, busca en toda la pantalla.",
                "default": True
            }
        },
        "required": ["query"]
    }

    def __init__(self, workspace_dir: Optional[Path] = None):
        self.workspace_dir = workspace_dir or default_config.workspace_dir

    def execute(self, query: str, only_focused_window: bool = True, **kwargs) -> ToolResult:
        query_clean = (query or "").strip()
        if not query_clean:
            return ToolResult(success=False, output="", error="La consulta de búsqueda UI no puede estar vacía.")

        screen_w, screen_h = pyautogui.size()

        # -------------------------------------------------------------
        # NIVEL 1: Windows UI Automation (Nativo, instantáneo y exacto)
        # -------------------------------------------------------------
        uia_result = self._search_via_uia(query_clean, only_focused_window)
        if uia_result and uia_result.get("found"):
            x = uia_result["x"]
            y = uia_result["y"]
            return ToolResult(
                success=True,
                output=(
                    f"✓ Elemento UI '{query_clean}' localizado mediante Windows UI Automation en ({x}, {y}). "
                    f"Tipo: {uia_result.get('type')}, Texto: '{uia_result.get('text')}'."
                ),
                data={
                    "query": query_clean,
                    "x": x,
                    "y": y,
                    "engine": "Windows UI Automation",
                    "rect": uia_result.get("rect"),
                    "confidence": 1.0,
                    "details": uia_result
                }
            )

        # -------------------------------------------------------------
        # NIVEL 2: Gemini Multimodal Vision Grounding (Para iconos y canvas)
        # -------------------------------------------------------------
        vision_result = self._search_via_gemini_vision(query_clean, screen_w, screen_h)
        if vision_result and vision_result.get("found"):
            x = vision_result["x"]
            y = vision_result["y"]
            return ToolResult(
                success=True,
                output=(
                    f"✓ Elemento visual '{query_clean}' localizado mediante Gemini Vision en ({x}, {y}). "
                    f"Confianza: {vision_result.get('confidence', 0.9):.2f}. "
                    f"Descripción: {vision_result.get('description', '')}"
                ),
                data={
                    "query": query_clean,
                    "x": x,
                    "y": y,
                    "engine": "Gemini Multimodal Vision",
                    "confidence": vision_result.get("confidence", 0.9),
                    "details": vision_result
                }
            )

        # -------------------------------------------------------------
        # NIVEL 3: Windows Media OCR (WinRT nativo para texto plano)
        # -------------------------------------------------------------
        ocr_result = self._search_via_windows_ocr(query_clean, screen_w, screen_h)
        if ocr_result and ocr_result.get("found"):
            x = ocr_result["x"]
            y = ocr_result["y"]
            return ToolResult(
                success=True,
                output=f"✓ Texto '{query_clean}' localizado mediante Windows Media OCR en ({x}, {y}).",
                data={
                    "query": query_clean,
                    "x": x,
                    "y": y,
                    "engine": "Windows Media OCR",
                    "confidence": 0.85,
                    "details": ocr_result
                }
            )

        # -------------------------------------------------------------
        # NIVEL 4: Fallback heurístico de anclajes universales
        # -------------------------------------------------------------
        fallback = self._heuristic_fallback(query_clean, screen_w, screen_h)
        if fallback:
            x, y, label = fallback
            return ToolResult(
                success=True,
                output=f"ℹ Elemento UI '{query_clean}' mapeado por heurística de sistema ('{label}') en ({x}, {y}).",
                data={"query": query_clean, "x": x, "y": y, "engine": "Heuristic Anchor", "confidence": 0.70}
            )

        return ToolResult(
            success=False,
            output="",
            error=(
                f"No se pudo localizar el elemento '{query_clean}' en pantalla ni por UI Automation, "
                f"ni por Visión IA ni por OCR. Asegúrate de que la ventana correcta esté al frente y visible."
            )
        )

    def _search_via_uia(self, query: str, only_focused: bool) -> Optional[Dict[str, Any]]:
        """Busca en el árbol de controles nativo de Windows."""
        try:
            import uiautomation as auto
            auto.SetGlobalSearchTimeout(1.0)

            root = (auto.GetForegroundControl() or auto.GetFocusedControl()) if only_focused else auto.GetRootControl()
            if not root and only_focused:
                root = auto.GetRootControl()

            if not root:
                return None

            q_lower = query.lower()
            candidates = []

            def walk(ctrl, depth=0):
                if depth > 6 or len(candidates) > 100:
                    return
                try:
                    name = (ctrl.Name or "").strip()
                    help_text = (getattr(ctrl, "HelpText", "") or "").strip()
                    auto_id = (getattr(ctrl, "AutomationId", "") or "").strip()
                    c_type = ctrl.ControlTypeName or ""

                    text_blob = f"{name} {help_text} {auto_id}".lower()

                    if q_lower in text_blob or any(word in text_blob for word in q_lower.split() if len(word) > 2):
                        rect = ctrl.BoundingRectangle
                        if rect and rect.width() > 0 and rect.height() > 0:
                            exact = (q_lower == name.lower())
                            score = 2.0 if exact else (1.5 if q_lower in name.lower() else 1.0)
                            candidates.append({
                                "found": True,
                                "x": rect.xcenter(),
                                "y": rect.ycenter(),
                                "text": name,
                                "type": c_type,
                                "rect": [rect.left, rect.top, rect.right, rect.bottom],
                                "score": score
                            })

                    for child in ctrl.GetChildren():
                        walk(child, depth + 1)
                except Exception:
                    pass

            walk(root)

            if candidates:
                candidates.sort(key=lambda c: c["score"], reverse=True)
                return candidates[0]
        except Exception:
            pass
        return None

    def _capture_screen_bytes(self) -> Optional[Tuple[bytes, int, int]]:
        """Captura la pantalla actual en PNG devolviendo (bytes, width, height)."""
        # Método 1: PIL ImageGrab
        try:
            from PIL import ImageGrab
            img = ImageGrab.grab()
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            return buf.getvalue(), img.width, img.height
        except Exception:
            pass

        # Método 2: mss
        try:
            import mss
            with mss.mss() as sct:
                mon = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]
                shot = sct.grab(mon)
                png_bytes = mss.tools.to_png(shot.rgb, shot.size)
                return png_bytes, shot.width, shot.height
        except Exception:
            pass

        # Método 3: PowerShell .NET Graphics
        try:
            ps_script = """
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
$bounds = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
$bmp = New-Object System.Drawing.Bitmap($bounds.Width, $bounds.Height)
$graphics = [System.Drawing.Graphics]::FromImage($bmp)
$graphics.CopyFromScreen($bounds.Location, [System.Drawing.Point]::Empty, $bounds.Size)
$ms = New-Object System.IO.MemoryStream
$bmp.Save($ms, [System.Drawing.Imaging.ImageFormat]::Png)
$bytes = $ms.ToArray()
[Convert]::ToBase64String($bytes)
$graphics.Dispose()
$bmp.Dispose()
"""
            proc = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_script],
                capture_output=True,
                text=True,
                timeout=5
            )
            if proc.returncode == 0 and proc.stdout.strip():
                raw = base64.b64decode(proc.stdout.strip())
                from PIL import Image
                with Image.open(io.BytesIO(raw)) as p_img:
                    return raw, p_img.width, p_img.height
        except Exception:
            pass

        return None

    def _search_via_gemini_vision(self, query: str, screen_w: int, screen_h: int) -> Optional[Dict[str, Any]]:
        """Utiliza Gemini Vision para anclar elementos gráficos complejos o iconos."""
        api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or getattr(default_config, "gemini_api_key", "")
        if not api_key:
            return None

        capture = self._capture_screen_bytes()
        if not capture:
            return None

        png_bytes, width, height = capture
        b64_img = base64.b64encode(png_bytes).decode("ascii")

        prompt = (
            f"Actúas como motor de visual grounding y automatización de interfaz de usuario en Windows.\n"
            f"Resolución de pantalla: {width} x {height} píxeles.\n"
            f"El usuario necesita hacer clic en: '{query}'.\n"
            f"Localiza el elemento visual, botón, icono, campo o texto que mejor coincida.\n"
            f"IMPORTANTE: Devuelve ÚNICAMENTE un objeto JSON válido con la siguiente estructura exacta:\n"
            f'{{"found": true, "x": 120, "y": 450, "confidence": 0.95, "description": "Icono de búsqueda en la barra superior"}}\n'
            f'Si el elemento no está visible, devuelve: {{"found": false, "reason": "no visible en pantalla"}}.\n'
            f"Sin explicaciones ni texto fuera del JSON."
        )

        import urllib.request
        for model in ("gemini-2.5-flash", "gemini-flash-lite-latest", "gemini-3.1-flash-lite"):
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
            payload = {
                "contents": [
                    {
                        "parts": [
                            {"text": prompt},
                            {
                                "inlineData": {
                                    "mimeType": "image/png",
                                    "data": b64_img
                                }
                            }
                        ]
                    }
                ],
                "generationConfig": {
                    "temperature": 0.1,
                    "responseMimeType": "application/json"
                }
            }
            try:
                req = urllib.request.Request(
                    url,
                    data=json.dumps(payload).encode("utf-8"),
                    headers={"Content-Type": "application/json"}
                )
                with urllib.request.urlopen(req, timeout=12.0) as resp:
                    if resp.status == 200:
                        data = json.loads(resp.read().decode("utf-8"))
                        candidates = data.get("candidates", [])
                        if candidates:
                            raw_text = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                            clean_json = raw_text.strip()
                            if clean_json.startswith("```"):
                                clean_json = clean_json.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
                            parsed = json.loads(clean_json)
                            if parsed.get("found") and "x" in parsed and "y" in parsed:
                                return parsed
            except Exception:
                continue
        return None

    def _search_via_windows_ocr(self, query: str, screen_w: int, screen_h: int) -> Optional[Dict[str, Any]]:
        """Ejecuta Windows Media OCR sobre la pantalla actual."""
        try:
            # Script PowerShell para ejecutar OCR sobre la pantalla activa
            ps_script = f"""
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
[Windows.Media.Ocr.OcrEngine, Windows.Foundation.UniversalApiContract, ContentType = WindowsRuntime] | Out-Null
$engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages()
if (-not $engine) {{
    Write-Output '{{"found": false}}'
    exit
}}
$bounds = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
$bmp = New-Object System.Drawing.Bitmap($bounds.Width, $bounds.Height)
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.CopyFromScreen($bounds.Location, [System.Drawing.Point]::Empty, $bounds.Size)
$ms = New-Object System.IO.MemoryStream
$bmp.Save($ms, [System.Drawing.Imaging.ImageFormat]::Bmp)
$bytes = $ms.ToArray()
$g.Dispose()
$bmp.Dispose()

# Crear SoftwareBitmap
$stream = New-Object Windows.Storage.Streams.InMemoryRandomAccessStream
$writer = New-Object Windows.Storage.Streams.DataWriter($stream)
$writer.WriteBytes($bytes)
$null = $writer.StoreAsync().GetAwaiter().GetResult()
$stream.Seek(0)
$decoder = [Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream).GetAwaiter().GetResult()
$sBmp = $decoder.GetSoftwareBitmapAsync().GetAwaiter().GetResult()
$ocrResult = $engine.RecognizeAsync($sBmp).GetAwaiter().GetResult()

$q = "{query}".ToLower()
$match = $null
foreach ($line in $ocrResult.Lines) {{
    if ($line.Text.ToLower().Contains($q)) {{
        foreach ($word in $line.Words) {{
            if ($word.Text.ToLower().Contains($q)) {{
                $match = @{{
                    found = $true
                    x = [int]($word.BoundingRect.X + ($word.BoundingRect.Width / 2))
                    y = [int]($word.BoundingRect.Y + ($word.BoundingRect.Height / 2))
                    text = $word.Text
                }}
                break
            }}
        }}
        if (-not $match) {{
            $match = @{{
                found = $true
                x = [int]($line.Words[0].BoundingRect.X + 20)
                y = [int]($line.Words[0].BoundingRect.Y + 10)
                text = $line.Text
            }}
        }}
        break
    }}
}}
if ($match) {{
    $match | ConvertTo-Json -Compress
}} else {{
    Write-Output '{{"found": false}}'
}}
"""
            proc = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_script],
                capture_output=True,
                text=True,
                timeout=6
            )
            if proc.returncode == 0 and proc.stdout.strip():
                try:
                    res = json.loads(proc.stdout.strip())
                    if res.get("found"):
                        return res
                except Exception:
                    pass
        except Exception:
            pass
        return None

    def _heuristic_fallback(self, query: str, screen_w: int, screen_h: int) -> Optional[Tuple[int, int, str]]:
        q = query.lower()
        if "start" in q or "inicio" in q or "windows" in q:
            return int(screen_w / 2), screen_h - 20, "Botón Inicio Win11"
        if "close" in q or "cerrar" in q or q == "x":
            return screen_w - 25, 15, "Botón Cerrar Ventana"
        if "minimize" in q or "minimizar" in q:
            return screen_w - 75, 15, "Botón Minimizar Ventana"
        return None


class SmartUIClickTool(BaseTool):
    """
    Localizador y Ejecutor Inteligente de Clics en Pantalla.
    Localiza un elemento por texto, icono o descripción, lo enfoca, hace clic
    y opcionalmente escribe texto o pulsa teclas de forma atómica.
    """
    name = "smart_ui_click"
    description = (
        "Encuentra cualquier elemento, botón, pestaña o campo en pantalla mediante IA visual y UIA, "
        "hace clic sobre él con precisión y opcionalmente escribe texto o pulsa Enter de manera atómica. "
        "Ej: smart_ui_click(target='Buscar', typing_text='Zuzi', press_enter=True)."
    )
    parameters = {
        "type": "object",
        "properties": {
            "target": {
                "type": "string",
                "description": "Texto, etiqueta, icono o elemento donde hacer clic (ej: 'Buscar', 'Guardar', 'Zuzi', 'icono de enviar', 'Cerrar')."
            },
            "clicks": {
                "type": "integer",
                "description": "Número de clics (1 para clic simple, 2 para doble clic). Defecto 1.",
                "default": 1
            },
            "button": {
                "type": "string",
                "enum": ["left", "right", "middle"],
                "description": "Botón del ratón ('left', 'right', 'middle'). Defecto 'left'.",
                "default": "left"
            },
            "focus_window": {
                "type": "string",
                "description": "Nombre o palabra clave de la ventana a traer al frente antes de hacer clic (ej: 'WhatsApp', 'OpenSCAD', 'Notepad')."
            },
            "typing_text": {
                "type": "string",
                "description": "Texto opcional a escribir con el teclado inmediatamente después de hacer clic en el elemento."
            },
            "press_enter": {
                "type": "boolean",
                "description": "Si es True, presiona la tecla Enter después de escribir el texto opcional.",
                "default": False
            },
            "wait_after": {
                "type": "number",
                "description": "Segundos de espera tras completar la acción (defecto 0.3s).",
                "default": 0.3
            }
        },
        "required": ["target"]
    }

    def __init__(self, finder_tool: Optional[FindUIElementTool] = None):
        self.finder = finder_tool or FindUIElementTool()

    def execute(
        self,
        target: str,
        clicks: int = 1,
        button: str = "left",
        focus_window: Optional[str] = None,
        typing_text: Optional[str] = None,
        press_enter: bool = False,
        wait_after: float = 0.3,
        **kwargs
    ) -> ToolResult:
        try:
            # 1. Si se solicita enfocar una ventana específica primero
            if focus_window:
                self._focus_window(focus_window)
                time.sleep(0.3)

            # 2. Localizar el elemento
            find_res = self.finder.execute(query=target)
            if not find_res.success:
                return find_res

            coords = find_res.data
            target_x = coords.get("x", 0)
            target_y = coords.get("y", 0)
            engine = coords.get("engine", "Visual Grounding")

            # 3. Mover y hacer clic
            pyautogui.moveTo(target_x, target_y, duration=0.2)
            pyautogui.click(x=target_x, y=target_y, clicks=clicks, button=button)
            time.sleep(0.1)

            typed_summary = ""
            # 4. Si se indicó texto a escribir
            if typing_text:
                pyautogui.write(typing_text, interval=0.01)
                typed_summary = f" y escribió '{typing_text}'"
                if press_enter:
                    time.sleep(0.1)
                    pyautogui.press("enter")
                    typed_summary += " con [Enter]"

            if wait_after > 0:
                time.sleep(wait_after)

            msg = (
                f"✓ Clic inteligente ({clicks}x {button}) ejecutado sobre '{target}' en ({target_x}, {target_y}) "
                f"usando [{engine}]{typed_summary}."
            )
            return ToolResult(
                success=True,
                output=msg,
                data={
                    "target": target,
                    "x": target_x,
                    "y": target_y,
                    "engine": engine,
                    "clicks": clicks,
                    "typed": typing_text,
                    "pressed_enter": press_enter
                }
            )
        except Exception as e:
            return ToolResult(success=False, output="", error=f"Error en smart_ui_click para '{target}': {str(e)}")

    def _focus_window(self, title_keyword: str) -> bool:
        """Trae al frente la ventana cuyo título contenga la palabra clave."""
        try:
            import ctypes
            from ctypes import wintypes
            user32 = ctypes.windll.user32
            keyword = title_keyword.lower()
            found_hwnds = []

            WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

            def _enum_proc(hwnd, _):
                if user32.IsWindowVisible(hwnd):
                    length = user32.GetWindowTextLengthW(hwnd)
                    if length > 0:
                        buf = ctypes.create_unicode_buffer(length + 1)
                        user32.GetWindowTextW(hwnd, buf, length + 1)
                        if keyword in buf.value.lower():
                            found_hwnds.append(hwnd)
                return True

            user32.EnumWindows(WNDENUMPROC(_enum_proc), 0)
            if found_hwnds:
                hwnd = found_hwnds[0]
                user32.ShowWindow(hwnd, 9)  # SW_RESTORE
                user32.BringWindowToTop(hwnd)
                user32.SetForegroundWindow(hwnd)
                return True
        except Exception:
            pass
        return False


class ClickElementByTextTool(SmartUIClickTool):
    """Alias retrocompatible para ClickElementByTextTool que delega en SmartUIClickTool."""
    name = "click_by_text"
    description = (
        "Localiza un botón, texto o enlace en la pantalla que contenga el texto especificado "
        "y hace clic sobre él en una sola operación inteligente."
    )
    parameters = {
        "type": "object",
        "properties": {
            "text": {
                "type": "string",
                "description": "Texto del elemento en el que hacer clic (ej: 'Guardar', 'Aceptar', 'Buscar')."
            },
            "clicks": {
                "type": "integer",
                "description": "Número de clics (1 para clic simple, 2 para doble clic). Por defecto 1.",
                "default": 1
            }
        },
        "required": ["text"]
    }

    def execute(self, text: str, clicks: int = 1, **kwargs) -> ToolResult:
        return super().execute(target=text, clicks=clicks, **kwargs)
