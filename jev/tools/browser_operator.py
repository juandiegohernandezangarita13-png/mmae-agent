"""
Subsistema de Navegación y Automatización Web Autónoma para Jeff (Browser-Use & Playwright Engine).

Combina dos capas de automatización:
1. Capa Táctica Autónoma (Browser-Use): El agente delega una meta web completa (ej: "Buscar vuelos económicos",
   "Navegar en GitHub, descargar el último release y extraer los cambios") a un agente web multimodal.
2. Capa Atómica Interactiva (Playwright + Edge Nativo): Acciones paso a paso directas (navigate, click, type,
   extract, screenshot) ejecutadas sin requerir descargas pesadas utilizando el Microsoft Edge preinstalado en Windows.
"""
from __future__ import annotations

import os
import sys
import json
import time
import asyncio
from pathlib import Path
from typing import Dict, Any, List, Optional

from jev.tools.base import BaseTool, ToolResult
from jev.config import default_config


class BrowserUseOperatorTool(BaseTool):
    """Herramienta de navegación e interacción web autónoma para Jeff."""
    name = "browser_navigate_and_act"
    description = (
        "Navega por la web de forma autónoma e interactiva usando Browser-Use y Playwright. "
        "Puede resolver metas completas (ej: 'Entrar a GitHub, buscar el repo X y extraer el número de estrellas') "
        "o ejecutar pasos puntuales ('navigate', 'click', 'type', 'extract_text', 'screenshot'). "
        "Soporta navegación visible (headless=False) para que el usuario observe la pantalla."
    )
    parameters = {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["autonomous_task", "step_navigate", "step_click", "step_type", "step_extract", "screenshot"],
                "description": "Modo de operación: 'autonomous_task' (resuelve una meta web completa con Browser-Use), 'step_navigate' (ir a URL), 'step_click' (clic por selector o texto), 'step_type' (escribir en campo), 'step_extract' (extraer texto/HTML), 'screenshot' (capturar página web).",
                "default": "autonomous_task"
            },
            "task": {
                "type": "string",
                "description": "Instrucción de la tarea autónoma (requerido para mode='autonomous_task', ej: 'Busca los últimos lanzamientos de Python en python.org y extrae sus versiones')."
            },
            "url": {
                "type": "string",
                "description": "URL a cargar (para step_navigate, ej: 'https://news.ycombinator.com')."
            },
            "selector": {
                "type": "string",
                "description": "Selector CSS o texto del elemento a interactuar (para step_click o step_type, ej: 'input[name=\"q\"]', 'text=Buscar')."
            },
            "text": {
                "type": "string",
                "description": "Texto a ingresar en el campo seleccionado (para step_type)."
            },
            "press_enter": {
                "type": "boolean",
                "description": "Si es True, presiona la tecla Enter tras escribir el texto.",
                "default": False
            },
            "headless": {
                "type": "boolean",
                "description": "Si es False, muestra la ventana del navegador en la pantalla frente al usuario.",
                "default": False
            },
            "max_steps": {
                "type": "integer",
                "description": "Límite máximo de pasos para tareas autónomas (defecto 15).",
                "default": 15
            }
        },
        "required": ["mode"]
    }

    # Estado persistente singleton para sesión interactiva de navegador
    _playwright = None
    _browser = None
    _page = None

    def __init__(self, workspace_dir: Optional[Path] = None):
        self.workspace_dir = workspace_dir or default_config.workspace_dir
        self.screenshots_dir = default_config.screenshots_dir
        self.screenshots_dir.mkdir(parents=True, exist_ok=True)

    def execute(
        self,
        mode: str = "autonomous_task",
        task: Optional[str] = None,
        url: Optional[str] = None,
        selector: Optional[str] = None,
        text: Optional[str] = None,
        press_enter: bool = False,
        headless: bool = False,
        max_steps: int = 15,
        **kwargs
    ) -> ToolResult:
        mode = (mode or "autonomous_task").strip().lower()

        # -------------------------------------------------------------
        # 1. Tarea Autónoma con Browser-Use
        # -------------------------------------------------------------
        if mode == "autonomous_task":
            if not task:
                return ToolResult(success=False, output="", error="Debes especificar 'task' para el modo autonomous_task.")

            return self._run_browser_use_task(task=task, headless=headless, max_steps=max_steps)

        # -------------------------------------------------------------
        # 2. Paso a paso interactivo con Playwright + Edge
        # -------------------------------------------------------------
        try:
            from playwright.sync_api import sync_playwright

            self._ensure_browser(headless=headless)
            page = self._page

            if mode == "step_navigate":
                if not url:
                    return ToolResult(success=False, output="", error="Debes especificar 'url' para step_navigate.")
                if not url.startswith("http://") and not url.startswith("https://"):
                    url = f"https://{url}"

                page.goto(url, wait_until="domcontentloaded", timeout=30000)
                title = page.title()
                return ToolResult(
                    success=True,
                    output=f"✓ Navegador cargó exitosamente: {url}\n• Título de la página: '{title}'",
                    data={"url": url, "title": title}
                )

            elif mode == "step_click":
                if not selector:
                    return ToolResult(success=False, output="", error="Debes indicar 'selector' para hacer clic.")

                page.click(selector, timeout=10000)
                time.sleep(0.5)
                return ToolResult(success=True, output=f"✓ Clic ejecutado en el elemento '{selector}'.", data={"selector": selector})

            elif mode == "step_type":
                if not selector or text is None:
                    return ToolResult(success=False, output="", error="Debes indicar 'selector' y 'text' a escribir.")

                page.fill(selector, text)
                summary = f"✓ Texto '{text}' ingresado en '{selector}'"
                if press_enter:
                    page.press(selector, "Enter")
                    time.sleep(1.0)
                    summary += " con [Enter]"
                return ToolResult(success=True, output=summary, data={"selector": selector, "text": text})

            elif mode == "step_extract":
                content = page.inner_text("body")
                lines = [l.strip() for l in content.splitlines() if l.strip()]
                preview = "\n".join(lines[:40])
                return ToolResult(
                    success=True,
                    output=f"📄 [CONTENIDO EXTRAÍDO DE LA PÁGINA (Título: '{page.title()}')]:\n{preview}",
                    data={"title": page.title(), "url": page.url, "text_sample": preview}
                )

            elif mode == "screenshot":
                timestamp = int(time.time() * 1000)
                shot_path = self.screenshots_dir / f"web_capture_{timestamp}.png"
                page.screenshot(path=str(shot_path), full_page=False)
                return ToolResult(
                    success=True,
                    output=f"📸 Captura web guardada en: {shot_path.name}",
                    data={"screenshot_path": str(shot_path), "url": page.url}
                )

        except Exception as e:
            return ToolResult(success=False, output="", error=f"Error en navegador interactivo ({mode}): {e}")

        return ToolResult(success=False, output="", error=f"Modo '{mode}' desconocido.")

    def _ensure_browser(self, headless: bool = False):
        """Inicializa o reutiliza la instancia de Playwright con canal nativo de Microsoft Edge."""
        from playwright.sync_api import sync_playwright

        if self._playwright is None:
            self._playwright = sync_playwright().start()

        if self._browser is None:
            # Intentar lanzar Microsoft Edge preinstalado en Windows
            try:
                self._browser = self._playwright.chromium.launch(
                    channel="msedge",
                    headless=headless,
                    args=["--disable-blink-features=AutomationControlled", "--start-maximized"]
                )
            except Exception:
                # Fallback a Google Chrome o Chromium estándar
                self._browser = self._playwright.chromium.launch(
                    headless=headless,
                    args=["--disable-blink-features=AutomationControlled"]
                )

        if self._page is None:
            context = self._browser.new_context(no_viewport=True if not headless else False)
            self._page = context.new_page()

    def _run_browser_use_task(self, task: str, headless: bool, max_steps: int) -> ToolResult:
        """Ejecuta una meta web autónoma usando la librería Browser-Use."""
        api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or getattr(default_config, "gemini_api_key", "")
        if not api_key:
            return ToolResult(
                success=False,
                output="",
                error="Se requiere GEMINI_API_KEY en .env para operar Browser-Use de forma multimodal."
            )

        async def _async_runner():
            from browser_use import Agent
            from browser_use.browser.browser import Browser, BrowserConfig
            from langchain_google_genai import ChatGoogleGenerativeAI

            # Modelo multimodal para visión de página
            llm = ChatGoogleGenerativeAI(
                model="gemini-2.0-flash-exp",
                google_api_key=api_key,
                temperature=0.1
            )

            browser = Browser(
                config=BrowserConfig(
                    headless=headless,
                    extra_chromium_args=["--disable-blink-features=AutomationControlled"]
                )
            )

            agent = Agent(
                task=task,
                llm=llm,
                browser=browser,
                max_actions_per_step=3,
                max_failures=3
            )

            history = await agent.run(max_steps=max_steps)
            await browser.close()
            return history

        try:
            # Si estamos en un hilo principal o secundario
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

            if loop.is_running():
                # Ejecutar en hilo de fondo si el bucle actual ya está activo
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    history = executor.submit(lambda: asyncio.run(_async_runner())).result()
            else:
                history = loop.run_until_complete(_async_runner())

            final_result = history.final_result() or "Tarea web finalizada con éxito."
            return ToolResult(
                success=True,
                output=f"🌐 [BROWSER-USE: TAREA WEB COMPLETADA]\n• Meta: {task}\n• Resultado extraído:\n{final_result}",
                data={"result": final_result}
            )
        except Exception as e:
            # Si la versión de langchain o browser-use requiere fallback interactivo
            return ToolResult(
                success=False,
                output="",
                error=f"Error en ejecución autónoma Browser-Use: {e}. Puedes usar mode='step_navigate' para interactuar directamente."
            )
