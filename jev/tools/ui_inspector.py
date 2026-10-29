"""
Herramienta de Inspección de Interfaz de Usuario mediante Windows UI Automation (UIInspectorTool).

Extrae la jerarquía de controles visibles, textos, botones y campos de entrada en tiempo real
con sus coordenadas exactas de pantalla (center_x, center_y) mediante accesibilidad nativa de Windows,
sin necesidad de tomar capturas de pantalla ni ejecutar OCR.
"""
from typing import Dict, Any, List, Optional
import json

from jev.tools.base import BaseTool, ToolResult


class UIInspectorTool(BaseTool):
    """
    Inspecciona la pantalla o ventana activa mediante la API de accesibilidad de Windows (UI Automation).
    Devuelve las coordenadas exactas de clic y textos de botones, campos y menús en milisegundos.
    """
    name = "inspect_screen_ui"
    description = (
        "Inspecciona la pantalla o ventana activa mediante accesibilidad nativa de Windows (UI Automation). "
        "Devuelve una lista estructurada con todos los textos, botones, campos y sus coordenadas exactas (x, y) "
        "para interactuar directamente sin tomar fotos ni usar OCR."
    )
    parameters = {
        "type": "object",
        "properties": {
            "max_elements": {
                "type": "integer",
                "description": "Límite máximo de elementos a listar (por defecto 30).",
                "default": 30
            },
            "only_focused_window": {
                "type": "boolean",
                "description": "Si es True, solo inspecciona la ventana activa; si es False, inspecciona toda la pantalla.",
                "default": True
            },
            "search_text": {
                "type": "string",
                "description": "Texto o etiqueta opcional a buscar directamente (ej: 'Guardar', 'Aceptar', 'Cerrar', 'Enviar')."
            },
            "clickable_only": {
                "type": "boolean",
                "description": "Si es True, sólo lista controles interactivos (botones, cuadros de texto, opciones, menús).",
                "default": False
            }
        },
        "required": []
    }

    def execute(
        self,
        max_elements: int = 30,
        only_focused_window: bool = True,
        search_text: Optional[str] = None,
        clickable_only: bool = False,
        **kwargs
    ) -> ToolResult:
        try:
            try:
                import uiautomation as auto
            except ImportError:
                return ToolResult(
                    success=False,
                    output="",
                    error="La librería 'uiautomation' no está instalada. Ejecuta: pip install uiautomation"
                )

            # Evitar bloqueos largos en búsquedas
            auto.SetGlobalSearchTimeout(1.0)

            # Obtener control raíz según el modo
            if only_focused_window:
                root = auto.GetForegroundControl() or auto.GetFocusedControl() or auto.GetRootControl()
            else:
                root = auto.GetRootControl()

            if not root:
                return ToolResult(success=False, output="", error="No se pudo obtener el control de la ventana en Windows.")

            elements_found: List[Dict[str, Any]] = []
            visited_handles = set()

            actionable_types = {
                "ButtonControl", "EditControl", "MenuItemControl", "CheckBoxControl",
                "RadioButtonControl", "ComboBoxControl", "HyperlinkControl", "TabItemControl",
                "ListItemControl", "TreeItemControl", "CustomControl"
            }

            clean_query = search_text.lower().strip() if search_text else None

            # Recorrido recursivo con poda de profundidad para alta velocidad
            def walk(control, depth=0):
                if len(elements_found) >= max_elements or depth > 5:
                    return

                try:
                    handle = control.NativeWindowHandle
                    if handle and handle in visited_handles and depth > 1:
                        return
                    if handle:
                        visited_handles.add(handle)
                except Exception:
                    pass

                # Filtrar elementos con dimensiones válidas en pantalla
                try:
                    rect = control.BoundingRectangle
                    if rect and (rect.width() > 0 and rect.height() > 0):
                        name = (control.Name or "").strip()
                        ctrl_type = control.ControlTypeName or "Control"
                        is_actionable = ctrl_type in actionable_types

                        # Si se solicitó clickable_only, descartar contenedores o texto estático sin acción
                        include = True
                        if clickable_only and not is_actionable:
                            include = False

                        # Si hay búsqueda por texto, verificar coincidencia
                        if clean_query and clean_query not in name.lower() and clean_query not in ctrl_type.lower():
                            include = False

                        if include and (name or is_actionable):
                            elements_found.append({
                                "type": ctrl_type,
                                "text": name,
                                "center_x": rect.xcenter(),
                                "center_y": rect.ycenter(),
                                "rect": [rect.left, rect.top, rect.right, rect.bottom],
                                "is_actionable": is_actionable
                            })
                except Exception:
                    pass

                # Iterar hijos
                try:
                    for child in control.GetChildren():
                        walk(child, depth + 1)
                        if len(elements_found) >= max_elements:
                            break
                except Exception:
                    pass

            walk(root)

            # Generar resumen estructurado
            window_name = getattr(root, "Name", "") or "Ventana Activa"
            lines = [
                f"🖥️ [WINDOWS UI INSPECTION: '{window_name}']",
                f"• Elementos detectados: {len(elements_found)} (Límite: {max_elements})",
                f"• Filtro búsqueda: '{search_text}'" if search_text else "• Modo: Escaneo general",
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            ]

            if elements_found:
                for idx, el in enumerate(elements_found, 1):
                    act_tag = " [Clickeable]" if el["is_actionable"] else ""
                    lines.append(
                        f"[{idx:02d}] {el['type']}{act_tag}: \"{el['text']}\" -> Coordenadas: ({el['center_x']}, {el['center_y']})"
                    )
            else:
                lines.append("(No se detectaron controles coincidentes en el nivel inspeccionado)")

            output_summary = {
                "window_title": window_name,
                "total_elements": len(elements_found),
                "elements": elements_found
            }

            return ToolResult(
                success=True,
                output="\n".join(lines),
                data=output_summary
            )

        except Exception as e:
            return ToolResult(success=False, output="", error=f"Error inspeccionando UI de Windows: {e}")
