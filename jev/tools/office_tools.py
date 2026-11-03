"""
Herramientas nativas de Microsoft Office (Excel y PowerPoint) para Bable 2.0.
Permite crear hojas de cálculo .xlsx con fórmulas y estilos, y presentaciones .pptx con diapositivas estructuradas.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional
from jev.tools.base import BaseTool, ToolResult


class ExcelTool(BaseTool):
    """Herramienta para crear y manipular hojas de cálculo de Microsoft Excel (.xlsx)."""

    @property
    def name(self) -> str:
        return "excel_tool"

    @property
    def description(self) -> str:
        return (
            "Crea o lee archivos de Microsoft Excel (.xlsx). "
            "Permite definir hojas, filas con datos, encabezados con formato y fórmulas matemáticas."
        )

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["create", "read"],
                    "description": "Acción a realizar: 'create' para generar nuevo libro o 'read' para leer datos"
                },
                "filename": {
                    "type": "string",
                    "description": "Nombre o ruta del archivo .xlsx (ej: 'workspace/informe_ventas.xlsx')"
                },
                "sheet_title": {
                    "type": "string",
                    "description": "Título de la hoja activa",
                    "default": "Hoja 1"
                },
                "headers": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Lista de títulos de columna para el encabezado"
                },
                "rows": {
                    "type": "array",
                    "items": {
                        "type": "array",
                        "items": {"type": "string"}
                    },
                    "description": "Lista de filas (cada fila es una lista de valores)"
                }
            },
            "required": ["action", "filename"]
        }

    def execute(self, **kwargs) -> ToolResult:
        action = kwargs.get("action", "create").lower().strip()
        filename = kwargs.get("filename", "workspace/documento.xlsx")
        sheet_title = kwargs.get("sheet_title", "Datos")
        headers = kwargs.get("headers", [])
        rows = kwargs.get("rows", [])

        if not filename.endswith(".xlsx"):
            filename += ".xlsx"

        file_path = Path(filename)
        file_path.parent.mkdir(parents=True, exist_ok=True)

        if action == "create":
            try:
                import openpyxl
                from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
                from openpyxl.utils import get_column_letter

                wb = openpyxl.Workbook()
                ws = wb.active
                ws.title = sheet_title

                # Estilos profesionales
                header_fill = PatternFill(start_color="1F4E79", end_color="1F4E79", fill_type="solid")
                header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
                align_center = Alignment(horizontal="center", vertical="center")
                thin_border = Border(
                    left=Side(style="thin", color="D9D9D9"),
                    right=Side(style="thin", color="D9D9D9"),
                    top=Side(style="thin", color="D9D9D9"),
                    bottom=Side(style="thin", color="D9D9D9")
                )

                cur_row = 1
                if headers:
                    for col_idx, h in enumerate(headers, 1):
                        cell = ws.cell(row=cur_row, column=col_idx, value=str(h))
                        cell.fill = header_fill
                        cell.font = header_font
                        cell.alignment = align_center
                        cell.border = thin_border
                    cur_row += 1

                for row_data in rows:
                    for col_idx, val in enumerate(row_data, 1):
                        # Intentar convertir numéricos
                        clean_val = val
                        try:
                            if isinstance(val, str) and val.replace(".", "", 1).replace("-", "", 1).isdigit():
                                clean_val = float(val) if "." in val else int(val)
                        except Exception:
                            pass
                        cell = ws.cell(row=cur_row, column=col_idx, value=clean_val)
                        cell.border = thin_border
                    cur_row += 1

                # Auto-ajuste de ancho de columnas
                for col in ws.columns:
                    max_len = max(len(str(cell.value or "")) for cell in col)
                    col_letter = get_column_letter(col[0].column)
                    ws.column_dimensions[col_letter].width = max(max_len + 4, 12)

                wb.save(str(file_path))
                return ToolResult(
                    success=True,
                    output=f"✓ Archivo Excel generado exitosamente: '{file_path.resolve()}' con {len(rows)} filas.",
                    data={"path": str(file_path.resolve()), "rows_count": len(rows)}
                )
            except Exception as e:
                return ToolResult(success=False, output="", error=f"Error al generar archivo Excel: {e}")

        elif action == "read":
            try:
                import openpyxl
                if not file_path.exists():
                    return ToolResult(success=False, output="", error=f"El archivo no existe: '{filename}'")

                wb = openpyxl.load_workbook(str(file_path), data_only=True)
                sheet = wb.active
                extracted = []
                for row in sheet.iter_rows(values_only=True):
                    if any(c is not None for c in row):
                        extracted.append([str(c) if c is not None else "" for c in row])

                return ToolResult(
                    success=True,
                    output=f"Leídas {len(extracted)} filas de '{filename}'.\n" + "\n".join(["\t".join(r[:8]) for r in extracted[:15]]),
                    data={"rows": extracted}
                )
            except Exception as e:
                return ToolResult(success=False, output="", error=f"Error al leer archivo Excel: {e}")

        return ToolResult(success=False, output="", error=f"Acción '{action}' no soportada. Use 'create' o 'read'.")


class PowerPointTool(BaseTool):
    """Herramienta para crear presentaciones de Microsoft PowerPoint (.pptx)."""

    @property
    def name(self) -> str:
        return "powerpoint_tool"

    @property
    def description(self) -> str:
        return (
            "Crea archivos de Microsoft PowerPoint (.pptx) profesionales. "
            "Permite generar diapositivas de portada, diapositivas con viñetas, secciones y temas de color."
        )

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "filename": {
                    "type": "string",
                    "description": "Nombre o ruta del archivo .pptx (ej: 'workspace/presentacion_ia.pptx')"
                },
                "title": {
                    "type": "string",
                    "description": "Título principal de la presentación"
                },
                "subtitle": {
                    "type": "string",
                    "description": "Subtítulo o autor",
                    "default": "Generado con Bable 2.0"
                },
                "slides": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string"},
                            "bullets": {
                                "type": "array",
                                "items": {"type": "string"}
                            }
                        },
                        "required": ["title"]
                    },
                    "description": "Lista de diapositivas con título y lista de viñetas"
                }
            },
            "required": ["filename", "title"]
        }

    def execute(self, **kwargs) -> ToolResult:
        filename = kwargs.get("filename", "workspace/presentacion.pptx")
        title = kwargs.get("title", "Presentación Ejecutiva")
        subtitle = kwargs.get("subtitle", "Bable 2.0 Multi-Model Engine")
        slides = kwargs.get("slides", [])

        if not filename.endswith(".pptx"):
            filename += ".pptx"

        file_path = Path(filename)
        file_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            from pptx import Presentation
            from pptx.util import Inches, Pt
            from pptx.dml.color import RGBColor

            prs = Presentation()

            # Diapositiva 1: Portada
            title_layout = prs.slide_layouts[0]
            slide_1 = prs.slides.add_slide(title_layout)
            slide_1.shapes.title.text = title
            if len(slide_1.shapes.placeholders) > 1:
                slide_1.shapes.placeholders[1].text = subtitle

            # Diapositivas de contenido
            bullet_layout = prs.slide_layouts[1]
            for s_data in slides:
                s_title = s_data.get("title", "Diapositiva")
                bullets = s_data.get("bullets", [])

                slide = prs.slides.add_slide(bullet_layout)
                slide.shapes.title.text = s_title
                tf = slide.shapes.placeholders[1].text_frame

                if bullets:
                    tf.text = bullets[0]
                    for b in bullets[1:]:
                        p = tf.add_paragraph()
                        p.text = b
                        p.level = 0

            prs.save(str(file_path))
            return ToolResult(
                success=True,
                output=f"✓ Presentación PowerPoint generada exitosamente: '{file_path.resolve()}' con {len(slides) + 1} diapositivas.",
                data={"path": str(file_path.resolve()), "slides_count": len(slides) + 1}
            )
        except Exception as e:
            return ToolResult(success=False, output="", error=f"Error al generar PowerPoint: {e}")
