"""
Herramientas de búsqueda y navegación web para JEV.
Permite buscar en Internet mediante DuckDuckGo y extraer contenido legible de páginas web.
"""
from typing import Dict, Any, List, Optional
import json
import httpx
from bs4 import BeautifulSoup
import trafilatura

try:
    from ddgs import DDGS
except ImportError:
    from duckduckgo_search import DDGS

from jev.tools.base import BaseTool, ToolResult


class WebSearchTool(BaseTool):
    """Buscador en Internet usando DuckDuckGo (sin API key requerida)."""
    name = "search_web"
    description = (
        "Busca información en Internet mediante DuckDuckGo. "
        "Devuelve una lista de los resultados más relevantes con título, enlace y resumen."
    )
    parameters = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Término o consulta de búsqueda en Internet."
            },
            "max_results": {
                "type": "integer",
                "description": "Número máximo de resultados a devolver (por defecto 5)."
            }
        },
        "required": ["query"]
    }

    def execute(self, query: str, max_results: int = 5, **kwargs) -> ToolResult:
        try:
            results = []
            with DDGS() as ddgs:
                raw_results = list(ddgs.text(query, max_results=max_results))

            if not raw_results:
                return ToolResult(
                    success=True,
                    output=f"No se encontraron resultados en la web para: '{query}'."
                )

            formatted_output = [f"Resultados de búsqueda web para '{query}':\n"]
            for i, r in enumerate(raw_results, 1):
                title = r.get("title", "Sin título")
                href = r.get("href", "")
                body = r.get("body", "")
                formatted_output.append(f"{i}. {title}\n   URL: {href}\n   Resumen: {body}\n")
                results.append({"title": title, "url": href, "snippet": body})

            return ToolResult(
                success=True,
                output="\n".join(formatted_output),
                data={"query": query, "results": results}
            )
        except Exception as e:
            return ToolResult(
                success=False,
                output="",
                error=f"Error al realizar búsqueda web: {str(e)}"
            )


class WebFetchTool(BaseTool):
    """Extrae el contenido textual limpio de una página web."""
    name = "fetch_webpage"
    description = (
        "Descarga y extrae el texto principal y legible de una URL web, "
        "eliminando anuncios, menús y estilos innecesarios."
    )
    parameters = {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "Dirección URL de la página web a leer (debe incluir http:// o https://)."
            },
            "max_chars": {
                "type": "integer",
                "description": "Límite máximo de caracteres de texto a retornar (por defecto 5000)."
            }
        },
        "required": ["url"]
    }

    def execute(self, url: str, max_chars: int = 5000, **kwargs) -> ToolResult:
        try:
            headers = {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                )
            }
            response = httpx.get(url, headers=headers, timeout=15.0, follow_redirects=True)
            if response.status_code >= 400:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Error HTTP {response.status_code} al acceder a {url}"
                )

            html_content = response.text

            # Intentar extracción inteligente con trafilatura
            extracted_text = trafilatura.extract(html_content, include_comments=False, include_tables=True)

            # Fallback con BeautifulSoup si trafilatura no extrae suficiente texto
            if not extracted_text or len(extracted_text.strip()) < 50:
                soup = BeautifulSoup(html_content, "html.parser")
                # Eliminar scripts y estilos
                for tag in soup(["script", "style", "nav", "footer", "header", "noscript"]):
                    tag.decompose()
                extracted_text = soup.get_text(separator="\n", strip=True)

            if not extracted_text:
                return ToolResult(
                    success=True,
                    output=f"No se pudo extraer texto visible relevante de la página {url}."
                )

            # Truncar si excede el límite
            text_sample = extracted_text[:max_chars]
            truncated_note = ""
            if len(extracted_text) > max_chars:
                truncated_note = f"\n\n[... Truncado. Mostrando {max_chars} de {len(extracted_text)} caracteres totales ...]"

            output_msg = f"--- Contenido extraído de {url} ---\n\n{text_sample}{truncated_note}"
            return ToolResult(
                success=True,
                output=output_msg,
                data={"url": url, "full_length": len(extracted_text), "retrieved_length": len(text_sample)}
            )
        except Exception as e:
            return ToolResult(
                success=False,
                output="",
                error=f"Error al descargar contenido de {url}: {str(e)}"
            )
