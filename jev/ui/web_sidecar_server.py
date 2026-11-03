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
from typing import Optional

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
        elif path == "/status":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(b'{"status": "ok", "service": "Bable Web Engine"}')
        else:
            # Página de inicio del navegador Bable
            self._handle_home()

    def _handle_image(self, img_name: str):
        """Sirve imágenes generadas por el agente de forma segura y directa."""
        if not img_name:
            self.send_response(400)
            self.end_headers()
            return

        # Limpiar nombre para evitar path traversal
        clean_name = os.path.basename(img_name)
        from jev.config import BASE_DIR
        img_path = Path(BASE_DIR) / "data" / "generated_images" / clean_name
        if not img_path.exists():
            # Buscar en directorio actual
            img_path = Path("data/generated_images") / clean_name

        if img_path.exists():
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
            self.end_headers()

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
            server = HTTPServer(("127.0.0.1", port), SidecarProxyHandler)
            _SERVER_INSTANCE = server
            server.serve_forever()
        except OSError:
            # Puerto en uso, intentar puerto alternativo
            try:
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
