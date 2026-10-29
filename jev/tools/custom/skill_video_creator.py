"""
Generador Programático de Vídeos de Lanzamiento (Auto-Launch Video Engine) para JEV.
Analiza cualquier proyecto web o artefacto generado en workspace/, extrae su propuesta
de valor, paleta de colores y genera un vídeo promocional MP4 (H.264) con motion graphics,
transiciones, subtítulos resaltados y renderizado con FFmpeg.
"""
from typing import Dict, Any, List, Optional, Tuple
from pathlib import Path
import json
import re
import shutil
import subprocess
import tempfile
import time
import os

from PIL import Image, ImageDraw, ImageFont
from bs4 import BeautifulSoup

from jev.tools.base import BaseTool, ToolResult
from jev.config import default_config


# =============================================================================
# 1. ANALIZADOR SEMÁNTICO DE PROYECTO (PROJECT CONTEXT PARSER)
# =============================================================================
class ProjectContextParser:
    """Extrae metadatos, valor de propuesta, colores y estructura un guion dinámico."""

    DEFAULT_PALETTE = {
        "primary": "#00f0ff",     # Cian cibernético
        "secondary": "#a855f7",   # Púrpura neón
        "background": "#080c14",  # Obsidiana profundo
        "card_bg": "#101826",     # Azul marino noche
        "text": "#f8fafc",        # Blanco brillante
        "text_dim": "#94a3b8"     # Gris plateado
    }

    @classmethod
    def parse(cls, html_content: str, file_name: str = "proyecto.html") -> Dict[str, Any]:
        """Extrae título, propósito, paleta de colores y genera un guion de 4 escenas."""
        soup = BeautifulSoup(html_content, "html.parser")

        # 1. Título principal
        title = ""
        if soup.title and soup.title.string:
            title = soup.title.string.strip()
        elif soup.h1:
            title = soup.h1.get_text().strip()
        else:
            meta_og = soup.find("meta", property="og:title")
            if meta_og and meta_og.get("content"):
                title = meta_og["content"].strip()
            else:
                title = Path(file_name).stem.replace("_", " ").title()

        title = title[:60]

        # 2. Propósito y propuesta de valor
        purpose = ""
        meta_desc = soup.find("meta", attrs={"name": "description"}) or soup.find("meta", property="og:description")
        if meta_desc and meta_desc.get("content"):
            purpose = meta_desc["content"].strip()
        elif soup.p:
            purpose = soup.p.get_text().strip()
        elif soup.h2:
            purpose = soup.h2.get_text().strip()
        else:
            purpose = "Plataforma interactiva autónoma desarrollada en el ecosistema JEV."

        purpose = purpose[:140]

        # 3. Características destacadas (features)
        features: List[str] = []
        for li in soup.find_all("li")[:4]:
            txt = li.get_text().strip()
            if txt and len(txt) > 3 and txt not in features:
                features.append(txt[:50])

        if not features:
            for h in (soup.find_all("h2") + soup.find_all("h3"))[:3]:
                txt = h.get_text().strip()
                if txt and txt != title and txt not in features:
                    features.append(txt[:50])

        if not features:
            features = [
                "Arquitectura reactiva en tiempo real",
                "Interfaz holográfica de alto rendimiento",
                "Integración con modelos de IA local"
            ]

        # 4. Paleta de colores
        palette = dict(cls.DEFAULT_PALETTE)
        all_text_styles = " ".join([tag.get_text() for tag in soup.find_all("style")])
        hex_colors = re.findall(r"#(?:[0-9a-fA-F]{3}){1,2}\b", all_text_styles)
        if hex_colors:
            # Filtrar colores no blancos/negros puros como acentos
            accents = [c for c in hex_colors if c.lower() not in ("#000", "#000000", "#fff", "#ffffff")]
            if accents:
                palette["primary"] = accents[0]
            if len(accents) > 1:
                palette["secondary"] = accents[1]

        # 5. Estructurar Guion Dinámico (Hook -> Demo -> Features -> CTA)
        scenes = [
            {
                "scene_id": 1,
                "type": "hook",
                "badge": "FASE 01 // LANZAMIENTO",
                "headline": title,
                "subtitle": "¿Listo para transformar tu flujo de trabajo?",
                "duration": 2.0
            },
            {
                "scene_id": 2,
                "type": "demo",
                "badge": "FASE 02 // VISIÓN GENERAL",
                "headline": "Solución Diseñada para la Acción",
                "subtitle": purpose,
                "duration": 2.5
            },
            {
                "scene_id": 3,
                "type": "features",
                "badge": "FASE 03 // CAPACIDADES CLAVE",
                "headline": "Innovación y Rendimiento",
                "bullets": features[:3],
                "duration": 2.5
            },
            {
                "scene_id": 4,
                "type": "cta",
                "badge": "FASE 04 // ACCIÓN",
                "headline": "¡Disponible Ahora!",
                "subtitle": "Ecosistema Autónomo JEV v2.6",
                "duration": 2.0
            }
        ]

        return {
            "title": title,
            "purpose": purpose,
            "features": features,
            "palette": palette,
            "scenes": scenes,
            "total_duration": sum(s["duration"] for s in scenes)
        }


