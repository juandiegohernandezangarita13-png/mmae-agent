"""
Servidor local de navegación web y búsqueda para el Sidecar de Antigravity 2.0 en MMAE.
Proporciona:
1. Búsqueda web real con DuckDuckGo (/search?q=...) con interfaz oscura Antigravity.
2. Proxy web desbloqueador (/browse?url=...) que elimina X-Frame-Options y CSP, permitiendo
   visitar páginas reales dentro del iframe del Sidecar.
3. Soporte inteligente para YouTube y vídeos (transformación a reproductor embebido sin restricciones).
4. Sincronización en vivo con el agente cuando este busca o lee páginas web.
"""
from __future__ import annotations

import os
import sys
import re
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading
from typing import Optional, List, Dict
from pathlib import Path

import httpx

try:
    from jev.tools.web import WebSearchTool
except ImportError:
    WebSearchTool = None


SERVER_PORT = 8765
_SERVER_INSTANCE: Optional[HTTPServer] = None


class SidecarProxyHandler(BaseHTTPRequestHandler):
    """Manejador HTTP para búsquedas web y proxy de navegación sin restricciones de marco."""

    def log_message(self, format, *args):
        # Silenciar logs ruidosos en la terminal estándar
        pass

    def do_GET(self):
        try:
            parsed = urllib.parse.urlparse(self.path)
            path = parsed.path
            query_params = urllib.parse.parse_qs(parsed.query)

            if path == "/search":
                q = query_params.get("q", [""])[0].strip()
                self._handle_search(q)
            elif path == "/browse":
                target_url = query_params.get("url", [""])[0].strip()
                self._handle_browse(target_url)
            elif path == "/image":
                img_name = query_params.get("name", [""])[0].strip()
                self._handle_image(img_name)
            elif path in ("/image-viewer", "/gallery"):
                img_name = query_params.get("name", [""])[0].strip()
                prompt = query_params.get("prompt", [""])[0].strip()
                self._handle_image_viewer(img_name, prompt)
            elif path == "/status":
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(b'{"status": "ok", "service": "Bable Web Engine"}')
            else:
                # Página de inicio del navegador Bable
                self._handle_home()
        except Exception as e:
            try:
                self.send_response(500)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.end_headers()
                self.wfile.write(f"Error en servidor Bable: {e}".encode("utf-8"))
            except Exception:
                pass

    def _handle_image(self, img_name: str):
        """Sirve imágenes generadas por el agente de forma segura y directa."""
        if not img_name:
            self.send_response(400)
            self.end_headers()
            return

        clean_name = os.path.basename(img_name)
        img_path = None
        try:
            from jev.config import BASE_DIR
            candidate = Path(BASE_DIR) / "data" / "generated_images" / clean_name
            if candidate.exists():
                img_path = candidate
        except Exception:
            pass

        if not img_path or not img_path.exists():
            candidate = Path("data/generated_images") / clean_name
            if candidate.exists():
                img_path = candidate

        if img_path and img_path.exists():
            data = img_path.read_bytes()
            mime = "image/jpeg" if clean_name.lower().endswith((".jpg", ".jpeg")) else "image/png"
            self.send_response(200)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Cache-Control", "public, max-age=86400")
            self.end_headers()
            self.wfile.write(data)
        else:
            self.send_response(404)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"Imagen no encontrada")

    def _handle_image_viewer(self, img_name: str, prompt: str = ""):
        """Visualizador web premium de imágenes generadas para el navegador Bable."""
        images_dir = Path("data/generated_images")
        if not images_dir.exists():
            images_dir.mkdir(parents=True, exist_ok=True)

        all_imgs = sorted(list(images_dir.glob("*.jpg")) + list(images_dir.glob("*.png")), key=lambda p: p.stat().st_mtime, reverse=True)
        img_names = [p.name for p in all_imgs]

        if not img_name and img_names:
            img_name = img_names[0]

        clean_name = os.path.basename(img_name) if img_name else ""
        current_img_url = f"/image?name={clean_name}" if clean_name else ""

        # Construir miniaturas de galería
        thumbs_html = ""
        for name in img_names:
            active_cls = "active" if name == clean_name else ""
            thumbs_html += f"""
            <a href="/image-viewer?name={name}" class="thumb-card {active_cls}">
              <img src="/image?name={name}" alt="{name}" loading="lazy"/>
              <span class="thumb-name">{name}</span>
            </a>
            """

        display_title = prompt if prompt else (clean_name if clean_name else "Galería de Imágenes Bable")

        html = f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <title>Bable // Visor de Imágenes: {clean_name}</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      background: #0d0e12;
      color: #e2e8f0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      height: 100vh;
      display: flex;
      flex-direction: column;
      overflow: hidden;
      user-select: none;
    }}
    .top-toolbar {{
      height: 52px;
      background: #14161b;
      border-bottom: 1px solid rgba(255, 255, 255, 0.08);
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 0 16px;
      gap: 12px;
      flex-shrink: 0;
    }}
    .top-toolbar-left {{
      display: flex;
      align-items: center;
      gap: 10px;
      min-width: 0;
    }}
    .badge-tag {{
      background: rgba(37, 99, 235, 0.2);
      color: #60a5fa;
      border: 1px solid rgba(37, 99, 235, 0.4);
      border-radius: 4px;
      font-size: 11px;
      font-weight: 600;
      padding: 2px 7px;
      white-space: nowrap;
    }}
    .img-title {{
      font-size: 13.5px;
      font-weight: 600;
      color: #f8fafc;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }}
    .top-toolbar-right {{
      display: flex;
      align-items: center;
      gap: 8px;
    }}
    .btn-tool {{
      background: rgba(255, 255, 255, 0.06);
      border: 1px solid rgba(255, 255, 255, 0.1);
      border-radius: 6px;
      color: #cbd5e1;
      padding: 6px 12px;
      font-size: 12px;
      font-weight: 500;
      cursor: pointer;
      display: flex;
      align-items: center;
      gap: 6px;
      transition: all 0.15s;
      text-decoration: none;
    }}
    .btn-tool:hover {{
      background: #2563eb;
      color: #ffffff;
      border-color: #3b82f6;
    }}
    .main-canvas-area {{
      flex: 1;
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 20px;
      overflow: auto;
      background: radial-gradient(circle at center, #171922 0%, #0d0e12 100%);
      position: relative;
    }}
    .image-frame {{
      max-width: 100%;
      max-height: 100%;
      display: flex;
      align-items: center;
      justify-content: center;
      transition: transform 0.2s ease;
    }}
    .main-image {{
      max-width: 90vw;
      max-height: calc(100vh - 190px);
      object-fit: contain;
      border-radius: 10px;
      box-shadow: 0 20px 50px rgba(0, 0, 0, 0.8), 0 0 0 1px rgba(255, 255, 255, 0.1);
    }}
    .bottom-gallery-bar {{
      height: 110px;
      background: #111216;
      border-top: 1px solid rgba(255, 255, 255, 0.08);
      display: flex;
      flex-direction: column;
      padding: 8px 14px;
      flex-shrink: 0;
    }}
    .gallery-header {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 6px;
    }}
    .gallery-title {{
      font-size: 11px;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.5px;
      color: #94a3b8;
    }}
    .gallery-count {{
      font-size: 11px;
      color: #64748b;
    }}
    .thumbs-strip {{
      display: flex;
      gap: 10px;
      overflow-x: auto;
      overflow-y: hidden;
      padding-bottom: 4px;
    }}
    .thumbs-strip::-webkit-scrollbar {{ height: 5px; }}
    .thumbs-strip::-webkit-scrollbar-thumb {{ background: rgba(255,255,255,0.15); border-radius: 4px; }}
    .thumb-card {{
      display: flex;
      flex-direction: column;
      align-items: center;
      text-decoration: none;
      width: 76px;
      flex-shrink: 0;
      border-radius: 6px;
      overflow: hidden;
      border: 1px solid rgba(255, 255, 255, 0.08);
      background: #181a20;
      padding: 3px;
      transition: all 0.15s;
    }}
    .thumb-card:hover {{
      border-color: #3b82f6;
      transform: translateY(-2px);
    }}
    .thumb-card.active {{
      border-color: #2563eb;
      background: rgba(37, 99, 235, 0.15);
      box-shadow: 0 0 10px rgba(37, 99, 235, 0.3);
    }}
    .thumb-card img {{
      width: 100%;
      height: 48px;
      object-fit: cover;
      border-radius: 4px;
    }}
    .thumb-name {{
      font-size: 9.5px;
      color: #94a3b8;
      width: 100%;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
      text-align: center;
      margin-top: 3px;
    }}
    .empty-state {{
      text-align: center;
      color: #64748b;
      font-size: 14px;
    }}
  </style>
</head>
<body>
  <div class="top-toolbar">
    <div class="top-toolbar-left">
      <span class="badge-tag">Bable Visor</span>
      <span class="img-title" title="{display_title}">{display_title}</span>
    </div>
    <div class="top-toolbar-right">
      <button class="btn-tool" onclick="toggleZoom()">🔍 Zoom</button>
      <a class="btn-tool" href="{current_img_url}" download="{clean_name}">⬇ Guardar</a>
      <a class="btn-tool" href="/search">🌐 Navegador</a>
    </div>
  </div>

  <div class="main-canvas-area">
    {"<div class='image-frame' id='imageFrame'><img id='mainImage' class='main-image' src='" + current_img_url + "' alt='" + clean_name + "'/></div>" if current_img_url else "<div class='empty-state'>No hay imágenes generadas aún</div>"}
  </div>

  <div class="bottom-gallery-bar">
    <div class="gallery-header">
      <span class="gallery-title">Imágenes Creadas en Bable</span>
      <span class="gallery-count">{len(img_names)} imágenes</span>
    </div>
    <div class="thumbs-strip">
      {thumbs_html if thumbs_html else "<span style='font-size:11px;color:#64748b;'>No hay otras imágenes</span>"}
    </div>
  </div>

  <script>
    var isZoomed = false;
    function toggleZoom() {{
      var img = document.getElementById("mainImage");
      if (!img) return;
      isZoomed = !isZoomed;
      if (isZoomed) {{
        img.style.maxHeight = "none";
        img.style.maxWidth = "none";
        img.style.transform = "scale(1.5)";
        img.style.cursor = "zoom-out";
      }} else {{
        img.style.maxHeight = "calc(100vh - 190px)";
        img.style.maxWidth = "90vw";
        img.style.transform = "none";
        img.style.cursor = "zoom-in";
      }}
    }}
    var imgEl = document.getElementById("mainImage");
    if (imgEl) {{
      imgEl.style.cursor = "zoom-in";
      imgEl.addEventListener("click", toggleZoom);
    }}
  </script>
</body>
</html>"""
        self._respond_html(html)

    def _handle_home(self):
        html = f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <title>Navegador Antigravity</title>
  <style>
    body {{
      background: #131417;
      color: #f0f1f4;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      margin: 0;
      padding: 40px 20px;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      min-height: 80vh;
    }}
    .logo {{
      font-size: 38px;
      font-weight: 700;
      color: #2563eb;
      margin-bottom: 24px;
      display: flex;
      align-items: center;
      gap: 12px;
    }}
    .search-box {{
      width: 100%;
      max-width: 540px;
      display: flex;
      align-items: center;
      background: #1e2024;
      border: 1px solid rgba(255, 255, 255, 0.14);
      border-radius: 28px;
      padding: 6px 16px;
      box-shadow: 0 8px 24px rgba(0,0,0,0.4);
    }}
    .search-input {{
      flex: 1;
      background: transparent;
      border: none;
      outline: none;
      color: #ffffff;
      font-size: 15px;
      padding: 8px 10px;
    }}
    .search-btn {{
      background: #2563eb;
      color: #ffffff;
      border: none;
      border-radius: 20px;
      padding: 8px 18px;
      font-size: 13px;
      font-weight: 600;
      cursor: pointer;
    }}
    .search-btn:hover {{ background: #1d4ed8; }}
    .shortcuts {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      margin-top: 30px;
      max-width: 540px;
      justify-content: center;
    }}
    .pill {{
      background: rgba(255, 255, 255, 0.06);
      border: 1px solid rgba(255, 255, 255, 0.1);
      border-radius: 16px;
      padding: 6px 14px;
      color: #9aa0a6;
      text-decoration: none;
      font-size: 12.5px;
      transition: all 0.15s;
    }}
    .pill:hover {{
      background: rgba(37, 99, 235, 0.2);
      color: #ffffff;
      border-color: #2563eb;
    }}
  </style>
</head>
<body>
  <div class="logo">
    <svg width="32" height="32" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2L2 22h20L12 2zm0 4.5l6.5 13.5H5.5L12 6.5z"/></svg>
    <span>Navegador Web Antigravity</span>
  </div>

  <form class="search-box" action="/search" method="GET">
    <input class="search-input" type="text" name="q" placeholder="Buscar en la web o escribir una URL..." autofocus>
    <button class="search-btn" type="submit">Buscar</button>
  </form>

  <div class="shortcuts">
    <a class="pill" href="/browse?url=https://news.ycombinator.com">⚡ Hacker News</a>
    <a class="pill" href="/browse?url=https://github.com">🐙 GitHub</a>
    <a class="pill" href="/browse?url=https://en.wikipedia.org">📚 Wikipedia</a>
    <a class="pill" href="/browse?url=https://docs.python.org/3/">🐍 Python Docs</a>
    <a class="pill" href="/browse?url=https://console.groq.com/keys">🔥 GroqCloud</a>
    <a class="pill" href="/search?q=inteligencia+artificial+noticias">📰 Noticias IA</a>
  </div>
</body>
</html>"""
        self._respond_html(html)

    def _handle_search(self, query: str):
        if not query:
            self._handle_home()
            return

        # Si el usuario introdujo directamente una URL en el campo de búsqueda
        if query.startswith("http://") or query.startswith("https://") or ("." in query and " " not in query and len(query.split(".")[-1]) >= 2):
            target = query if (query.startswith("http://") or query.startswith("https://")) else "https://" + query
            self.send_response(302)
            self.send_header("Location", f"/browse?url={urllib.parse.quote(target)}")
            self.end_headers()
            return

        # Realizar búsqueda web en tiempo real
        results = []
        try:
            if WebSearchTool:
                tool = WebSearchTool()
                tool_res = tool.execute(query=query, max_results=8)
                if tool_res.data:
                    results = tool_res.data
            if not results:
                try:
                    from duckduckgo_search import DDGS
                    with DDGS() as ddgs:
                        raw = list(ddgs.text(query, max_results=8))
                    results = [{"title": r.get("title"), "url": r.get("href"), "snippet": r.get("body")} for r in raw]
                except Exception:
                    pass
        except Exception as e:
            pass

        items_html = ""
        for r in results:
            title = r.get("title") or "Sin título"
            url = r.get("url") or ""
            snippet = r.get("snippet") or ""
            proxied_url = f"/browse?url={urllib.parse.quote(url)}"
            items_html += f"""
            <div class="result-item">
              <a class="result-title" href="{proxied_url}">{title}</a>
              <div class="result-url">{url}</div>
              <div class="result-snippet">{snippet}</div>
            </div>
            """

        if not items_html:
            items_html = f"""
            <div style="padding: 30px; text-align: center; color: #9aa0a6;">
              <p>No se encontraron resultados directos para "<strong>{query}</strong>".</p>
              <p style="margin-top: 10px;">
                <a class="btn-direct" href="/browse?url={urllib.parse.quote('https://duckduckgo.com/?q=' + query)}">Buscar en DuckDuckGo Web</a>
                <a class="btn-direct" href="/browse?url={urllib.parse.quote('https://www.google.com/search?q=' + query)}">Buscar en Google Web</a>
              </p>
            </div>
            """

        html = f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <title>Búsqueda: {query}</title>
  <style>
    body {{
      background: #131417;
      color: #f0f1f4;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      margin: 0;
      padding: 16px 24px;
    }}
    .search-header {{
      display: flex;
      align-items: center;
      gap: 14px;
      padding-bottom: 16px;
      border-bottom: 1px solid rgba(255, 255, 255, 0.08);
      margin-bottom: 20px;
    }}
    .search-input {{
      flex: 1;
      max-width: 560px;
      background: #1e2024;
      border: 1px solid rgba(255, 255, 255, 0.15);
      border-radius: 20px;
      padding: 7px 16px;
      color: #ffffff;
      font-size: 13.5px;
      outline: none;
    }}
    .result-list {{
      display: flex;
      flex-direction: column;
      gap: 20px;
      max-width: 720px;
    }}
    .result-item {{
      display: flex;
      flex-direction: column;
      gap: 4px;
    }}
    .result-title {{
      color: #60a5fa;
      font-size: 16px;
      font-weight: 600;
      text-decoration: none;
    }}
    .result-title:hover {{
      text-decoration: underline;
    }}
    .result-url {{
      color: #34d399;
      font-size: 11.5px;
      word-break: break-all;
    }}
    .result-snippet {{
      color: #9aa0a6;
      font-size: 13px;
      line-height: 1.5;
    }}
    .btn-direct {{
      display: inline-block;
      background: #2563eb;
      color: #ffffff;
      padding: 6px 14px;
      border-radius: 8px;
      text-decoration: none;
      font-size: 12px;
      margin: 4px;
    }}
  </style>
</head>
<body>
  <div class="search-header">
    <a href="/" style="color:#2563eb; font-weight:700; text-decoration:none; font-size:16px;">▲ Antigravity</a>
    <form action="/search" method="GET" style="display:contents;">
      <input class="search-input" type="text" name="q" value="{query}">
    </form>
  </div>
  <div class="result-list">
    {items_html}
  </div>
</body>
</html>"""
        self._respond_html(html)

    def _handle_browse(self, target_url: str):
        if not target_url:
            self._handle_home()
            return

        if not target_url.startswith("http://") and not target_url.startswith("https://"):
            target_url = "https://" + target_url

        # Soporte especial para YouTube (evitar el error de iframe)
        yt_match = re.search(r'(?:youtube\.com\/(?:watch\?v=|embed\/|shorts\/)|youtu\.be\/)([a-zA-Z0-9_-]{11})', target_url)
        if yt_match:
            video_id = yt_match.group(1)
            embed_html = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <title>YouTube Player</title>
  <style>
    body, html {{ margin: 0; padding: 0; width: 100%; height: 100%; background: #000; overflow: hidden; }}
    iframe {{ width: 100%; height: 100%; border: none; }}
  </style>
</head>
<body>
  <iframe src="https://www.youtube.com/embed/{video_id}?autoplay=1" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture" allowfullscreen></iframe>
</body>
</html>"""
            self._respond_html(embed_html)
            return

        if "youtube.com" in target_url and not yt_match:
            # Página principal de YouTube o búsqueda
            yt_landing = f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <style>
    body {{ background: #0f0f0f; color: #fff; font-family: sans-serif; padding: 30px; text-align: center; }}
    input {{ width: 80%; max-width: 480px; padding: 10px 16px; background: #222; border: 1px solid #444; border-radius: 20px; color: #fff; }}
    button {{ padding: 10px 18px; background: #cc0000; color: #fff; border: none; border-radius: 20px; font-weight: bold; cursor: pointer; }}
  </style>
</head>
<body>
  <h2 style="color:#ff0000;">YouTube en Antigravity</h2>
  <p style="color:#aaa;">Pega el enlace de cualquier vídeo o escribe el ID para reproducirlo sin restricciones:</p>
  <form onsubmit="event.preventDefault(); var v = document.getElementById('ytUrl').value; window.location.href='/browse?url=' + encodeURIComponent(v);">
    <input type="text" id="ytUrl" placeholder="https://www.youtube.com/watch?v=..." autofocus>
    <button type="submit">Ver Vídeo</button>
  </form>
</body>
</html>"""
            self._respond_html(yt_landing)
            return

        # Fetching web real con eliminación de X-Frame-Options y CSP
        try:
            headers = {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0"
                ),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
            }
            with httpx.Client(timeout=15.0, follow_redirects=True, headers=headers) as client:
                res = client.get(target_url)

            content_type = res.headers.get("content-type", "text/html")

            # Si es contenido no HTML (ej. imagen, css, json)
            if "text/html" not in content_type:
                self.send_response(res.status_code)
                self.send_header("Content-Type", content_type)
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(res.content)
                return

            body = res.text
            final_url = str(res.url)

            # Inyectar etiqueta <base> para que los recursos relativos resuelvan al host original
            base_tag = f'<base href="{final_url}">'
            if "<head>" in body:
                body = body.replace("<head>", f"<head>{base_tag}", 1)
            else:
                body = base_tag + body

            # Inyectar script de captura de clics para mantener la navegación dentro del proxy
            nav_interceptor = f"""
            <script>
              document.addEventListener('click', function(e) {{
                var a = e.target.closest('a');
                if (a && a.href && !a.href.startsWith('javascript:') && !a.href.startsWith('#')) {{
                  e.preventDefault();
                  window.location.href = 'http://127.0.0.1:{SERVER_PORT}/browse?url=' + encodeURIComponent(a.href);
                }}
              }}, true);
            </script>
            """
            if "</body>" in body:
                body = body.replace("</body>", f"{nav_interceptor}</body>", 1)
            else:
                body += nav_interceptor

            self._respond_html(body, status=res.status_code)
        except Exception as e:
            error_html = f"""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><title>Error al cargar página</title>
<style>body{{background:#131417; color:#f0f1f4; font-family:sans-serif; padding:30px;}}</style>
</head>
<body>
  <h3>No se pudo cargar la página directamente</h3>
  <p style="color:#9aa0a6;">Detalle: {str(e)}</p>
  <p><a href="/browse?url={urllib.parse.quote(target_url)}" style="color:#60a5fa;">Reintentar</a> | <a href="/search?q={urllib.parse.quote(target_url)}" style="color:#60a5fa;">Buscar en la Web</a></p>
</body>
</html>"""
            self._respond_html(error_html, status=502)

    def _respond_html(self, html_content: str, status: int = 200):
        data = html_content.encode("utf-8", errors="replace")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        # DESBLOQUEO TOTAL: sin X-Frame-Options ni CSP restrictivo
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(data)


def start_sidecar_proxy_server(port: int = SERVER_PORT) -> int:
    """Inicia el servidor proxy del Sidecar en segundo plano si no está ya activo."""
    global _SERVER_INSTANCE
    if _SERVER_INSTANCE is not None:
        return port

    def _run_server():
        global _SERVER_INSTANCE
        try:
            HTTPServer.allow_reuse_address = True
            server = HTTPServer(("127.0.0.1", port), SidecarProxyHandler)
            _SERVER_INSTANCE = server
            server.serve_forever()
        except OSError:
            # Puerto en uso, intentar puerto alternativo
            try:
                HTTPServer.allow_reuse_address = True
                server = HTTPServer(("127.0.0.1", port + 1), SidecarProxyHandler)
                _SERVER_INSTANCE = server
                server.serve_forever()
            except Exception:
                pass
        except Exception:
            pass

    t = threading.Thread(target=_run_server, daemon=True, name="SidecarProxyServer")
    t.start()
    return port


if __name__ == "__main__":
    print(f"Bable Sidecar Web Engine iniciando en http://127.0.0.1:{SERVER_PORT}...")
    server = HTTPServer(("127.0.0.1", SERVER_PORT), SidecarProxyHandler)
    server.serve_forever()
