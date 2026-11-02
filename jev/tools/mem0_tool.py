"""
Herramienta de Agente para Gestión de Memoria a Largo Plazo (Mem0 Layer).
Permite al agente almacenar y recuperar proactivamente preferencias del usuario,
rutas de archivos y resoluciones de errores pasados entre sesiones.
"""
from typing import Dict, Any, Optional
import json

from jev.tools.base import BaseTool, ToolResult
from core.memory.mem0_bridge import Mem0Bridge
from core.memory.user_memory import UserMemoryCategory


class Mem0MemoryTool(BaseTool):
    """Herramienta para gestionar la memoria persistente a largo plazo Mem0."""
    name = "manage_user_memory"
    description = (
        "Gestiona la memoria persistente a largo plazo (Mem0). Permite almacenar y recuperar "
        "preferencias del usuario, rutas de archivos habituales, y soluciones a errores pasados para "
        "reutilizarlas entre sesiones de trabajo. Acciones: 'remember', 'recall', 'remember_path', "
        "'remember_error', 'list', 'delete'."
    )
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["remember", "recall", "remember_path", "remember_error", "list", "delete"],
                "description": "Acción a realizar en la memoria persistente."
            },
            "key": {
                "type": "string",
                "description": "Identificador o clave mnemotécnica (ej: 'idioma_favorito', 'path_workspace', 'err_404_gemini')."
            },
            "value": {
                "type": "string",
                "description": "Contenido o hecho a almacenar (requerido para 'remember', 'remember_path', 'remember_error')."
            },
            "category": {
                "type": "string",
                "enum": ["preference", "personal_fact", "system_directive", "project_context", "workflow_rule", "habitual_path", "error_resolution"],
                "description": "Categoría de la memoria."
            },
            "query": {
                "type": "string",
                "description": "Texto o términos de búsqueda para 'recall'."
            },
            "resolution": {
                "type": "string",
                "description": "Solución técnica aplicada al error (requerido para 'remember_error')."
            },
            "memory_id": {
                "type": "string",
                "description": "ID de memoria a eliminar (para 'delete')."
            }
        },
        "required": ["action"]
    }

    def __init__(self, mem0_bridge: Optional[Mem0Bridge] = None):
        self.bridge = mem0_bridge or Mem0Bridge()

    def execute(
        self,
        action: str,
        key: Optional[str] = None,
        value: Optional[str] = None,
        category: Optional[str] = None,
        query: Optional[str] = None,
        resolution: Optional[str] = None,
        memory_id: Optional[str] = None,
        **kwargs
    ) -> ToolResult:
        try:
            cat = category or UserMemoryCategory.PREFERENCE.value

            if action == "remember":
                if not value:
                    return ToolResult(success=False, output="", error="El parámetro 'value' es obligatorio para 'remember'.")
                res = self.bridge.add(text=value, category=cat, key=key)
                return ToolResult(
                    success=True,
                    output=f"✓ Memoria persistente registrada con éxito [{res.get('action', 'guardado')}]: ID={res.get('memory_id')} (clave='{res.get('key')}').",
                    data=res
                )

            elif action == "remember_path":
                if not value:
                    return ToolResult(success=False, output="", error="El parámetro 'value' (ruta del archivo/carpeta) es obligatorio.")
                res = self.bridge.remember_path(path=value, description=key or "")
                return ToolResult(
                    success=True,
                    output=f"✓ Ruta habitual registrada en Mem0: '{value}'.",
                    data=res
                )

            elif action == "remember_error":
                if not value or not resolution:
                    return ToolResult(success=False, output="", error="Los parámetros 'value' (descripción del error) y 'resolution' (solución) son requeridos.")
                res = self.bridge.remember_error_resolution(error=value, resolution=resolution)
                return ToolResult(
                    success=True,
                    output=f"✓ Resolución de error persistida en Mem0: {res.get('memory_id')}.",
                    data=res
                )

            elif action == "recall":
                search_q = query or value or key or ""
                results = self.bridge.search(query=search_q, category=category, limit=6)
                if not results:
                    return ToolResult(
                        success=True,
                        output=f"No se encontraron memorias para la consulta '{search_q}'.",
                        data={"count": 0, "results": []}
                    )
                out_lines = [f"Resultados encontrados ({len(results)} memorias):"]
                for r in results:
                    out_lines.append(f"- [{r.get('category')}] {r.get('key')}: {r.get('value')} (ID: {r.get('memory_id')})")
                return ToolResult(
                    success=True,
                    output="\n".join(out_lines),
                    data={"count": len(results), "results": results}
                )

            elif action == "list":
                all_mem = self.bridge.get_all(category=category)
                out_lines = [f"Total memorias activas ({len(all_mem)}):"]
                for r in all_mem:
                    out_lines.append(f"- [{r.get('category')}] {r.get('key')}: {r.get('value')} (ID: {r.get('memory_id')})")
                return ToolResult(
                    success=True,
                    output="\n".join(out_lines),
                    data={"count": len(all_mem), "results": all_mem}
                )

            elif action == "delete":
                if not memory_id:
                    return ToolResult(success=False, output="", error="El parámetro 'memory_id' es requerido para 'delete'.")
                ok = self.bridge.delete(memory_id=memory_id)
                if ok:
                    return ToolResult(success=True, output=f"✓ Memoria '{memory_id}' desactivada con éxito.")
                return ToolResult(success=False, output="", error=f"No se encontró memoria activa con ID '{memory_id}'.")

            else:
                return ToolResult(success=False, output="", error=f"Acción '{action}' no reconocida en Mem0MemoryTool.")

        except Exception as e:
            return ToolResult(success=False, output="", error=f"Error en Mem0MemoryTool: {str(e)}")
