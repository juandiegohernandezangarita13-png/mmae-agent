import os
from typing import Dict, Any

class SafeFileSystemSkill:
    """
    Herramienta segura de lectura y escritura de archivos en disco.
    Permite manipular código y archivos de configuración sin salir de la raíz del proyecto.
    """
    def __init__(self, base_directory: str = "."):
        self.base_directory = os.path.abspath(base_directory)

    def _resolve_safe_path(self, relative_path: str) -> str:
        target_path = os.path.abspath(os.path.join(self.base_directory, relative_path))
        if not target_path.startswith(self.base_directory):
            raise PermissionError("Acceso fuera del directorio base no permitido por seguridad.")
        return target_path

    def read_file(self, file_path: str) -> Dict[str, Any]:
        try:
            full_path = self._resolve_safe_path(file_path)
            if not os.path.exists(full_path):
                return {"success": False, "error": f"Archivo '{file_path}' no encontrado."}
            
            with open(full_path, "r", encoding="utf-8") as f:
                content = f.read()
            return {"success": True, "content": content}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def write_file(self, file_path: str, content: str) -> Dict[str, Any]:
        try:
            full_path = self._resolve_safe_path(file_path)
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            
            with open(full_path, "w", encoding="utf-8") as f:
                f.write(content)
            return {"success": True, "message": f"Archivo '{file_path}' escrito correctamente."}
        except Exception as e:
            return {"success": False, "error": str(e)}