# =============================================================================
# 2. MOTOR DE RENDERIZADO Y MOTION GRAPHICS (LAUNCH VIDEO RENDERER)
# =============================================================================
class LaunchVideoRenderer:
    """Genera secuencias de fotogramas con motion graphics y compila a MP4 con FFmpeg."""

    RESOLUTIONS = {
        "720p": (1280, 720),
        "1080p": (1920, 1080),
        "vertical_reel": (1080, 1920),
        "square": (1080, 1080)
    }

    @staticmethod
    def get_ffmpeg_binary() -> Optional[str]:
        """Localiza el binario de FFmpeg en el sistema."""
        binary = shutil.which("ffmpeg")
        if binary:
            return binary
        # Comprobar rutas comunes en Windows
        known_paths = [
            Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft/WinGet/Packages/Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe/ffmpeg-9.0.2-full_build/bin/ffmpeg.exe",
            Path("C:/ffmpeg/bin/ffmpeg.exe"),
            Path("C:/Program Files/ffmpeg/bin/ffmpeg.exe")
        ]
        for p in known_paths:
            if p.exists():
                return str(p)
        return None

    @classmethod
    def hex_to_rgb(cls, hex_str: str) -> Tuple[int, int, int]:
        clean = hex_str.lstrip("#")
        if len(clean) == 3:
            clean = "".join([c * 2 for c in clean])
        try:
            return tuple(int(clean[i:i+2], 16) for i in (0, 2, 4))
        except Exception:
            return (0, 240, 255)

    @classmethod
    def _render_scene_frame(
        cls,
        scene: Dict[str, Any],
        palette: Dict[str, str],
        width: int = 1280,
        height: int = 720,
        progress: float = 0.5,
        scene_progress: float = 0.5
    ) -> Image.Image:
        """Renderiza un único fotograma de escena en un objeto PIL.Image."""
        bg_rgb = cls.hex_to_rgb(palette.get("background", "#080c14"))
        card_rgb = cls.hex_to_rgb(palette.get("card_bg", "#101826"))
        primary_rgb = cls.hex_to_rgb(palette.get("primary", "#00f0ff"))
        secondary_rgb = cls.hex_to_rgb(palette.get("secondary", "#a855f7"))
        text_rgb = cls.hex_to_rgb(palette.get("text", "#f8fafc"))
        dim_rgb = cls.hex_to_rgb(palette.get("text_dim", "#94a3b8"))

        badge = scene.get("badge", "FASE // INFORMACIÓN")
        headline = scene.get("headline", "")
        subtitle = scene.get("subtitle", "")
        bullets = scene.get("bullets", [])

        img = Image.new("RGB", (width, height), color=bg_rgb)
        draw = ImageDraw.Draw(img)

        # 1. Fondo degradado sutil y detalles tecnológicos
        glow_y = int(height * 0.35)
        glow_radius = int(250 + 20 * scene_progress)
        glow_color = (
            int(primary_rgb[0] * 0.15),
            int(primary_rgb[1] * 0.15),
            int(primary_rgb[2] * 0.15)
        )
        draw.ellipse(
            [width // 2 - glow_radius, glow_y - glow_radius, width // 2 + glow_radius, glow_y + glow_radius],
            fill=glow_color
        )

        # 2. Marco / Tarjeta central de contenido
        card_w = int(width * 0.85)
        card_h = int(height * 0.68)
        card_x1 = (width - card_w) // 2
        card_y1 = (height - card_h) // 2 - 20
        card_x2 = card_x1 + card_w
        card_y2 = card_y1 + card_h

        draw.rectangle([card_x1, card_y1, card_x2, card_y2], fill=card_rgb, outline=primary_rgb, width=2)

        # Decoración en las esquinas de la tarjeta (estilo HUD)
        corner_len = 24
        draw.line([card_x1, card_y1, card_x1 + corner_len, card_y1], fill=primary_rgb, width=4)
        draw.line([card_x1, card_y1, card_x1, card_y1 + corner_len], fill=primary_rgb, width=4)
        draw.line([card_x2, card_y2, card_x2 - corner_len, card_y2], fill=primary_rgb, width=4)
        draw.line([card_x2, card_y2, card_x2, card_y2 - corner_len], fill=primary_rgb, width=4)

        # 3. Badge superior de la escena
        badge_y = card_y1 + 30
        draw.text((card_x1 + 40, badge_y), badge, fill=secondary_rgb)

        # 4. Título principal con animación de slide-up y fade-in
        anim_offset = int(15 * (1.0 - min(scene_progress * 2.0, 1.0)))
        head_y = badge_y + 40 + anim_offset
        draw.text((card_x1 + 40, head_y), headline, fill=text_rgb)

        # 5. Línea divisoria de acento animada
        line_w = int((card_w - 80) * min(scene_progress * 1.5, 1.0))
        draw.line([card_x1 + 40, head_y + 45, card_x1 + 40 + line_w, head_y + 45], fill=primary_rgb, width=2)

        # 6. Subtítulo o viñetas según el tipo de escena
        content_y = head_y + 65
        if bullets:
            for b_idx, b_text in enumerate(bullets):
                bullet_alpha = min(max((scene_progress * 3.0) - (b_idx * 0.3), 0.0), 1.0)
                if bullet_alpha > 0.1:
                    bullet_color = (
                        int(text_rgb[0] * bullet_alpha),
                        int(text_rgb[1] * bullet_alpha),
                        int(text_rgb[2] * bullet_alpha)
                    )
                    draw.text((card_x1 + 60, content_y + (b_idx * 36)), f"▸  {b_text}", fill=bullet_color)
        else:
            sub_color = (
                int(dim_rgb[0] * min(scene_progress * 2.0, 1.0)),
                int(dim_rgb[1] * min(scene_progress * 2.0, 1.0)),
                int(dim_rgb[2] * min(scene_progress * 2.0, 1.0))
            )
            words = subtitle.split()
            lines = []
            cur_line = []
            for w in words:
                cur_line.append(w)
                if len(" ".join(cur_line)) > 55:
                    lines.append(" ".join(cur_line))
                    cur_line = []
            if cur_line:
                lines.append(" ".join(cur_line))

            for l_idx, line_str in enumerate(lines[:3]):
                draw.text((card_x1 + 40, content_y + (l_idx * 28)), line_str, fill=sub_color)

        # 7. Barra de progreso global del vídeo en la parte inferior
        bar_h = 6
        bar_y = height - bar_h - 15
        draw.rectangle([card_x1, bar_y, card_x2, bar_y + bar_h], fill=(30, 40, 60))
        fill_x = card_x1 + int(card_w * progress)
        draw.rectangle([card_x1, bar_y, fill_x, bar_y + bar_h], fill=primary_rgb)

        return img

    @classmethod
    def render_video(
        cls,
        parsed_context: Dict[str, Any],
        output_file: Path,
        resolution: str = "720p",
        fps: int = 30
    ) -> Dict[str, Any]:
        """
        Genera fotogramas para cada escena y compila un MP4 con H.264.
        """
        width, height = cls.RESOLUTIONS.get(resolution, (1280, 720))
        palette = parsed_context.get("palette", ProjectContextParser.DEFAULT_PALETTE)
        scenes = parsed_context.get("scenes", [])
        total_duration = parsed_context.get("total_duration", 9.0)
        total_frames = int(total_duration * fps)

        ffmpeg_bin = cls.get_ffmpeg_binary()
        if not ffmpeg_bin:
            raise FileNotFoundError("FFmpeg no encontrado en PATH ni en rutas locales del sistema.")

        with tempfile.TemporaryDirectory() as tmp_dir:
            frames_dir = Path(tmp_dir) / "frames"
            frames_dir.mkdir(parents=True, exist_ok=True)

            current_frame_idx = 0

            # Renderizado secuencial de escenas
            for scene_idx, scene in enumerate(scenes):
                scene_duration = scene.get("duration", 2.0)
                scene_frames = int(scene_duration * fps)

                for f in range(scene_frames):
                    scene_progress = f / max(scene_frames - 1, 1)  # 0.0 a 1.0 dentro de la escena
                    global_progress = current_frame_idx / max(total_frames - 1, 1)

                    img = cls._render_scene_frame(
                        scene=scene,
                        palette=palette,
                        width=width,
                        height=height,
                        progress=global_progress,
                        scene_progress=scene_progress
                    )

                    # Guardar fotograma numerado
                    frame_path = frames_dir / f"frame_{current_frame_idx:05d}.png"
                    img.save(frame_path, "PNG")
                    current_frame_idx += 1


            # Compilar los fotogramas con FFmpeg a MP4 (H.264 / yuv420p)
            output_file.parent.mkdir(parents=True, exist_ok=True)
            input_pattern = str(frames_dir / "frame_%05d.png")

            ffmpeg_cmd = [
                ffmpeg_bin,
                "-y",
                "-framerate", str(fps),
                "-i", input_pattern,
                "-c:v", "libx264",
                "-pix_fmt", "yuv420p",
                "-movflags", "+faststart",
                str(output_file)
            ]

            t0 = time.time()
            proc = subprocess.run(
                ffmpeg_cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace"
            )
            render_time = round(time.time() - t0, 2)

            if proc.returncode != 0:
                raise RuntimeError(f"FFmpeg error ({proc.returncode}): {proc.stderr[:400]}")

            return {
                "success": True,
                "output_file": str(output_file),
                "resolution": f"{width}x{height}",
                "total_frames": current_frame_idx,
                "fps": fps,
                "duration_seconds": total_duration,
                "render_time_seconds": render_time,
                "file_size_bytes": output_file.stat().st_size if output_file.exists() else 0
            }


# =============================================================================
# 3. HERRAMIENTA PRINCIPAL: AUTOLAUNCHVIDEOTOOL
# =============================================================================
class AutoLaunchVideoTool(BaseTool):
    """
    Herramienta que analiza proyectos web o artefactos en workspace/ y
    compila automáticamente un vídeo promocional corto de lanzamiento (MP4).
    """
    name = "skill_video_creator"
    description = (
        "Generador programático de vídeos de lanzamiento (Auto-Launch Video Engine). "
        "Analiza proyectos web o dashboards generados en workspace/, extrae su propuesta "
        "de valor, estructura un guion dinámico (Hook, Demostración, Características, Call to Action) "
        "y compila automáticamente un vídeo promocional MP4 codificado en H.264 con FFmpeg."
    )
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "Acción a realizar: 'create_launch_video', 'parse_project', 'check_ffmpeg'",
                "enum": ["create_launch_video", "parse_project", "check_ffmpeg"],
                "default": "create_launch_video"
            },
            "target_path": {
                "type": "string",
                "description": "Ruta del archivo HTML o proyecto en workspace/ (ej. 'workspace/lottery_dashboard.html')",
                "default": "workspace/index.html"
            },
            "html_content": {
                "type": "string",
                "description": "Contenido HTML opcional si se pasa directamente sin archivo en disco",
                "default": ""
            },
            "output_filename": {
                "type": "string",
                "description": "Nombre del archivo de vídeo de salida (por defecto 'launch_video.mp4')",
                "default": "launch_video.mp4"
            },
            "resolution": {
                "type": "string",
                "description": "Resolución del vídeo: '720p', '1080p', 'vertical_reel', 'square'",
                "enum": ["720p", "1080p", "vertical_reel", "square"],
                "default": "720p"
            },
            "fps": {
                "type": "integer",
                "description": "Fotogramas por segundo (por defecto 30)",
                "default": 30
            }
        },
        "required": ["action"]
    }

    def __init__(self, workspace_dir: Optional[Path] = None):
        self.workspace_dir = workspace_dir or default_config.workspace_dir
        self.workspace_dir.mkdir(parents=True, exist_ok=True)

    def execute(self, **kwargs) -> ToolResult:
        action = kwargs.get("action", "create_launch_video")
        target_path_str = kwargs.get("target_path", "workspace/index.html")
        html_content = kwargs.get("html_content", "")
        output_filename = kwargs.get("output_filename", "launch_video.mp4")
        resolution = kwargs.get("resolution", "720p")
        fps = int(kwargs.get("fps", 30))

        try:
            # 1. Comprobación de binario FFmpeg
            if action == "check_ffmpeg":
                binary = LaunchVideoRenderer.get_ffmpeg_binary()
                if binary:
                    return ToolResult(
                        success=True,
                        output=f"FFmpeg disponible en el sistema: {binary}",
                        data={"ffmpeg_path": binary, "available": True}
                    )
                return ToolResult(
                    success=False,
                    output="",
                    error="FFmpeg no encontrado en PATH ni en rutas estándar del sistema.",
                    data={"available": False}
                )

            # 2. Obtener contenido HTML (del archivo o del argumento directo)
            resolved_html = html_content
            file_name = "index.html"

            if not resolved_html:
                target_file = Path(target_path_str)
                if not target_file.is_absolute():
                    target_file = self.workspace_dir.parent / target_path_str if (self.workspace_dir.parent / target_path_str).exists() else self.workspace_dir / target_path_str

                if target_file.exists():
                    resolved_html = target_file.read_text(encoding="utf-8")
                    file_name = target_file.name
                else:
                    # Si no existe, plantilla de demostración por defecto
                    resolved_html = f"""<!DOCTYPE html>
<html>
<head><title>{Path(target_path_str).stem.replace('_', ' ').title()}</title></head>
<body>
  <h1>Plataforma Inteligente Autónoma</h1>
  <p>Generación y orquestación dinámica de soluciones impulsadas por IA local.</p>
  <ul>
    <li>Motor de ejecución reactivo</li>
    <li>Procesamiento local 100% privado</li>
    <li>Renderizado en tiempo real</li>
  </ul>
</body>
</html>"""
                    file_name = Path(target_path_str).name

            # 3. Analizar contexto y estructurar guion
            parsed = ProjectContextParser.parse(resolved_html, file_name=file_name)

            if action == "parse_project":
                return ToolResult(
                    success=True,
                    output=f"Análisis semántico completado: Título='{parsed['title']}', Escenas={len(parsed['scenes'])}, Duración={parsed['total_duration']}s.",
                    data=parsed
                )

            # 4. Renderizar vídeo completo a MP4
            out_file = self.workspace_dir / output_filename
            render_res = LaunchVideoRenderer.render_video(
                parsed_context=parsed,
                output_file=out_file,
                resolution=resolution,
                fps=fps
            )

            # Notificación y resumen de éxito
            summary = (
                f"🎬 Vídeo promocional de lanzamiento compilado con éxito: '{out_file.name}' "
                f"({render_res['resolution']}, {render_res['duration_seconds']}s, {render_res['total_frames']} frames, "
                f"{round(render_res['file_size_bytes'] / 1024, 1)} KB en {render_res['render_time_seconds']}s)."
            )

            return ToolResult(
                success=True,
                output=summary,
                data={
                    "video_path": str(out_file.resolve()),
                    "title": parsed["title"],
                    "scenes_count": len(parsed["scenes"]),
                    "resolution": render_res["resolution"],
                    "duration_seconds": render_res["duration_seconds"],
                    "render_metrics": render_res
                }
            )

        except Exception as e:
            return ToolResult(
                success=False,
                output="",
                error=f"Error en AutoLaunchVideoTool: {str(e)}"
            )
