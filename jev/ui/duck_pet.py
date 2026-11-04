"""
Módulo Desktop Duck Pet (Pato de Escritorio 100% Transparente).
Implementa un compañero pixel-art animado que camina sobre la barra de tareas de Windows,
animando físicamente los pies paso a paso sobre el fondo del escritorio (sin recuadros blancos),
mostrando el estado de actividad del agente y abriendo la interfaz con doble clic.
"""
from __future__ import annotations

import ctypes
import os
import subprocess
import sys
import threading
import time
import tkinter as tk
from ctypes import wintypes
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageTk

from config import BASE_DIR
from jev.core.status_sync import get_agent_status
from utils.logger import log

# Paleta de colores pixel-art fiel a la imagen dibujada
PALETTE = {
    ' ': (1, 1, 1, 0),         # Color clave transparente (#010101)
    'B': (15, 15, 20, 255),    # Negro contorno
    'W': (255, 255, 255, 255),# Blanco plumaje
    'S': (220, 226, 238, 255),# Sombra plumaje
    'O': (255, 75, 10, 255),   # Naranja pico y patas
    'D': (210, 50, 0, 255),    # Naranja oscuro
}

# Matrices de sprites (12 columnas x 16 filas)
SPRITES_DATA = {
    "STAND": [
        "    BBBB    ",
        "   BWWBWB   ",
        "  OBWWWB    ",
        " OOBBWB     ",
        "   BWWB     ",
        "   BWWB     ",
        "   BWWB     ",
        "  BWWWWB    ",
        " BWWWWWB    ",
        " BWWWWWWB   ",
        " BWWWWWWWBB ",
        "  BWWWWWWB  ",
        "   BBBBBB   ",
        "   BOOBB    ",
        "   BOOB OB  ",
        "   BBBB BB  "
    ],
    "WALK_1": [
        "    BBBB    ",
        "   BWWBWB   ",
        "  OBWWWB    ",
        " OOBBWB     ",
        "   BWWB     ",
        "   BWWB     ",
        "   BWWB     ",
        "  BWWWWB    ",
        " BWWWWWB    ",
        " BWWWWWWB   ",
        " BWWWWWWWBB ",
        "  BWWWWWWB  ",
        "   BBBBBB   ",
        "  BOOBB     ",
        " OOOOB  OB  ",
        " BBBBB  BB  "
    ],
    "WALK_2": [
        "    BBBB    ",
        "   BWWBWB   ",
        "  OBWWWB    ",
        " OOBBWB     ",
        "   BWWB     ",
        "   BWWB     ",
        "   BWWB     ",
        "  BWWWWB    ",
        " BWWWWWB    ",
        " BWWWWWWB   ",
        " BWWWWWWWBB ",
        "  BWWWWWWB  ",
        "   BBBBBB   ",
        "   BOOBB    ",
        "   BOOB OOB ",
        "   BBBB     "
    ],
    "WALK_3": [
        "    BBBB    ",
        "   BWWBWB   ",
        "  OBWWWB    ",
        " OOBBWB     ",
        "   BWWB     ",
        "   BWWB     ",
        "   BWWB     ",
        "  BWWWWB    ",
        " BWWWWWB    ",
        " BWWWWWWB   ",
        " BWWWWWWWBB ",
        "  BWWWWWWB  ",
        "   BBBBBB   ",
        "    BOOBB   ",
        " BO  OOOOOB ",
        " BB  BBBBBB "
    ],
    "WALK_4": [
        "    BBBB    ",
        "   BWWBWB   ",
        "  OBWWWB    ",
        " OOBBWB     ",
        "   BWWB     ",
        "   BWWB     ",
        "   BWWB     ",
        "  BWWWWB    ",
        " BWWWWWB    ",
        " BWWWWWWB   ",
        " BWWWWWWWBB ",
        "  BWWWWWWB  ",
        "   BBBBBB   ",
        "   OOB BOOB ",
        "       BOOB ",
        "       BBBB "
    ],
    "BLINK": [
        "    BBBB    ",
        "   BBBBBB   ",
        "  OBWWWB    ",
        " OOBBWB     ",
        "   BWWB     ",
        "   BWWB     ",
        "   BWWB     ",
        "  BWWWWB    ",
        " BWWWWWB    ",
        " BWWWWWWB   ",
        " BWWWWWWWBB ",
        "  BWWWWWWB  ",
        "   BBBBBB   ",
        "   BOOBB    ",
        "   BOOB OB  ",
        "   BBBB BB  "
    ],
    "PECK": [
        "            ",
        "            ",
        "    BBBB    ",
        "   BWWBWB   ",
        "  OBWWWB    ",
        " OOBBWB     ",
        "   BWWB     ",
        "  BWWWWB    ",
        " BWWWWWB    ",
        " BWWWWWWB   ",
        " BWWWWWWWBB ",
        "  BWWWWWWB  ",
        "   BBBBBB   ",
        "   BOOBB    ",
        "   BOOB OB  ",
        "   BBBB BB  "
    ],
    "QUACK_HOP": [
        "    BBBB    ",
        "   BWWBWB   ",
        "  OBWWWB    ",
        "   BBWB     ",
        " OO BWWB    ",
        "   BWWB     ",
        "  BWWWWB B  ",
        " BWWWWWWBB  ",
        " BWWWWWWB   ",
        " BWWWWWWWBB ",
        "  BWWWWWWB  ",
        "   BBBBBB   ",
        "   BOOBB    ",
        "   BOOB OB  ",
        "   BBBB BB  ",
        "            "
    ],
}


