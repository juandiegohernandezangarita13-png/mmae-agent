"""
Módulo Desktop Duck Pet (Pato de Escritorio con Física, Gravedad y Conexión Antigravity 2.0).
1. Transparencia total en Windows (sin recuadros blancos, directamente sobre el escritorio).
2. Gravedad física real: si se arrastra hacia arriba y se suelta, cae acelerando hasta su piso.
3. El piso es la barra de tareas de Windows.
4. Doble clic abre o enfoca de inmediato la interfaz de Antigravity 2.0 / JARVIS (app.py).
5. Ciclo de caminata animado paso a paso con patas alternadas y aleteo en el aire.
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

# Paleta de colores pixel-art fiel a la imagen
PALETTE = {
    ' ': (1, 1, 1, 0),         # Color clave transparente (#010101)
    'B': (15, 15, 20, 255),    # Negro contorno nítido
    'W': (255, 255, 255, 255),# Blanco plumaje puro
    'S': (220, 226, 238, 255),# Sombra plumaje
    'O': (255, 80, 0, 255),    # Naranja pico y patas
    'D': (210, 55, 0, 255),    # Naranja oscuro
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
    "FLAP": [
        "    BBBB    ",
        "   BWWBWB   ",
        "  OBWWWB    ",
        " OOBBWB     ",
        "   BWWB     ",
        " B BWWB B   ",
        " BBWWWWB BB ",
        "  BWWWWBB   ",
        " BWWWWWWB   ",
        " BWWWWWWWBB ",
        "  BWWWWWWB  ",
        "   BBBBBB   ",
        "    BOOB    ",
        "    BOOB    ",
        "    BBBB    ",
        "            "
    ],
    "SQUASH": [
        "            ",
        "            ",
        "    BBBB    ",
        "   BWWBWB   ",
        "  OBWWWB    ",
        " OOBBWB     ",
        "   BWWB     ",
        "  BWWWWB    ",
        " BWWWWWWB   ",
        " BWWWWWWWBB ",
        "  BWWWWWWB  ",
        "  BBBBBBBB  ",
        " BOOB  BOOB ",
        " BOOB  BOOB ",
        " BBBB  BBBB ",
        "            "
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
    """Retorna (left, top, right, bottom) del área de trabajo (descuenta la barra de tareas en Windows)."""
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
    Pato de Escritorio animado con física de gravedad, piso real y lanzamiento de Antigravity 2.0.
    """

    def __init__(self, pixel_scale: int = 8) -> None:
        self.pixel_scale = pixel_scale  # 8px por pixel = 96x128px (~3.4 cm)
        self.duck_w = 12 * pixel_scale
        self.duck_h = 16 * pixel_scale

        # Dimensiones de la ventana transparente
        self.win_w = 260
        self.win_h = 175

        # Colores
        self.TRANS_COLOR = "#010101"  # Color croma 100% invisible en Windows
        self.BUBBLE_BG = "#13161F"
        self.BUBBLE_BORDER = "#333A4D"
        self.TEXT_COLOR = "#E2E8F0"

        # Física de Gravedad y Piso
        work_l, work_t, work_r, work_b = get_taskbar_work_area()
        self.min_x = work_l + 30
        self.max_x = work_r - self.win_w - 30

        # El piso físico exacto: la parte superior de la barra de tareas
        self.floor_y = float(work_b - self.win_h + 8)

        # Posición actual
        self.pos_x = float(work_r - self.win_w - 140)
        self.pos_y = self.floor_y

        # Dinámica de caída libre
        self.velocity_y = 0.0
        self.gravity = 3.6  # Aceleración gravitacional en píxeles/frame^2
        self.is_falling = False
        self.landing_timer = 0

        # Estado y animación
        self.direction = 1  # 1 = caminando a la derecha, -1 = a la izquierda
        self.state = "walking"  # "walking", "idle", "pecking", "hopping", "dragging", "falling", "landing"
        self.walk_frame_idx = 0
        self.walk_frames_list = ["WALK_1", "WALK_2", "WALK_3", "WALK_4"]

        # Variables de arrastre con ratón
        self._drag_start_x = 0
        self._drag_start_y = 0
        self._is_dragging = False
        self._is_launching = False

        # Temporizadores de comportamiento
        self.idle_counter = 0
        self.step_speed = 4.0
        self.status_message = "💤 En guardia • 2 clics para entrar"
        self.status_color = "#10B981"

        # Inicializar Tkinter transparente
        self._init_window()
        self._load_sprites()
        self._bind_events()

    def _init_window(self) -> None:
        self.root = tk.Tk()
        self.root.title("MMAE Desktop Duck")
        self.root.overrideredirect(True)
        self.root.wm_attributes("-topmost", True)

        # Transparencia por hardware en Windows
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
        """Renderiza los patrones a PhotoImages de Tkinter."""
        self.sprites: Dict[str, Dict[str, ImageTk.PhotoImage]] = {}

        for name, pattern in SPRITES_DATA.items():
            img = Image.new("RGBA", (12, 16), (1, 1, 1, 0))
            for r, row in enumerate(pattern):
                for c, char in enumerate(row):
                    color = PALETTE.get(char, (1, 1, 1, 0))
                    img.putpixel((c, r), color)

            # Escalar nítido
            scaled_right = img.resize((self.duck_w, self.duck_h), Image.Resampling.NEAREST)
            scaled_left = ImageOps.mirror(scaled_right)

            self.sprites[name] = {
                "right": ImageTk.PhotoImage(scaled_left),
                "left": ImageTk.PhotoImage(scaled_right),
            }

    def _bind_events(self) -> None:
        # Clic y arrastre
        self.canvas.bind("<Button-1>", self._on_mouse_down)
        self.canvas.bind("<B1-Motion>", self._on_mouse_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_mouse_up)

        # Doble clic para abrir Antigravity 2.0 / JARVIS
        self.canvas.bind("<Double-Button-1>", self._on_double_click)

        # Menú contextual
        self.canvas.bind("<Button-3>", self._on_right_click)

    def _on_mouse_down(self, event: tk.Event) -> None:
        self._is_dragging = True
        self.is_falling = False
        self.velocity_y = 0.0
        self.state = "dragging"
        self._drag_start_x = event.x
        self._drag_start_y = event.y
        self.status_message = "¡Waaa! 🦆"
        self.status_color = "#F59E0B"
        self._draw_frame()

    def _on_mouse_drag(self, event: tk.Event) -> None:
        if self._is_dragging:
            dx = event.x - self._drag_start_x
            dy = event.y - self._drag_start_y
            self.pos_x += dx
            self.pos_y += dy
            self.root.geometry(f"{self.win_w}x{self.win_h}+{int(self.pos_x)}+{int(self.pos_y)}")

    def _on_mouse_up(self, event: tk.Event) -> None:
        self._is_dragging = False

        # Si el pato quedó por encima del piso, ¡SE ACTIVA LA GRAVEDAD!
        if self.pos_y < self.floor_y:
            self.is_falling = True
            self.velocity_y = 1.0
            self.state = "falling"
            self.status_message = "¡Cayendo! 🪂"
            self.status_color = "#3B82F6"
        else:
            # Si fue arrastrado por debajo de la taskbar, apoyarlo en el piso
            self.pos_y = self.floor_y
            self.is_falling = False
            self.state = "idle"
            self.idle_counter = 0
            self.root.geometry(f"{self.win_w}x{self.win_h}+{int(self.pos_x)}+{int(self.pos_y)}")

    def _on_double_click(self, event: tk.Event) -> None:
        """Doble clic: Salto alegre '¡CUAC!' y apertura garantizada de la interfaz Antigravity 2.0."""
        self._is_dragging = False
        self.is_falling = False
        self.velocity_y = 0.0
        self.state = "hopping"
        self.status_message = "¡CUAC! 🚀 Abriendo Antigravity 2.0..."
        self.status_color = "#FF5500"
        self._draw_frame()

        if not self._is_launching:
            self._is_launching = True
            threading.Thread(target=self._launch_or_focus_agent, daemon=True).start()

    def _on_right_click(self, event: tk.Event) -> None:
        menu = tk.Menu(self.root, tearoff=0)
        menu.add_command(label="🚀 Abrir Antigravity 2.0", command=self._launch_or_focus_agent)
        menu.add_command(label="🦆 Tirar al aire (Gravedad)", command=self._throw_in_the_air)
        menu.add_separator()
        menu.add_command(label="❌ Cerrar Pato", command=self.root.destroy)
        menu.post(event.x_root, event.y_root)

    def _throw_in_the_air(self) -> None:
        """Lanza el pato hacia arriba para ver la gravedad."""
        self.pos_y = max(50.0, self.floor_y - 450.0)
        self.is_falling = True
        self.velocity_y = 1.0
        self.state = "falling"
        self.status_message = "¡Gravedad! 🪂"
        self.status_color = "#3B82F6"
        self.root.geometry(f"{self.win_w}x{self.win_h}+{int(self.pos_x)}+{int(self.pos_y)}")

    def _launch_or_focus_agent(self) -> None:
        """Enfoca la ventana de Antigravity 2.0 o la lanza mediante app.py."""
        log.info("🦆 [DesktopDuck]: Abriendo interfaz Antigravity 2.0 (app.py)...")

        # 1. Comprobar si ya existe la ventana de Antigravity 2.0 / Bable abierta
        if sys.platform == "win32":
            try:
                found_hwnd = None
                duck_hwnd = int(self.root.frame(), 16) if hasattr(self.root, "frame") else 0

                def _enum_win(h, _):
                    nonlocal found_hwnd
                    if ctypes.windll.user32.IsWindowVisible(h):
                        length = ctypes.windll.user32.GetWindowTextLengthW(h)
                        if length > 0:
                            buff = ctypes.create_unicode_buffer(length + 1)
                            ctypes.windll.user32.GetWindowTextW(h, buff, length + 1)
                            title = buff.value
                            # IGNORAR la propia ventana del pato
                            if "Desktop Duck" in title or "MMAE Desktop Duck" in title or h == duck_hwnd:
                                return True

                            # Detectar la interfaz principal de Antigravity 2.0 / Bable / JARVIS
                            if "Bable 2.0" in title or "Antigravity 2.0" in title or "MMAE // Claude" in title or "JARVIS" in title:
                                found_hwnd = h
                                return False
                    return True

                WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
                ctypes.windll.user32.EnumWindows(WNDENUMPROC(_enum_win), 0)

                if found_hwnd:
                    log.info(f"🦆 [DesktopDuck]: Ventana Antigravity encontrada (HWND {found_hwnd}). Restaurando...")
                    ctypes.windll.user32.ShowWindow(found_hwnd, 9)  # SW_RESTORE
                    ctypes.windll.user32.SetForegroundWindow(found_hwnd)
                    ctypes.windll.user32.BringWindowToTop(found_hwnd)
                    time.sleep(1.5)
                    self._is_launching = False
                    return
            except Exception as e:
                log.warning(f"Error buscando ventana existente: {e}")

        # 2. Si no está abierta, lanzar la interfaz mediante jev_launcher.py --classic o app.py
        try:
            # Resolver intérprete de Python seguro
            py_bin = sys.executable or "python.exe"
            known_py = Path(r"C:\Users\juand\AppData\Roaming\uv\python\cpython-3.11.16-windows-x86_64-none\python.exe")
            if (not Path(py_bin).exists() or "WindowsApps" in str(py_bin)) and known_py.exists():
                py_bin = str(known_py)

            launcher_script = BASE_DIR / "jev_launcher.py"
            if launcher_script.exists():
                cmd = [py_bin, str(launcher_script), "--classic"]
            else:
                cmd = [py_bin, str(BASE_DIR / "app.py")]

            DETACHED = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
            log.info(f"🦆 [DesktopDuck]: Lanzando proceso: {' '.join(cmd)}")
            proc = subprocess.Popen(
                cmd,
                cwd=str(BASE_DIR),
                creationflags=DETACHED if sys.platform == "win32" else 0,
                close_fds=True,
            )
            log.info(f"🦆 [DesktopDuck]: Proceso Antigravity 2.0 iniciado (PID {proc.pid}).")
        except Exception as e:
            log.error(f"Error al abrir la interfaz: {e}")
        finally:
            time.sleep(2.0)
            self._is_launching = False

    def _draw_frame(self) -> None:
        """Dibuja en el Canvas el pato y la burbuja de estado flotante."""
        self.canvas.delete("all")

        # 1. Dibujar burbuja de diálogo
        bubble_x1 = 20
        bubble_y1 = 6
        bubble_x2 = self.win_w - 20
        bubble_y2 = 38
        r = 10

        self.canvas.create_rectangle(bubble_x1 + r, bubble_y1, bubble_x2 - r, bubble_y2, fill=self.BUBBLE_BG, outline="")
        self.canvas.create_rectangle(bubble_x1, bubble_y1 + r, bubble_x2, bubble_y2 - r, fill=self.BUBBLE_BG, outline="")
        self.canvas.create_oval(bubble_x1, bubble_y1, bubble_x1 + 2*r, bubble_y1 + 2*r, fill=self.BUBBLE_BG, outline="")
        self.canvas.create_oval(bubble_x2 - 2*r, bubble_y1, bubble_x2, bubble_y1 + 2*r, fill=self.BUBBLE_BG, outline="")
        self.canvas.create_oval(bubble_x1, bubble_y2 - 2*r, bubble_x1 + 2*r, bubble_y2, fill=self.BUBBLE_BG, outline="")
        self.canvas.create_oval(bubble_x2 - 2*r, bubble_y2 - 2*r, bubble_x2, bubble_y2, fill=self.BUBBLE_BG, outline="")

        # Bordes
        self.canvas.create_arc(bubble_x1, bubble_y1, bubble_x1 + 2*r, bubble_y1 + 2*r, start=90, extent=90, outline=self.BUBBLE_BORDER, style="arc", width=1)
        self.canvas.create_arc(bubble_x2 - 2*r, bubble_y1, bubble_x2, bubble_y1 + 2*r, start=0, extent=90, outline=self.BUBBLE_BORDER, style="arc", width=1)
        self.canvas.create_arc(bubble_x1, bubble_y2 - 2*r, bubble_x1 + 2*r, bubble_y2, start=180, extent=90, outline=self.BUBBLE_BORDER, style="arc", width=1)
        self.canvas.create_arc(bubble_x2 - 2*r, bubble_y2 - 2*r, bubble_x2, bubble_y2, start=270, extent=90, outline=self.BUBBLE_BORDER, style="arc", width=1)
        self.canvas.create_line(bubble_x1 + r, bubble_y1, bubble_x2 - r, bubble_y1, fill=self.BUBBLE_BORDER, width=1)
        self.canvas.create_line(bubble_x1 + r, bubble_y2, bubble_x2 - r, bubble_y2, fill=self.BUBBLE_BORDER, width=1)
        self.canvas.create_line(bubble_x1, bubble_y1 + r, bubble_x1, bubble_y2 - r, fill=self.BUBBLE_BORDER, width=1)
        self.canvas.create_line(bubble_x2, bubble_y1 + r, bubble_x2, bubble_y2 - r, fill=self.BUBBLE_BORDER, width=1)

        # Flecha indicadora
        tri_x = (bubble_x1 + bubble_x2) // 2
        self.canvas.create_polygon(tri_x - 5, bubble_y2, tri_x + 5, bubble_y2, tri_x, bubble_y2 + 5, fill=self.BUBBLE_BG, outline="")

        # Punto de estado
        self.canvas.create_oval(bubble_x1 + 12, bubble_y1 + 12, bubble_x1 + 20, bubble_y1 + 20, fill=self.status_color, outline="")

        # Texto
        display_text = self.status_message
        if len(display_text) > 30:
            display_text = display_text[:27] + "..."
        self.canvas.create_text(bubble_x1 + 26, (bubble_y1 + bubble_y2) // 2, text=display_text, anchor="w", fill=self.TEXT_COLOR, font=("Segoe UI", 9, "bold"))

        # 2. Sprite actual del Pato
        dir_key = "right" if self.direction == 1 else "left"
        sprite_name = "STAND"
        duck_draw_y = 42

        if self.state in ("dragging", "falling"):
            sprite_name = "FLAP"
            duck_draw_y -= 4
        elif self.state == "landing":
            sprite_name = "SQUASH"
            duck_draw_y += 6
        elif self.state == "walking":
            sprite_name = self.walk_frames_list[self.walk_frame_idx]
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
        """Bucle principal de física, gravedad y caminata."""
        if not self._is_dragging:
            # --- FÍSICA DE GRAVEDAD ---
            if self.is_falling:
                self.velocity_y += self.gravity
                self.pos_y += self.velocity_y

                # Colisión con el piso físico (barra de tareas)
                if self.pos_y >= self.floor_y:
                    self.pos_y = self.floor_y
                    self.is_falling = False
                    self.velocity_y = 0.0
                    self.state = "landing"
                    self.landing_timer = 3
                    self.status_message = "¡Plaf! 🦆"
                    self.status_color = "#10B981"

                self.root.geometry(f"{self.win_w}x{self.win_h}+{int(self.pos_x)}+{int(self.pos_y)}")

            elif self.state == "landing":
                self.landing_timer -= 1
                if self.landing_timer <= 0:
                    self.state = "idle"
                    self.idle_counter = 0
                    self.status_message = "💤 En guardia • 2 clics para entrar"
                    self.status_color = "#10B981"

            elif self.state == "walking":
                # Caminata horizontal sobre el piso
                self.pos_x += self.direction * self.step_speed
                self.walk_frame_idx = (self.walk_frame_idx + 1) % len(self.walk_frames_list)

                # Rebote en los bordes de la pantalla
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

                self.idle_counter += 1
                if self.idle_counter > 35:
                    self.state = "idle"
                    self.idle_counter = 0

                self.root.geometry(f"{self.win_w}x{self.win_h}+{int(self.pos_x)}+{int(self.pos_y)}")

            elif self.state == "idle":
                self.idle_counter += 1
                if self.idle_counter == 15 and (time.time() % 4 < 2):
                    self.state = "pecking"
                elif self.idle_counter > 28:
                    self.state = "walking"
                    self.idle_counter = 0
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
        # Cadencia de 80ms para caída suave y 120ms para caminata
        tick_interval = 50 if self.is_falling else 125
        self.root.after(tick_interval, self._update_loop)

    def _sync_agent_status_loop(self) -> None:
        """Sincroniza periódicamente el mensaje de la burbuja."""
        try:
            status = get_agent_status()
            if status and self.state not in ("hopping", "dragging", "falling"):
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
    pet = DesktopDuckPet(pixel_scale=8)
    pet.run()
    return 0


__all__ = ["DesktopDuckPet", "run_duck"]
