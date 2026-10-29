"""
Módulo Generador y Estructurador de Artefactos Web Reactivos (Web Sandbox).
Genera sitios y aplicaciones web autocontenidas en HTML5 con soporte nativo para
Tailwind CSS vía CDN, temas oscuros/cyberpunk, componentes interactivos y visualización en tiempo real.
"""
from typing import Dict, Any, List, Optional
from pathlib import Path
import json
import re

from jev.tools.base import BaseTool, ToolResult
from jev.config import default_config


class WebBuilderTool(BaseTool):
    """Herramienta para generar y estructurar páginas y artefactos web modernos e interactivos."""
    name = "skill_web_builder"
    description = (
        "Estructura y compila artefactos web modernos completos en HTML5 con Tailwind CSS (CDN), "
        "componentes interactivos (gráficos, métricas, tablas, calculadoras reactivas) y los despacha "
        "automáticamente para previsualización en el visor de artefactos web de JEV."
    )
    parameters = {
        "type": "object",
        "properties": {
            "template_type": {
                "type": "string",
                "description": "Tipo de plantilla web: 'dashboard', 'landing', 'interactive_calculator', 'data_table', 'custom'",
                "enum": ["dashboard", "landing", "interactive_calculator", "data_table", "custom"],
                "default": "dashboard"
            },
            "title": {
                "type": "string",
                "description": "Título principal de la aplicación o página web",
                "default": "JEV Web Artifact"
            },
            "theme": {
                "type": "string",
                "description": "Esquema cromático y de diseño: 'dark_cyber', 'dark_slate', 'light_clean', 'emerald_tech'",
                "enum": ["dark_cyber", "dark_slate", "light_clean", "emerald_tech"],
                "default": "dark_cyber"
            },
            "components": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Componentes a ensamblar: 'navbar', 'hero', 'stat_cards', 'charts', 'data_table', 'interactive_form', 'footer'",
                "default": ["navbar", "stat_cards", "charts", "data_table"]
            },
            "custom_html": {
                "type": "string",
                "description": "Fragmento HTML personalizado a incrustar dentro del contenedor principal",
                "default": ""
            },
            "custom_css": {
                "type": "string",
                "description": "Reglas de estilo CSS personalizadas adicionales",
                "default": ""
            },
            "custom_js": {
                "type": "string",
                "description": "Lógica JavaScript interactiva a ejecutar en el contexto de la página",
                "default": ""
            },
            "save_to_workspace": {
                "type": "boolean",
                "description": "Si True, guarda el archivo .html en el directorio workspace/web_artifacts/",
                "default": True
            },
            "output_filename": {
                "type": "string",
                "description": "Nombre de archivo sugerido (ej. 'dashboard.html')",
                "default": "index.html"
            }
        },
        "required": ["template_type", "title"]
    }

    def __init__(self, workspace_dir: Optional[Path] = None):
        self.workspace_dir = workspace_dir or default_config.workspace_dir

    def execute(self, **kwargs) -> ToolResult:
        template_type = kwargs.get("template_type", "dashboard")
        title = kwargs.get("title", "JEV Web Artifact")
        theme = kwargs.get("theme", "dark_cyber")
        components = kwargs.get("components", ["navbar", "stat_cards", "charts"])
        custom_html = kwargs.get("custom_html", "")
        custom_css = kwargs.get("custom_css", "")
        custom_js = kwargs.get("custom_js", "")
        save_file = bool(kwargs.get("save_to_workspace", True))
        output_filename = kwargs.get("output_filename", "index.html")

        try:
            html_content = self.compile_web_artifact(
                template_type=template_type,
                title=title,
                theme=theme,
                components=components,
                custom_html=custom_html,
                custom_css=custom_css,
                custom_js=custom_js
            )

            file_path = None
            if save_file:
                target_dir = self.workspace_dir / "web_artifacts"
                target_dir.mkdir(parents=True, exist_ok=True)
                clean_name = re.sub(r'[^a-zA-Z0-9_\-\.]', '_', output_filename)
                if not clean_name.endswith(".html"):
                    clean_name += ".html"
                file_path = target_dir / clean_name
                file_path.write_text(html_content, encoding="utf-8")

            return ToolResult(
                success=True,
                output=f"Artefacto web '{title}' compilado con éxito ({len(html_content)} bytes). Listo para vista previa en vivo.",
                data={
                    "html": html_content,
                    "title": title,
                    "template": template_type,
                    "theme": theme,
                    "file_path": str(file_path) if file_path else None
                }
            )
        except Exception as e:
            return ToolResult(
                success=False,
                output="",
                error=f"Error al compilar artefacto web: {str(e)}"
            )

    def compile_web_artifact(
        self,
        template_type: str = "dashboard",
        title: str = "JEV Web Artifact",
        theme: str = "dark_cyber",
        components: Optional[List[str]] = None,
        custom_html: str = "",
        custom_css: str = "",
        custom_js: str = ""
    ) -> str:
        """Ensambla un documento HTML5 completo con Tailwind y componentes interactivos."""
        components = components or ["navbar", "stat_cards", "charts"]
        theme_classes = self._get_theme_classes(theme)

        # Generar secciones modulares
        sections = []
        if "navbar" in components:
            sections.append(self._generate_navbar(title, theme_classes))
        
        main_content = []
        if template_type == "interactive_calculator":
            main_content.append(self._generate_calculator_ui(theme_classes))
        elif template_type == "landing":
            if "hero" in components or True:
                main_content.append(self._generate_hero_section(title, theme_classes))
        
        if "stat_cards" in components:
            main_content.append(self._generate_stat_cards(theme_classes))
        if "charts" in components:
            main_content.append(self._generate_chart_card(theme_classes))
        if "data_table" in components:
            main_content.append(self._generate_data_table(theme_classes))
        if custom_html:
            main_content.append(f"""
            <div class="my-6 p-6 rounded-xl {theme_classes['card_bg']} border {theme_classes['border']}">
                {custom_html}
            </div>
            """)

        sections.append(f"""
        <main class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-8">
            {''.join(main_content)}
        </main>
        """)

        if "footer" in components or True:
            sections.append(self._generate_footer(title, theme_classes))

        body_html = "\n".join(sections)

        # Documento completo con CDNs de Tailwind y Chart.js
        doc = f"""<!DOCTYPE html>
<html lang="es" class="{theme_classes['html_class']}">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title}</title>
  <!-- Tailwind CSS CDN -->
  <script src="https://cdn.tailwindcss.com"></script>
  <!-- Chart.js CDN para analíticas interactivas -->
  <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
  <style>
    @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600;800&family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap');
    body {{
      font-family: 'Plus Jakarta Sans', sans-serif;
    }}
    code, pre, .font-mono {{
      font-family: 'JetBrains Mono', monospace;
    }}
    {custom_css}
  </style>
</head>
<body class="{theme_classes['body_bg']} {theme_classes['text_main']} min-h-screen flex flex-direction-column">
  <div class="w-full flex-1 flex flex-col">
    {body_html}
  </div>

  <script>
    // Inicialización de componentes gráficos
    document.addEventListener('DOMContentLoaded', () => {{
      const ctx = document.getElementById('analyticsChart');
      if (ctx && window.Chart) {{
        new Chart(ctx, {{
          type: 'line',
          data: {{
            labels: ['00:00', '04:00', '08:00', '12:00', '16:00', '20:00', '24:00'],
            datasets: [
              {{
                label: 'Carga de Cómputo (FLOPs)',
                data: [35, 42, 68, 85, 74, 92, 88],
                borderColor: '{theme_classes["chart_accent"]}',
                backgroundColor: '{theme_classes["chart_fill"]}',
                borderWidth: 2,
                tension: 0.35,
                fill: true
              }},
              {{
                label: 'Rendimiento Cuántico (%)',
                data: [60, 65, 72, 80, 89, 94, 96],
                borderColor: '#10b981',
                backgroundColor: 'rgba(16, 185, 129, 0.08)',
                borderWidth: 2,
                tension: 0.35,
                fill: true
              }}
            ]
          }},
          options: {{
            responsive: true,
            maintainAspectRatio: false,
            plugins: {{
              legend: {{
                labels: {{ color: '{theme_classes["text_muted_hex"]}' }}
              }}
            }},
            scales: {{
              x: {{ grid: {{ color: '{theme_classes["grid_line_hex"]}' }}, ticks: {{ color: '{theme_classes["text_muted_hex"]}' }} }},
              y: {{ grid: {{ color: '{theme_classes["grid_line_hex"]}' }}, ticks: {{ color: '{theme_classes["text_muted_hex"]}' }} }}
            }}
          }}
        }});
      }}
    }});

    {custom_js}
  </script>
</body>
</html>"""
        return doc

    def _get_theme_classes(self, theme: str) -> Dict[str, str]:
        if theme == "light_clean":
            return {
                "html_class": "light",
                "body_bg": "bg-slate-50",
                "card_bg": "bg-white",
                "text_main": "text-slate-900",
                "text_muted": "text-slate-500",
                "text_muted_hex": "#64748b",
                "border": "border-slate-200",
                "accent_badge": "bg-indigo-50 text-indigo-700 border-indigo-200",
                "btn_primary": "bg-indigo-600 hover:bg-indigo-700 text-white shadow-sm",
                "chart_accent": "#6366f1",
                "chart_fill": "rgba(99, 102, 241, 0.12)",
                "grid_line_hex": "rgba(226, 232, 240, 0.8)"
            }
        elif theme == "emerald_tech":
            return {
                "html_class": "dark",
                "body_bg": "bg-neutral-950",
                "card_bg": "bg-neutral-900/90",
                "text_main": "text-neutral-100",
                "text_muted": "text-neutral-400",
                "text_muted_hex": "#a3a3a3",
                "border": "border-neutral-800",
                "accent_badge": "bg-emerald-950/60 text-emerald-400 border-emerald-800/60",
                "btn_primary": "bg-emerald-500 hover:bg-emerald-400 text-neutral-950 font-bold",
                "chart_accent": "#10b981",
                "chart_fill": "rgba(16, 185, 129, 0.15)",
                "grid_line_hex": "rgba(38, 38, 38, 0.6)"
            }
        elif theme == "dark_slate":
            return {
                "html_class": "dark",
                "body_bg": "bg-slate-950",
                "card_bg": "bg-slate-900/80",
                "text_main": "text-slate-100",
                "text_muted": "text-slate-400",
                "text_muted_hex": "#94a3b8",
                "border": "border-slate-800",
                "accent_badge": "bg-sky-950/60 text-sky-400 border-sky-800/60",
                "btn_primary": "bg-sky-500 hover:bg-sky-400 text-slate-950 font-bold",
                "chart_accent": "#0ea5e9",
                "chart_fill": "rgba(14, 165, 233, 0.15)",
                "grid_line_hex": "rgba(30, 41, 59, 0.8)"
            }
        else:
            # dark_cyber (default)
            return {
                "html_class": "dark",
                "body_bg": "bg-[#050811]",
                "card_bg": "bg-[#0b1120]/90",
                "text_main": "text-slate-100",
                "text_muted": "text-slate-400",
                "text_muted_hex": "#94a3b8",
                "border": "border-[#1e293b]",
                "accent_badge": "bg-[#00f0ff]/10 text-[#00f0ff] border-[#00f0ff]/30",
                "btn_primary": "bg-[#00f0ff] hover:bg-[#38bdf8] text-black font-bold tracking-wide",
                "chart_accent": "#00f0ff",
                "chart_fill": "rgba(0, 240, 255, 0.15)",
                "grid_line_hex": "rgba(30, 41, 59, 0.7)"
            }

    def _generate_navbar(self, title: str, th: Dict[str, str]) -> str:
        return f"""
        <header class="w-full border-b {th['border']} {th['card_bg']} backdrop-blur sticky top-0 z-50">
            <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
                <div class="flex items-center space-x-3">
                    <div class="w-3 h-3 rounded-full bg-emerald-400 shadow-[0_0_8px_#34d399]"></div>
                    <span class="font-extrabold tracking-wider text-base font-mono">{title}</span>
                    <span class="text-xs px-2.5 py-0.5 rounded-full border {th['accent_badge']}">JEV Artifact</span>
                </div>
                <div class="flex items-center space-x-4">
                    <span class="text-xs {th['text_muted']} font-mono">SANDBOX ACTIVE</span>
                    <button class="px-4 py-2 text-xs rounded-lg {th['btn_primary']} transition-all">
                        Explorar
                    </button>
                </div>
            </div>
        </header>
        """

    def _generate_stat_cards(self, th: Dict[str, str]) -> str:
        return f"""
        <div class="grid grid-cols-1 md:grid-cols-3 gap-6">
            <div class="p-6 rounded-2xl border {th['border']} {th['card_bg']} shadow-lg">
                <div class="text-xs font-semibold tracking-wider uppercase {th['text_muted']}">Tasa de Inferencia</div>
                <div class="mt-2 text-3xl font-extrabold tracking-tight">1,840 <span class="text-sm font-normal text-emerald-400">+14%</span></div>
                <div class="mt-2 text-xs {th['text_muted']}">Tokens por segundo en ejecución paralela</div>
            </div>
            <div class="p-6 rounded-2xl border {th['border']} {th['card_bg']} shadow-lg">
                <div class="text-xs font-semibold tracking-wider uppercase {th['text_muted']}">Latencia Media</div>
                <div class="mt-2 text-3xl font-extrabold tracking-tight">18.4 <span class="text-xs font-normal">ms</span></div>
                <div class="mt-2 text-xs text-emerald-400">99.8% dentro del SLA</div>
            </div>
            <div class="p-6 rounded-2xl border {th['border']} {th['card_bg']} shadow-lg">
                <div class="text-xs font-semibold tracking-wider uppercase {th['text_muted']}">Eficiencia Energética</div>
                <div class="mt-2 text-3xl font-extrabold tracking-tight">98.2 <span class="text-xs font-normal">%</span></div>
                <div class="mt-2 text-xs {th['text_muted']}">Asignación dinámica de VRAM</div>
            </div>
        </div>
        """

    def _generate_chart_card(self, th: Dict[str, str]) -> str:
        return f"""
        <div class="p-6 rounded-2xl border {th['border']} {th['card_bg']} shadow-lg">
            <div class="flex items-center justify-between mb-4">
                <h3 class="text-sm font-bold tracking-wide uppercase">Monitoreo de Telemetría en Vivo</h3>
                <span class="text-xs font-mono {th['text_muted']}">FRECUENCIA: 100 Hz</span>
            </div>
            <div class="h-72 w-full">
                <canvas id="analyticsChart"></canvas>
            </div>
        </div>
        """

    def _generate_data_table(self, th: Dict[str, str]) -> str:
        return f"""
        <div class="rounded-2xl border {th['border']} {th['card_bg']} overflow-hidden shadow-lg">
            <div class="px-6 py-4 border-b {th['border']} flex items-center justify-between">
                <h3 class="text-sm font-bold tracking-wide uppercase">Nodos de Cómputo Distribuidos</h3>
                <span class="text-xs px-2 py-0.5 rounded border {th['accent_badge']}">5 Activos</span>
            </div>
            <div class="overflow-x-auto">
                <table class="w-full text-left text-xs">
                    <thead class="uppercase bg-slate-950/40 text-slate-400">
                        <tr>
                            <th class="px-6 py-3">Identificador</th>
                            <th class="px-6 py-3">Subred</th>
                            <th class="px-6 py-3">Rol</th>
                            <th class="px-6 py-3">Rendimiento</th>
                            <th class="px-6 py-3">Estado</th>
                        </tr>
                    </thead>
                    <tbody class="divide-y {th['border']}">
                        <tr>
                            <td class="px-6 py-4 font-mono text-cyan-400">NODE-QWEN-01</td>
                            <td class="px-6 py-4 font-mono">192.168.1.120</td>
                            <td class="px-6 py-4">Inferencia Local</td>
                            <td class="px-6 py-4">98.4%</td>
                            <td class="px-6 py-4"><span class="px-2 py-0.5 text-[10px] rounded bg-emerald-950 text-emerald-400 border border-emerald-800">ONLINE</span></td>
                        </tr>
                        <tr>
                            <td class="px-6 py-4 font-mono text-cyan-400">NODE-CFD-02</td>
                            <td class="px-6 py-4 font-mono">192.168.1.121</td>
                            <td class="px-6 py-4">Navier-Stokes Engine</td>
                            <td class="px-6 py-4">99.1%</td>
                            <td class="px-6 py-4"><span class="px-2 py-0.5 text-[10px] rounded bg-emerald-950 text-emerald-400 border border-emerald-800">ONLINE</span></td>
                        </tr>
                    </tbody>
                </table>
            </div>
        </div>
        """

    def _generate_hero_section(self, title: str, th: Dict[str, str]) -> str:
        return f"""
        <div class="text-center py-12 px-4 rounded-3xl border {th['border']} {th['card_bg']}">
            <h1 class="text-4xl sm:text-5xl font-black tracking-tight mb-4">{title}</h1>
            <p class="max-w-2xl mx-auto text-sm sm:text-base {th['text_muted']} mb-8">
                Infraestructura autónoma de alto rendimiento con renderizado dual, modelado CAD paramétrico y analítica estocástica.
            </p>
            <div class="flex justify-center gap-4">
                <button class="px-6 py-3 rounded-xl {th['btn_primary']}">Comenzar</button>
            </div>
        </div>
        """

    def _generate_calculator_ui(self, th: Dict[str, str]) -> str:
        return f"""
        <div class="max-w-md mx-auto p-6 rounded-2xl border {th['border']} {th['card_bg']} shadow-xl">
            <h2 class="text-base font-bold mb-4 font-mono text-center">Calculadora Interactiva Reactiva</h2>
            <div class="space-y-4">
                <div>
                    <label class="block text-xs uppercase {th['text_muted']} mb-1">Entrada A</label>
                    <input type="number" id="calcA" value="100" class="w-full px-3 py-2 rounded-lg bg-black/50 border {th['border']} text-white text-sm" oninput="runCompute()">
                </div>
                <div>
                    <label class="block text-xs uppercase {th['text_muted']} mb-1">Entrada B</label>
                    <input type="number" id="calcB" value="25" class="w-full px-3 py-2 rounded-lg bg-black/50 border {th['border']} text-white text-sm" oninput="runCompute()">
                </div>
                <div class="p-4 rounded-lg bg-black/60 border {th['border']} text-center">
                    <span class="text-xs uppercase {th['text_muted']}">Resultado Computado</span>
                    <div id="calcResult" class="text-2xl font-bold font-mono text-cyan-400 mt-1">125.0</div>
                </div>
            </div>
            <script>
                function runCompute() {{
                    const a = parseFloat(document.getElementById('calcA').value) || 0;
                    const b = parseFloat(document.getElementById('calcB').value) || 0;
                    document.getElementById('calcResult').innerText = (a + b).toFixed(2);
                }}
            </script>
        </div>
        """

    def _generate_footer(self, title: str, th: Dict[str, str]) -> str:
        return f"""
        <footer class="w-full border-t {th['border']} py-6 mt-auto">
            <div class="max-w-7xl mx-auto px-4 text-center text-xs {th['text_muted']}">
                <span>Generado dinámicamente por JEV Agent // {title}</span>
            </div>
        </footer>
        """