class _RECT(ctypes.Structure):
    _fields_ = [("left", wintypes.LONG), ("top", wintypes.LONG),
                ("right", wintypes.LONG), ("bottom", wintypes.LONG)]


class _MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", _RECT),
                ("rcWork", _RECT), ("dwFlags", wintypes.DWORD)]


def get_taskbar_work_area() -> Tuple[int, int, int, int]:
    """Retorna (left, top, right, bottom) del área de trabajo de la pantalla principal en Windows."""
    if sys.platform != "win32":
        return 0, 0, 1920, 1040
    try:
        user32 = ctypes.windll.user32
        info = _MONITORINFO()
        info.cbSize = ctypes.sizeof(_MONITORINFO)
        monitor = user32.MonitorFromWindow(0, 1)  # MONITOR_DEFAULTTOPRIMARY
        if monitor and user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
            work = info.rcWork
            return work.left, work.top, work.right, work.bottom
    except Exception:
        pass
    return 0, 0, 1920, 1040


class DesktopDuckPet:
    """
    Compañero Pato de Escritorio autónomo con renderizado 100% transparente en Windows.
    Sin marcos, sin cajas blancas, caminando literalmente sobre el fondo del escritorio.
    """

    def __init__(self, pixel_scale: int = 8) -> None:
        self.pixel_scale = pixel_scale  # 8px por pixel = 96x128px (~3.4 cm en pantalla)
        self.duck_w = 12 * pixel_scale
        self.duck_h = 16 * pixel_scale

        # Dimensiones de la ventana transparente (Pato + burbuja de diálogo)
        self.win_w = 260
        self.win_h = 175

        # Colores
        self.TRANS_COLOR = "#010101"  # Color croma 100% invisible en Windows
        self.BUBBLE_BG = "#13161F"
        self.BUBBLE_BORDER = "#333A4D"
        self.TEXT_COLOR = "#E2E8F0"

        # Estado y física
        self.direction = 1  # 1 = caminando hacia la derecha, -1 = hacia la izquierda
        self.state = "walking"  # "walking", "idle", "pecking", "hopping"
        self.walk_frame_idx = 0
        self.walk_frames_list = ["WALK_1", "WALK_2", "WALK_3", "WALK_4"]
        
        work_l, work_t, work_r, work_b = get_taskbar_work_area()
        self.min_x = work_l + 40
        self.max_x = work_r - self.win_w - 40
        self.pos_x = float(work_r - self.win_w - 120)
        # Apoyar exactamente los pies en la barra de tareas
        self.pos_y = float(work_b - self.win_h + 8)

        # Variables de arrastre con ratón
        self._drag_start_x = 0
        self._drag_start_y = 0
        self._is_dragging = False

        # Temporizadores de comportamiento
        self.idle_counter = 0
        self.step_speed = 4.0  # Píxeles por paso
        self.status_message = "💤 En guardia • 2 clics para entrar"
        self.status_color = "#10B981"  # Verde esmeralda por defecto

        # Inicializar Tkinter transparente
        self._init_window()
        self._load_sprites()
        self._bind_events()

    def _init_window(self) -> None:
        self.root = tk.Tk()
        self.root.title("MMAE Desktop Duck")
        self.root.overrideredirect(True)
        self.root.wm_attributes("-topmost", True)
        
        # Transparencia total en Windows (elimina por completo el recuadro blanco)
        if sys.platform == "win32":
            self.root.wm_attributes("-transparentcolor", self.TRANS_COLOR)
        
        self.root.config(bg=self.TRANS_COLOR)
        self.root.geometry(f"{self.win_w}x{self.win_h}+{int(self.pos_x)}+{int(self.pos_y)}")

        self.canvas = tk.Canvas(
            self.root,
            width=self.win_w,
            height=self.win_h,
            bg=self.TRANS_COLOR,
            highlightthickness=0,
            cursor="hand2",
        )
        self.canvas.pack(fill="both", expand=True)

    def _load_sprites(self) -> None:
        """Renderiza la biblioteca de sprites del pato en imágenes PhotoImage de Tkinter."""
        self.sprites: Dict[str, Dict[str, ImageTk.PhotoImage]] = {}

        for name, pattern in SPRITES_DATA.items():
            img = Image.new("RGBA", (12, 16), (1, 1, 1, 0))
            for r, row in enumerate(pattern):
                for c, char in enumerate(row):
                    color = PALETTE.get(char, (1, 1, 1, 0))
                    img.putpixel((c, r), color)

            # Escalar limpiamente con interpolación Nearest (Pixel-Art nítido)
            scaled_right = img.resize((self.duck_w, self.duck_h), Image.Resampling.NEAREST)
            # Reflejar para cuando camina a la derecha
            scaled_left = ImageOps.mirror(scaled_right)

            self.sprites[name] = {
                "right": ImageTk.PhotoImage(scaled_left),   # Dibujo base mira a la izquierda, mirror mira a la derecha
                "left": ImageTk.PhotoImage(scaled_right),
            }

    def _bind_events(self) -> None:
        # Arrastre con clic izquierdo
        self.canvas.bind("<Button-1>", self._on_mouse_down)
        self.canvas.bind("<B1-Motion>", self._on_mouse_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_mouse_up)

        # Doble clic para abrir el agente
        self.canvas.bind("<Double-Button-1>", self._on_double_click)

        # Clic derecho para menú contextual
        self.canvas.bind("<Button-3>", self._on_right_click)

    def _on_mouse_down(self, event: tk.Event) -> None:
        self._is_dragging = True
        self._drag_start_x = event.x
        self._drag_start_y = event.y

    def _on_mouse_drag(self, event: tk.Event) -> None:
        if self._is_dragging:
            dx = event.x - self._drag_start_x
            dy = event.y - self._drag_start_y
            self.pos_x += dx
            self.pos_y += dy
            self.root.geometry(f"{self.win_w}x{self.win_h}+{int(self.pos_x)}+{int(self.pos_y)}")

    def _on_mouse_up(self, event: tk.Event) -> None:
        self._is_dragging = False

    def _on_double_click(self, event: tk.Event) -> None:
        """Reacción física de salto y apertura del agente."""
        self.state = "hopping"
        self.status_message = "¡CUAC! 🚀 Abriendo agente..."
        self.status_color = "#FF5500"
        self._draw_frame()

        # Invocar apertura en un hilo desacoplado
        threading.Thread(target=self._launch_or_focus_agent, daemon=True).start()

    def _on_right_click(self, event: tk.Event) -> None:
        menu = tk.Menu(self.root, tearoff=0)
        menu.add_command(label="🚀 Abrir Agente JEV", command=self._launch_or_focus_agent)
        menu.add_command(label="🦆 Picotear Suelo", command=lambda: setattr(self, "state", "pecking"))
        menu.add_separator()
        menu.add_command(label="❌ Cerrar Pato", command=self.root.destroy)
        menu.post(event.x_root, event.y_root)

    def _launch_or_focus_agent(self) -> None:
        """Restaura la ventana existente o lanza app.py / jev_launcher.py."""
        log.info("🦆 [DesktopDuck]: Doble clic detectado. Enfocando interfaz principal...")

        # 1. Buscar si la ventana ya existe en Windows y traerla al frente
        if sys.platform == "win32":
            try:
                found_hwnd = None
                def _enum_win(h, _):
                    nonlocal found_hwnd
                    if ctypes.windll.user32.IsWindowVisible(h):
                        length = ctypes.windll.user32.GetWindowTextLengthW(h)
                        if length > 0:
                            buff = ctypes.create_unicode_buffer(length + 1)
                            ctypes.windll.user32.GetWindowTextW(h, buff, length + 1)
                            title = buff.value
                            if "MMAE" in title or "JARVIS" in title or "Bable" in title:
                                found_hwnd = h
                                return False
                    return True

                WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
                ctypes.windll.user32.EnumWindows(WNDENUMPROC(_enum_win), 0)

                if found_hwnd:
                    ctypes.windll.user32.ShowWindow(found_hwnd, 9)  # SW_RESTORE
                    ctypes.windll.user32.SetForegroundWindow(found_hwnd)
                    ctypes.windll.user32.BringWindowToTop(found_hwnd)
                    return
            except Exception:
                pass

        # 2. Si no está abierta, lanzarla
        try:
            launcher_script = BASE_DIR / "jev_launcher.py"
            app_script = BASE_DIR / "app.py"
            py_bin = sys.executable or "python.exe"

            cmd = [py_bin, str(launcher_script), "--classic"] if launcher_script.exists() else [py_bin, str(app_script)]
            DETACHED = 0x00000008 | 0x00000200
            subprocess.Popen(
                cmd,
                cwd=str(BASE_DIR),
                creationflags=DETACHED if sys.platform == "win32" else 0,
                close_fds=True,
            )
        except Exception as e:
            log.error(f"Error al abrir agente: {e}")

    def _draw_frame(self) -> None:
        """Dibuja en el Canvas el pato y la burbuja de estado flotante."""
        self.canvas.delete("all")

        # 1. Dibujar burbuja de diálogo redondeada con sombra
        bubble_x1 = 20
        bubble_y1 = 6
        bubble_x2 = self.win_w - 20
        bubble_y2 = 38
        r = 10

        # Fondo de la burbuja
        self.canvas.create_rectangle(
            bubble_x1 + r, bubble_y1, bubble_x2 - r, bubble_y2,
            fill=self.BUBBLE_BG, outline=""
        )
        self.canvas.create_rectangle(
            bubble_x1, bubble_y1 + r, bubble_x2, bubble_y2 - r,
            fill=self.BUBBLE_BG, outline=""
        )
        self.canvas.create_oval(bubble_x1, bubble_y1, bubble_x1 + 2*r, bubble_y1 + 2*r, fill=self.BUBBLE_BG, outline="")
        self.canvas.create_oval(bubble_x2 - 2*r, bubble_y1, bubble_x2, bubble_y1 + 2*r, fill=self.BUBBLE_BG, outline="")
        self.canvas.create_oval(bubble_x1, bubble_y2 - 2*r, bubble_x1 + 2*r, bubble_y2, fill=self.BUBBLE_BG, outline="")
        self.canvas.create_oval(bubble_x2 - 2*r, bubble_y2 - 2*r, bubble_x2, bubble_y2, fill=self.BUBBLE_BG, outline="")

        # Borde exterior fino
        self.canvas.create_arc(bubble_x1, bubble_y1, bubble_x1 + 2*r, bubble_y1 + 2*r, start=90, extent=90, outline=self.BUBBLE_BORDER, style="arc", width=1)
        self.canvas.create_arc(bubble_x2 - 2*r, bubble_y1, bubble_x2, bubble_y1 + 2*r, start=0, extent=90, outline=self.BUBBLE_BORDER, style="arc", width=1)
        self.canvas.create_arc(bubble_x1, bubble_y2 - 2*r, bubble_x1 + 2*r, bubble_y2, start=180, extent=90, outline=self.BUBBLE_BORDER, style="arc", width=1)
        self.canvas.create_arc(bubble_x2 - 2*r, bubble_y2 - 2*r, bubble_x2, bubble_y2, start=270, extent=90, outline=self.BUBBLE_BORDER, style="arc", width=1)
        self.canvas.create_line(bubble_x1 + r, bubble_y1, bubble_x2 - r, bubble_y1, fill=self.BUBBLE_BORDER, width=1)
        self.canvas.create_line(bubble_x1 + r, bubble_y2, bubble_x2 - r, bubble_y2, fill=self.BUBBLE_BORDER, width=1)
        self.canvas.create_line(bubble_x1, bubble_y1 + r, bubble_x1, bubble_y2 - r, fill=self.BUBBLE_BORDER, width=1)
        self.canvas.create_line(bubble_x2, bubble_y1 + r, bubble_x2, bubble_y2 - r, fill=self.BUBBLE_BORDER, width=1)

        # Pequeño triángulo apuntando al pato
        tri_x = (bubble_x1 + bubble_x2) // 2
        self.canvas.create_polygon(
            tri_x - 5, bubble_y2,
            tri_x + 5, bubble_y2,
            tri_x, bubble_y2 + 5,
            fill=self.BUBBLE_BG, outline=""
        )

        # Punto indicador de estado
        self.canvas.create_oval(
            bubble_x1 + 12, bubble_y1 + 12, bubble_x1 + 20, bubble_y1 + 20,
            fill=self.status_color, outline=""
        )

        # Texto del estado
        display_text = self.status_message
        if len(display_text) > 30:
            display_text = display_text[:27] + "..."
        self.canvas.create_text(
            bubble_x1 + 26, (bubble_y1 + bubble_y2) // 2,
            text=display_text,
            anchor="w",
            fill=self.TEXT_COLOR,
            font=("Segoe UI", 9, "bold")
        )

        # 2. Determinar sprite actual del Pato
        dir_key = "right" if self.direction == 1 else "left"
        sprite_name = "STAND"

        duck_draw_y = 42

        if self.state == "walking":
            sprite_name = self.walk_frames_list[self.walk_frame_idx]
            # Leve bamboleo vertical al caminar
            if self.walk_frame_idx in (1, 3):
                duck_draw_y -= 2
        elif self.state == "pecking":
            sprite_name = "PECK"
            duck_draw_y += 3
        elif self.state == "hopping":
            sprite_name = "QUACK_HOP"
            duck_draw_y -= 12
        elif self.state == "idle":
            if self.idle_counter % 20 in (18, 19):
                sprite_name = "BLINK"
            else:
                sprite_name = "STAND"

        img = self.sprites[sprite_name][dir_key]
        duck_center_x = self.win_w // 2
        self.canvas.create_image(duck_center_x, duck_draw_y + (self.duck_h // 2), image=img)

    def _update_loop(self) -> None:
        """Bucle de animación y física de caminata (60-120ms por frame)."""
        if not self._is_dragging:
            if self.state == "walking":
                # Avanzar físicamente en la pantalla
                self.pos_x += self.direction * self.step_speed
                self.walk_frame_idx = (self.walk_frame_idx + 1) % len(self.walk_frames_list)

                # Si llega al borde de la pantalla, cambiar de dirección y pausar
                if self.pos_x >= self.max_x:
                    self.pos_x = self.max_x
                    self.direction = -1
                    self.state = "idle"
                    self.idle_counter = 0
                elif self.pos_x <= self.min_x:
                    self.pos_x = self.min_x
                    self.direction = 1
                    self.state = "idle"
                    self.idle_counter = 0

                # Cada cierto número de pasos, detenerse a descansar
                self.idle_counter += 1
                if self.idle_counter > 35:
                    self.state = "idle"
                    self.idle_counter = 0

                # Mover la ventana en Windows
                self.root.geometry(f"{self.win_w}x{self.win_h}+{int(self.pos_x)}+{int(self.pos_y)}")

            elif self.state == "idle":
                self.idle_counter += 1
                # Ocasionalmente picotea
                if self.idle_counter == 15 and (time.time() % 4 < 2):
                    self.state = "pecking"
                elif self.idle_counter > 28:
                    # Reanudar caminata
                    self.state = "walking"
                    self.idle_counter = 0
                    # 30% de probabilidad de cambiar dirección
                    if (time.time() % 3) > 1.8:
                        self.direction *= -1

            elif self.state == "pecking":
                self.idle_counter += 1
                if self.idle_counter > 8:
                    self.state = "idle"
                    self.idle_counter = 0

            elif self.state == "hopping":
                self.idle_counter += 1
                if self.idle_counter > 10:
                    self.state = "idle"
                    self.idle_counter = 0
                    self.status_message = "💤 En guardia • 2 clics para entrar"
                    self.status_color = "#10B981"

        self._draw_frame()
        # Próximo frame de animación en 130ms (cadencia perfecta para caminata de pato)
        self.root.after(130, self._update_loop)

    def _sync_agent_status_loop(self) -> None:
        """Sincroniza periódicamente el mensaje de la burbuja con el agente en segundo plano."""
        try:
            status = get_agent_status()
            if status and self.state != "hopping":
                if status.get("running") or status.get("state") == "thinking":
                    thought = status.get("thought", "")
                    self.status_message = f"🧠 {thought}" if thought else "🧠 Pensando y analizando..."
                    self.status_color = "#3B82F6"
                elif status.get("tool_in_progress") or status.get("tool"):
                    tool = status.get("tool", "herramienta")
                    self.status_message = f"⚡ Ejecutando: {tool}"
                    self.status_color = "#F59E0B"
                elif status.get("state") == "curiosity":
                    self.status_message = "🦉 Curiosidad Nivel 0 activa"
                    self.status_color = "#8B5CF6"
                elif status.get("state") == "talking":
                    self.status_message = "🔊 Hablando aviso de voz"
                    self.status_color = "#EC4899"
                else:
                    self.status_message = "💤 En guardia • 2 clics para entrar"
                    self.status_color = "#10B981"
        except Exception:
            pass

        self.root.after(1200, self._sync_agent_status_loop)

    def run(self) -> None:
        """Arranca el bucle principal de la mascota de escritorio."""
        self._update_loop()
        self._sync_agent_status_loop()
        self.root.mainloop()


def run_duck() -> int:
    """Punto de entrada principal para lanzar el Pato de Escritorio."""
    pet = DesktopDuckPet(pixel_scale=8)
    pet.run()
    return 0


__all__ = ["DesktopDuckPet", "run_duck"]
