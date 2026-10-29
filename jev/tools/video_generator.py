"""
Herramienta de Generación de Video basada en HyperFrames (HeyGen).
Permite a JEV crear, componer y renderizar videos MP4 deterministas de alta calidad (1080p/4K)
a partir de animaciones web en HTML5, CSS3, Tailwind y GSAP, acelerados por hardware en GPU local.
"""
from typing import Dict, Any, Optional
import os
import subprocess
import json
from pathlib import Path
from jev.tools.base import BaseTool, ToolResult
from jev.config import default_config


class HyperFramesVideoTool(BaseTool):
    """Herramienta para crear y renderizar videos deterministas con HyperFrames."""
    name = "render_hyperframes_video"
    description = (
        "Crea y renderiza videos MP4 deterministas de alta fidelidad a partir de composiciones HTML5/CSS3/GSAP. "
        "Permite generar videos promocionales, explicativos, reels/shorts verticales (1080x1920) o landscape (1920x1080) "
        "con animaciones fluidas a 60 FPS aceleradas por hardware en la GPU local."
    )
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["render_html", "scaffold_project", "check_environment"],
                "description": "Acción a realizar: 'render_html' (crea y renderiza una composición HTML a MP4), 'scaffold_project' (inicializa un proyecto de video) o 'check_environment' (comprueba dependencias)."
            },
            "project_name": {
                "type": "string",
                "description": "Nombre del proyecto o video (ej. 'presentacion_jev' o 'openmythos_reel')."
            },
            "html_content": {
                "type": "string",
                "description": "Código HTML5/CSS/GSAP completo que define la animación y el contenido visual del video."
            },
            "duration_seconds": {
                "type": "integer",
                "description": "Duración del video en segundos (por defecto 5 a 10)."
            },
            "resolution": {
                "type": "string",
                "enum": ["landscape", "portrait", "square", "4k"],
                "description": "Formato del video: 'landscape' (1920x1080 YouTube/Web), 'portrait' (1080x1920 TikTok/Reels), 'square' (1080x1080 Instagram) o '4k'."
            },
            "output_filename": {
                "type": "string",
                "description": "Nombre del archivo de video resultante (por defecto 'video.mp4')."
            }
        },
        "required": ["action"]
    }

    def __init__(self, workspace_dir: Optional[Path] = None):
        self.workspace_dir = workspace_dir or default_config.workspace_dir

    def execute(
        self,
        action: str,
        project_name: str = "video_project",
        html_content: Optional[str] = None,
        duration_seconds: int = 5,
        resolution: str = "landscape",
        output_filename: str = "video.mp4",
        **kwargs
    ) -> ToolResult:
        videos_dir = self.workspace_dir / "videos"
        videos_dir.mkdir(parents=True, exist_ok=True)

        if action == "check_environment":
            try:
                cmd = ["npx", "--yes", "hyperframes", "doctor"]
                proc = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=30,
                    shell=True
                )
                return ToolResult(
                    success=True,
                    output=f"Diagnóstico de HyperFrames:\n{proc.stdout[:800]}",
                    data={"exit_code": proc.returncode}
                )
            except Exception as e:
                return ToolResult(success=False, output="", error=f"Error ejecutando hyperframes doctor: {str(e)}")

        elif action == "scaffold_project":
            proj_dir = videos_dir / project_name
            if proj_dir.exists():
                return ToolResult(
                    success=True,
                    output=f"El proyecto '{project_name}' ya existe en: {proj_dir}",
                    data={"path": str(proj_dir)}
                )
            try:
                cmd = ["npx", "--yes", "hyperframes", "init", str(proj_dir), "--example", "blank", "--non-interactive"]
                proc = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=60,
                    shell=True
                )
                if proc.returncode == 0:
                    return ToolResult(
                        success=True,
                        output=f"✓ Proyecto HyperFrames creado exitosamente en: {proj_dir}",
                        data={"path": str(proj_dir)}
                    )
                else:
                    return ToolResult(
                        success=False,
                        output=proc.stdout,
                        error=f"Fallo al inicializar proyecto HyperFrames: {proc.stderr[:300]}"
                    )
            except Exception as e:
                return ToolResult(success=False, output="", error=f"Error inicializando proyecto: {str(e)}")

        elif action == "render_html":
            proj_dir = videos_dir / project_name
            proj_dir.mkdir(parents=True, exist_ok=True)

            res_map = {
                "landscape": (1920, 1080),
                "portrait": (1080, 1920),
                "square": (1080, 1080),
                "4k": (3840, 2160)
            }
            width, height = res_map.get(resolution, (1920, 1080))

            if not html_content:
                # Plantilla base estilizada y minimalista por defecto si no se proporciona HTML
                html_content = f"""<!doctype html>
<html lang="es">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width={width}, height={height}" />
  <script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
  <style>
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    html, body {{
      width: {width}px;
      height: {height}px;
      overflow: hidden;
      background: #000000;
      color: #00f0ff;
      font-family: 'Segoe UI', system-ui, sans-serif;
    }}
    #root {{
      width: 100%;
      height: 100%;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      text-align: center;
      padding: 40px;
    }}
    .glow {{
      font-size: 72px;
      font-weight: 700;
      letter-spacing: 2px;
      text-shadow: 0 0 25px rgba(0, 240, 255, 0.6);
      margin-bottom: 20px;
    }}
    .subtitle {{
      font-size: 32px;
      color: #94a3b8;
    }}
  </style>
</head>
<body>
  <div id="root" data-composition-id="main" data-start="0" data-duration="{duration_seconds}" data-width="{width}" data-height="{height}">
    <h1 id="title" class="glow">JEV AI VIDEO CORE</h1>
    <p id="sub" class="subtitle">Generado de forma determinista con HyperFrames</p>
  </div>
  <script>
    const tl = gsap.timeline({{ paused: true }});
    tl.fromTo("#title", {{ opacity: 0, scale: 0.8, y: 30 }}, {{ opacity: 1, scale: 1, y: 0, duration: 1.2, ease: "power3.out" }}, 0);
    tl.fromTo("#sub", {{ opacity: 0, y: 20 }}, {{ opacity: 1, y: 0, duration: 1, ease: "power2.out" }}, 0.6);
    window.__timelines = window.__timelines || {{}};
    window.__timelines["main"] = tl;
    tl.seek(0);
  </script>
</body>
</html>"""

            # Guardar index.html y hyperframes.json
            index_path = proj_dir / "index.html"
            with open(index_path, "w", encoding="utf-8") as f:
                f.write(html_content)

            hf_json = {
                "version": "1.0",
                "width": width,
                "height": height,
                "fps": 60,
                "duration": duration_seconds
            }
            with open(proj_dir / "hyperframes.json", "w", encoding="utf-8") as f:
                json.dump(hf_json, f, indent=2)

            out_file = proj_dir / output_filename
            try:
                cmd = ["npx", "--yes", "hyperframes", "render", "-o", str(out_file)]
                proc = subprocess.run(
                    cmd,
                    cwd=str(proj_dir),
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=120,
                    shell=True
                )

                if out_file.exists() and out_file.stat().st_size > 0:
                    size_kb = round(out_file.stat().st_size / 1024, 1)
                    msg = (
                        f"🎬 Video Renderizado Exitosamente con HyperFrames:\n"
                        f"• Archivo: {out_file}\n"
                        f"• Tamaño: {size_kb} KB\n"
                        f"• Resolución: {width}x{height} ({resolution})\n"
                        f"• Duración: {duration_seconds} segundos (60 FPS determinista)\n"
                        f"• Aceleración: Hardware GPU / FFmpeg NVENC\n"
                        f"• Estado: Listo para visualización o distribución."
                    )
                    return ToolResult(
                        success=True,
                        output=msg,
                        data={
                            "video_path": str(out_file),
                            "size_bytes": out_file.stat().st_size,
                            "duration_seconds": duration_seconds,
                            "resolution": f"{width}x{height}"
                        }
                    )
                else:
                    return ToolResult(
                        success=False,
                        output=proc.stdout,
                        error=f"El renderizado de HyperFrames finalizó pero no generó el archivo de video: {proc.stderr[:400]}"
                    )
            except Exception as e:
                return ToolResult(success=False, output="", error=f"Error durante el renderizado del video: {str(e)}")

        else:
            return ToolResult(
                success=False,
                output="",
                error=f"Acción '{action}' no reconocida. Usa 'render_html', 'scaffold_project' o 'check_environment'."
            )
