"""
Módulo Desktop Duck Pet (Pato de Escritorio con Física, Colisiones con Ventanas y Animaciones Completas).
Inspirado en los sprites originales del usuario (25 frames de pixel-art):
1. Animaciones completas:
   - Caminata fluida de 6 fases (walk_1 .. walk_6).
   - Choque contra ventanas (BONK con pico aplastado contra la pared).
   - Mareo y estrellas (dizzy_1, dizzy_2, ko_feet_1, ko_feet_2 con pataleo al revés).
   - Caída y giros en el aire (tumble_1 .. tumble_4, flap_1 .. flap_3).
   - Descanso y aseo (idle_stand, idle_sit, sit_flat, groom, peck, alert).
2. Detección física de ventanas abiertas de Windows:
   - El pato choca de frente contra los bordes laterales de las ventanas abiertas (¡BONK!), se marea y da media vuelta.
   - Si cae sobre una ventana, la usa como plataforma y camina por encima de ella.
   - Si llega al borde de la ventana, cae por gravedad hasta la barra de tareas.
3. Transparencia de hardware DWM en Windows (-transparentcolor #010101).
4. Doble clic abre o restaura la interfaz de Antigravity 2.0 / JARVIS (app.py).
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

try:
    import win32gui
except ImportError:
    win32gui = None

ASSETS_DIR = BASE_DIR / "jev" / "ui" / "assets" / "duck"


class _RECT(ctypes.Structure):
    _fields_ = [
        ("left", wintypes.LONG),
        ("top", wintypes.LONG),
        ("right", wintypes.LONG),
        ("bottom", wintypes.LONG)
    ]


class _MONITORINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", _RECT),
        ("rcWork", _RECT),
        ("dwFlags", wintypes.DWORD)
    ]


def get_taskbar_work_area() -> Tuple[int, int, int, int]:
    """Retorna (left, top, right, bottom) del área de trabajo disponible (descuenta la barra de tareas)."""
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
    Pato de Escritorio autónomo con animaciones completas, colisiones con ventanas de Windows
    y física de gravedad interactiva.
    """

    def __init__(self, target_height: int = 118) -> None:
        self.target_height = target_height  # ~118 px = ~3.4 cm en pantalla
        self.scale_factor = target_height / 165.0

        # Dimensiones de la ventana transparente del pato
        self.win_w = 260
        self.win_h = 175

        # Colores de interfaz
        self.TRANS_COLOR = "#010101"  # Croma 100% transparente en Windows
        self.BUBBLE_BG = "#13161F"
        self.BUBBLE_BORDER = "#333A4D"
        self.TEXT_COLOR = "#E2E8F0"

        # Área de trabajo y límites de pantalla
        work_l, work_t, work_r, work_b = get_taskbar_work_area()
        self.screen_left = work_l
        self.screen_top = work_t
        self.screen_right = work_r
        self.screen_bottom = work_b

        self.min_x = work_l + 10
        self.max_x = work_r - self.win_w - 10

        # Piso natural: barra de tareas de Windows
        self.taskbar_floor_y = float(work_b - self.win_h + 8)
        self.current_floor_y = self.taskbar_floor_y

        # Posición y dinámica
        self.pos_x = float(work_r - self.win_w - 160)
        self.pos_y = self.taskbar_floor_y
        self.velocity_y = 0.0
        self.gravity = 3.8
        self.is_falling = False

        # Estado de animación y comportamiento
        self.direction = 1  # 1 = caminando derecha, -1 = izquierda
        self.state = "walking"  # "walking", "bonk", "dizzy", "alert", "idle", "pecking", "grooming", "dragging", "falling", "landing", "hopping"
        self.anim_frame = 0
        self.step_speed = 3.6

        # Temporizadores de estados
        self.state_timer = 0
        self.idle_counter = 0
        self.bonk_cooldown = 0  # Evita choques en bucle infinito en el mismo píxel

        # Caché de ventanas para colisiones
        self._cached_windows: List[Tuple[int, int, int, int]] = []
        self._last_win_scan = 0.0

        # Mensaje de estado
        self.status_message = "💤 En guardia • 2 clics para entrar"
        self.status_color = "#10B981"

        # Variables de arrastre
        self._is_dragging = False
        self._drag_start_x = 0
        self._drag_start_y = 0
        self._is_launching = False

        # Listas de frames para animaciones
        self.walk_frames = ["WALK_1", "WALK_2", "WALK_3", "WALK_4", "WALK_5", "WALK_6"]
        self.flap_frames = ["FLAP_1", "FLAP_2", "FLAP_3", "FLAP_2"]
        self.tumble_frames = ["TUMBLE_1", "TUMBLE_2", "TUMBLE_3", "TUMBLE_4"]
        self.dizzy_frames = ["DIZZY_1", "DIZZY_2", "KO_FEET_1", "KO_FEET_2"]

        # Inicialización
        self._init_window()
        self._load_all_sprites()
        self._bind_events()

    def _init_window(self) -> None:
        self.root = tk.Tk()
        self.root.title("MMAE Desktop Duck")
        self.root.overrideredirect(True)
        self.root.wm_attributes("-topmost", True)

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

    def _load_all_sprites(self) -> None:
        """Carga y procesa todos los sprites extraídos de la hoja de sprites original."""
        self.sprites: Dict[str, Dict[str, ImageTk.PhotoImage]] = {}
        self.sprite_sizes: Dict[str, Tuple[int, int]] = {}

        if ASSETS_DIR.is_dir():
            for p in ASSETS_DIR.glob("*.png"):
                name = p.stem.upper()
                try:
                    img = Image.open(p).convert("RGBA")
                    w, h = img.size
                    nw = max(1, int(w * self.scale_factor))
                    nh = max(1, int(h * self.scale_factor))
                    scaled = img.resize((nw, nh), Image.Resampling.NEAREST)

                    # Reemplazar transparencia con la clave de croma #010101
                    bg = Image.new("RGBA", (nw, nh), (1, 1, 1, 255))
                    comp = Image.alpha_composite(bg, scaled).convert("RGB")

                    right = ImageTk.PhotoImage(comp)
                    left = ImageTk.PhotoImage(ImageOps.mirror(comp))

                    self.sprites[name] = {"right": right, "left": left}
                    self.sprite_sizes[name] = (nw, nh)
                except Exception as e:
                    log.warning(f"Error cargando sprite {p.name}: {e}")

        # Fallback si falta algún sprite básico
        if "STAND" not in self.sprites and "IDLE_STAND" in self.sprites:
            self.sprites["STAND"] = self.sprites["IDLE_STAND"]
            self.sprite_sizes["STAND"] = self.sprite_sizes["IDLE_STAND"]

        log.info(f"🦆 [DesktopDuck]: {len(self.sprites)} sprites cargados listos para animación.")

    def _bind_events(self) -> None:
        self.canvas.bind("<Button-1>", self._on_mouse_down)
        self.canvas.bind("<B1-Motion>", self._on_mouse_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_mouse_up)
        self.canvas.bind("<Double-Button-1>", self._on_double_click)
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

        # Si el pato quedó por encima del piso, ¡se activa la gravedad!
        if self.pos_y < self.taskbar_floor_y:
            self.is_falling = True
            self.velocity_y = 1.0
            self.state = "falling"
            self.status_message = "¡Cayendo! 🪂"
            self.status_color = "#3B82F6"
        else:
            self.pos_y = self.taskbar_floor_y
            self.current_floor_y = self.taskbar_floor_y
            self.is_falling = False
            self.state = "idle"
            self.idle_counter = 0
            self.root.geometry(f"{self.win_w}x{self.win_h}+{int(self.pos_x)}+{int(self.pos_y)}")

    def _on_double_click(self, event: tk.Event) -> None:
        """Doble clic: Salto alegre '¡CUAC!' y apertura garantizada de Antigravity 2.0."""
        self._is_dragging = False
        self.is_falling = False
        self.velocity_y = 0.0
        self.state = "hopping"
        self.anim_frame = 0
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
        menu.add_command(label="💥 Simular Choque (¡Bonk!)", command=self._trigger_bonk_manual)
        menu.add_separator()
        menu.add_command(label="❌ Cerrar Pato", command=self.root.destroy)
        menu.post(event.x_root, event.y_root)

    def _throw_in_the_air(self) -> None:
        self.pos_y = max(50.0, self.taskbar_floor_y - 450.0)
        self.is_falling = True
        self.velocity_y = 1.0
        self.state = "falling"
        self.status_message = "¡Gravedad! 🪂"
        self.status_color = "#3B82F6"
        self.root.geometry(f"{self.win_w}x{self.win_h}+{int(self.pos_x)}+{int(self.pos_y)}")

    def _trigger_bonk_manual(self) -> None:
        """Fuerza la animación de choque contra pared y mareo."""
        self.state = "bonk"
        self.state_timer = 4
        self.status_message = "¡BONK! 💥"
        self.status_color = "#EF4444"
        self.pos_x -= self.direction * 12
        self.root.geometry(f"{self.win_w}x{self.win_h}+{int(self.pos_x)}+{int(self.pos_y)}")

    def _scan_visible_windows(self) -> List[Tuple[int, int, int, int]]:
        """
        Escanea las ventanas visibles abiertas en el escritorio de Windows con las que el pato
        puede colisionar o usar como plataformas.
        """
        now = time.time()
        # Escanear cada 0.8s para 0% consumo de CPU
        if now - self._last_win_scan < 0.8 and self._cached_windows:
            return self._cached_windows

        self._last_win_scan = now
        windows: List[Tuple[int, int, int, int]] = []
        if sys.platform != "win32":
            return windows

        duck_hwnd = int(self.root.frame(), 16) if hasattr(self.root, "frame") else 0

        # Opción 1: win32gui si está disponible
        if win32gui:
            def _win_enum(h, _):
                if h == duck_hwnd or not win32gui.IsWindowVisible(h) or win32gui.IsIconic(h):
                    return True
                cls = win32gui.GetClassName(h)
                if cls in ("Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd"):
                    return True
                title = win32gui.GetWindowText(h)
                if not title.strip() or "Desktop Duck" in title or "MMAE Desktop Duck" in title:
                    return True
                rect = win32gui.GetWindowRect(h)
                w = rect[2] - rect[0]
                h_len = rect[3] - rect[1]
                # Ventana con dimensiones reales
                if 220 <= w <= 3840 and 150 <= h_len <= 2160:
                    windows.append(rect)
                return True

            try:
                win32gui.EnumWindows(_win_enum, None)
            except Exception:
                pass

        # Opción 2: Ventana en primer plano activa vía ctypes
        try:
            user32 = ctypes.windll.user32
            fg = user32.GetForegroundWindow()
            if fg and fg != duck_hwnd and user32.IsWindowVisible(fg) and not user32.IsIconic(fg):
                rc = _RECT()
                if user32.GetWindowRect(fg, ctypes.byref(rc)):
                    w = rc.right - rc.left
                    h = rc.bottom - rc.top
                    if 220 <= w <= 3840 and 150 <= h <= 2160:
                        fg_rect = (rc.left, rc.top, rc.right, rc.bottom)
                        if fg_rect not in windows:
                            windows.append(fg_rect)
        except Exception:
            pass

        self._cached_windows = windows
        return windows

    def _check_window_collision(self) -> bool:
        """
        Verifica si el pato ha chocado de frente contra el lateral de una ventana abierta.
        """
        if self.bonk_cooldown > 0:
            self.bonk_cooldown -= 1
            return False

        windows = self._scan_visible_windows()
        if not windows:
            return False

        # Coordenadas visuales del cuerpo del pato en la pantalla
        duck_center_x = self.pos_x + (self.win_w / 2)
        duck_feet_y = self.pos_y + 160
        duck_head_y = self.pos_y + 45

        for (wl, wt, wr, wb) in windows:
            # Debe haber solapamiento vertical con la ventana
            if not (duck_feet_y > wt + 15 and duck_head_y < wb - 15):
                continue

            # 1. Caminando hacia la derecha (choca contra el borde IZQUIERDO de la ventana)
            if self.direction == 1:
                duck_beak_x = duck_center_x + 36
                if wl - 12 <= duck_beak_x <= wl + 18:
                    log.info("🦆💥 [DesktopDuck]: ¡BONK! Choque contra borde izquierdo de ventana.")
                    self.state = "bonk"
                    self.state_timer = 4
                    self.status_message = "¡BONK! 💥"
                    self.status_color = "#EF4444"
                    self.pos_x = wl - (self.win_w / 2) - 34
                    self.bonk_cooldown = 15
                    return True

            # 2. Caminando hacia la izquierda (choca contra el borde DERECHO de la ventana)
            elif self.direction == -1:
                duck_beak_x = duck_center_x - 36
                if wr - 18 <= duck_beak_x <= wr + 12:
                    log.info("🦆💥 [DesktopDuck]: ¡BONK! Choque contra borde derecho de ventana.")
                    self.state = "bonk"
                    self.state_timer = 4
                    self.status_message = "¡BONK! 💥"
                    self.status_color = "#EF4444"
                    self.pos_x = wr - (self.win_w / 2) + 34
                    self.bonk_cooldown = 15
                    return True

        return False

    def _find_highest_floor(self) -> float:
        """
        Calcula el piso más alto debajo del pato (la barra de tareas o la parte superior de una ventana).
        Permite al pato usar las ventanas abiertas como plataformas.
        """
        highest_floor = self.taskbar_floor_y
        duck_center_x = self.pos_x + (self.win_w / 2)

        for (wl, wt, wr, wb) in self._scan_visible_windows():
            # Si el pato está horizontalmente sobre la ventana
            if wl - 15 <= duck_center_x <= wr + 15:
                window_top_floor = float(wt - self.win_h + 12)
                # Solo válida si está por encima de la barra de tareas y el pato está encima de ella
                if 60 <= window_top_floor < highest_floor:
                    # Si el pato está cayendo o caminando sobre ella
                    if self.pos_y <= window_top_floor + 18:
                        highest_floor = window_top_floor

        return highest_floor

    def _launch_or_focus_agent(self) -> None:
        """Enfoca la ventana de Antigravity 2.0 o la lanza mediante jev_launcher.py --classic / app.py."""
        log.info("🦆 [DesktopDuck]: Abriendo interfaz Antigravity 2.0 (app.py)...")

        # 1. Comprobar si ya existe la ventana abierta
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
                            # IGNORAR la ventana del propio pato
                            if "Desktop Duck" in title or "MMAE Desktop Duck" in title or h == duck_hwnd:
                                return True

                            # Detectar la interfaz de Antigravity / Bable / JARVIS
                            if any(k in title for k in ("Bable 2.0", "Antigravity 2.0", "MMAE // Claude", "JARVIS")):
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

        # 2. Si no está abierta, lanzar mediante jev_launcher.py --classic
        try:
            py_bin = sys.executable or "python.exe"
            known_py = Path(r"C:\Users\juand\AppData\Roaming\uv\python\cpython-3.11.16-windows-x86_64-none\python.exe")
            if (not Path(py_bin).exists() or "WindowsApps" in str(py_bin)) and known_py.exists():
                py_bin = str(known_py)

            launcher_script = BASE_DIR / "jev_launcher.py"
            cmd = [py_bin, str(launcher_script), "--classic"] if launcher_script.exists() else [py_bin, str(BASE_DIR / "app.py")]

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
        """Dibuja en el Canvas el pato con su sprite correspondiente y la burbuja de estado."""
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

        # Bordes de burbuja
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

        # Texto de estado
        display_text = self.status_message
        if len(display_text) > 30:
            display_text = display_text[:27] + "..."
        self.canvas.create_text(bubble_x1 + 26, (bubble_y1 + bubble_y2) // 2, text=display_text, anchor="w", fill=self.TEXT_COLOR, font=("Segoe UI", 9, "bold"))

        # 2. Selección del Sprite según el estado actual
        dir_key = "right" if self.direction == 1 else "left"
        sprite_name = "IDLE_STAND"
        duck_draw_y = 48

        if self.state == "bonk":
            sprite_name = "BONK"
            duck_draw_y += 2
        elif self.state == "dizzy":
            frame_idx = (self.anim_frame // 2) % len(self.dizzy_frames)
            sprite_name = self.dizzy_frames[frame_idx]
            duck_draw_y += 22  # Acostado en el piso
        elif self.state == "alert":
            sprite_name = "ALERT"
        elif self.state == "walking":
            frame_idx = self.anim_frame % len(self.walk_frames)
            sprite_name = self.walk_frames[frame_idx]
        elif self.state == "pecking":
            sprite_name = "PECK"
            duck_draw_y += 3
        elif self.state == "grooming":
            sprite_name = "GROOM"
        elif self.state == "sit_flat":
            sprite_name = "SIT_FLAT"
            duck_draw_y += 12
        elif self.state == "flapping":
            frame_idx = (self.anim_frame // 2) % len(self.flap_frames)
            sprite_name = self.flap_frames[frame_idx]
            duck_draw_y -= 4
        elif self.state == "dragging":
            frame_idx = (self.anim_frame // 2) % len(self.flap_frames)
            sprite_name = self.flap_frames[frame_idx]
            duck_draw_y -= 4
        elif self.state == "falling":
            frame_idx = (self.anim_frame // 2) % len(self.tumble_frames)
            sprite_name = self.tumble_frames[frame_idx]
            duck_draw_y -= 2
        elif self.state == "landing":
            sprite_name = "KO_FLAT"
            duck_draw_y += 20
        elif self.state == "hopping":
            sprite_name = "FLAP_3"
            duck_draw_y -= 14
        elif self.state == "idle":
            if self.idle_counter % 30 > 20:
                sprite_name = "IDLE_SIT"
                duck_draw_y += 6
            else:
                sprite_name = "IDLE_STAND"

        # Fallback si el nombre no está en el mapa
        if sprite_name not in self.sprites:
            sprite_name = "IDLE_STAND" if "IDLE_STAND" in self.sprites else list(self.sprites.keys())[0]

        img = self.sprites[sprite_name][dir_key]
        sw, sh = self.sprite_sizes.get(sprite_name, (80, 115))
        duck_center_x = self.win_w // 2
        self.canvas.create_image(duck_center_x, duck_draw_y + (sh // 2), image=img)

    def _update_loop(self) -> None:
        """Bucle principal de física, colisiones y animación."""
        self.anim_frame += 1

        if not self._is_dragging:
            # 1. Determinar el piso actual (barra de tareas o plataforma de ventana)
            target_floor = self._find_highest_floor()

            # --- FÍSICA DE GRAVEDAD ---
            if self.is_falling:
                self.velocity_y += self.gravity
                self.pos_y += self.velocity_y

                # Colisión con el piso detectado
                if self.pos_y >= target_floor:
                    self.pos_y = target_floor
                    self.current_floor_y = target_floor
                    self.is_falling = False
                    self.velocity_y = 0.0
                    self.state = "landing"
                    self.state_timer = 3
                    self.status_message = "¡Plaf! 🦆"
                    self.status_color = "#10B981"

                self.root.geometry(f"{self.win_w}x{self.win_h}+{int(self.pos_x)}+{int(self.pos_y)}")

            # --- CHOQUE CONTRA VENTANA (BONK) ---
            elif self.state == "bonk":
                self.state_timer -= 1
                if self.state_timer <= 0:
                    # Pasar a estado mareado (DIZZY) con retroceso
                    self.state = "dizzy"
                    self.state_timer = 14
                    self.status_message = "¡Uff, qué golpe! 💫"
                    self.status_color = "#F59E0B"
                    self.pos_x -= self.direction * 14
                    self.root.geometry(f"{self.win_w}x{self.win_h}+{int(self.pos_x)}+{int(self.pos_y)}")

            # --- MAREADO CON ESTRELLAS Y PATALEO ---
            elif self.state == "dizzy":
                self.state_timer -= 1
                if self.state_timer <= 0:
                    # Pasar a alerta y dar la vuelta
                    self.state = "alert"
                    self.state_timer = 5
                    self.status_message = "¿Quién puso esa ventana? 🦆"
                    self.status_color = "#3B82F6"
                    self.direction *= -1

            # --- ALERTA Y RECUPERACIÓN ---
            elif self.state == "alert":
                self.state_timer -= 1
                if self.state_timer <= 0:
                    self.state = "walking"
                    self.idle_counter = 0

            # --- ATERRIZAJE ---
            elif self.state == "landing":
                self.state_timer -= 1
                if self.state_timer <= 0:
                    self.state = "idle"
                    self.idle_counter = 0
                    self.status_message = "💤 En guardia • 2 clics para entrar"
                    self.status_color = "#10B981"

            # --- CAMINATA NORMAL ---
            elif self.state == "walking":
                # Si el piso bajo el pato desapareció (ej: se salió del borde de la ventana), CAER
                if self.pos_y < target_floor - 12:
                    self.is_falling = True
                    self.velocity_y = 1.0
                    self.state = "falling"
                    self.status_message = "¡Me caigo! 🪂"
                    self.status_color = "#3B82F6"
                else:
                    # Verificar si choca con alguna ventana en el camino
                    has_bonked = self._check_window_collision()

                    if not has_bonked:
                        # Avanzar paso a paso
                        self.pos_x += self.direction * self.step_speed

                        # Rebote en los bordes de la pantalla física
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

                        # Pausa de caminata tras unos pasos
                        self.idle_counter += 1
                        if self.idle_counter > 40:
                            self.state = "idle"
                            self.idle_counter = 0

                        self.root.geometry(f"{self.win_w}x{self.win_h}+{int(self.pos_x)}+{int(self.pos_y)}")

            # --- ESTADOS DE DESCANSO E INTERACCIÓN ---
            elif self.state == "idle":
                self.idle_counter += 1
                if self.idle_counter == 12:
                    # 40% probabilidad de acicalarse o picotear
                    roll = time.time() % 3
                    if roll < 1.0:
                        self.state = "pecking"
                    elif roll < 2.0:
                        self.state = "grooming"
                    else:
                        self.state = "flapping"
                elif self.idle_counter > 32:
                    self.state = "walking"
                    self.idle_counter = 0
                    if (time.time() % 3) > 1.7:
                        self.direction *= -1

            elif self.state in ("pecking", "grooming", "flapping"):
                self.idle_counter += 1
                if self.idle_counter > 10:
                    self.state = "idle"
                    self.idle_counter = 0

            elif self.state == "hopping":
                self.idle_counter += 1
                if self.idle_counter > 8:
                    self.state = "idle"
                    self.idle_counter = 0

        self._draw_frame()

        # Cadencia fluida: 60ms cayendo, 100ms en bonk/dizzy, 120ms caminando
        if self.is_falling:
            interval = 55
        elif self.state in ("bonk", "dizzy"):
            interval = 95
        else:
            interval = 115

        self.root.after(interval, self._update_loop)

    def _sync_agent_status_loop(self) -> None:
        """Sincroniza periódicamente el mensaje de la burbuja."""
        try:
            status = get_agent_status()
            if status and self.state not in ("hopping", "dragging", "falling", "bonk", "dizzy"):
                if status.get("running") or status.get("state") == "thinking":
                    thought = status.get("thought", "")
                    self.status_message = f"🧠 {thought}" if thought else "🧠 Pensando y analizando..."
                    self.status_color = "#3B82F6"
                elif status.get("curiosity_active"):
                    proc = status.get("curiosity_proc", "")
                    self.status_message = f"🦉 Auto-mejorando: {proc}" if proc else "🦉 Investigando en segundo plano..."
                    self.status_color = "#8B5CF6"
                elif status.get("voice_active"):
                    text = status.get("voice_text", "")
                    self.status_message = f"🎙️ Hablando: {text}" if text else "🎙️ Emitiendo voz..."
                    self.status_color = "#EC4899"
                elif status.get("error"):
                    self.status_message = f"⚠️ {status.get('error')}"
                    self.status_color = "#EF4444"
                else:
                    self.status_message = "💤 En guardia • 2 clics para entrar"
                    self.status_color = "#10B981"
        except Exception:
            pass
        finally:
            self.root.after(1500, self._sync_agent_status_loop)

    def run(self) -> None:
        """Ejecuta el bucle de eventos del escritorio."""
        log.info("🦆 [DesktopDuck]: Iniciando pato interactivo con física y colisiones...")
        self.root.after(100, self._update_loop)
        self.root.after(1500, self._sync_agent_status_loop)
        self.root.mainloop()


def run_duck() -> int:
    pet = DesktopDuckPet(target_height=118)
    pet.run()
    return 0


if __name__ == "__main__":
    sys.exit(run_duck())
