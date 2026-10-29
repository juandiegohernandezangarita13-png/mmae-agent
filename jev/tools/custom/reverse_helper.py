"""
Herramienta de Análisis Estático y Triaje Inverso (ReverseHelperTool).

Extrae de forma estática y ultrarrápida metadatos, firmas de encabezado (Magic Bytes)
y cadenas de texto imprimibles de binarios o scripts ubicados dentro de 'workspace/',
con verificación estricta de rutas (Path Traversal Guard).
"""
from typing import Dict, Any, Optional, List, Set
from pathlib import Path
import hashlib
import time
import re
from pydantic import BaseModel, Field, ValidationError

from jev.tools.base import BaseTool, ToolResult
from jev.config import default_config


class ReverseHelperInput(BaseModel):
    """Esquema de parámetros validados con Pydantic para ReverseHelperTool."""
    target_file: str = Field(
        description="Ruta relativa del binario, ejecutable o script dentro del directorio workspace/."
    )
    min_string_len: int = Field(
        default=4,
        ge=3,
        le=50,
        description="Longitud mínima para extraer cadenas de texto imprimibles (por defecto 4)."
    )
    max_strings: int = Field(
        default=50,
        ge=5,
        le=500,
        description="Límite máximo de cadenas a listar para mantener el contexto ligero."
    )
    include_hashes: bool = Field(
        default=True,
        description="Calcular hashes criptográficos SHA256 y MD5 del archivo."
    )
    pattern_filter: Optional[str] = Field(
        default=None,
        description="Expresión regular opcional para filtrar cadenas (ej: 'url' para URLs, 'ip' para IPs, o un regex personalizado)."
    )


class ReverseHelperTool(BaseTool):
    """
    Herramienta de inspección estática que analiza encabezados binarios, hashes
    y strings imprimibles de archivos confinados en workspace/.
    """
    name = "reverse_engineering_helper"
    description = (
        "Analizador estático de binarios y scripts en workspace/. Detecta tipo de formato (PE, ELF, Mach-O, ZIP, etc.), "
        "calcula hashes SHA256/MD5 y extrae cadenas imprimibles con filtrado inteligente (URLs, IPs, funciones)."
    )
    parameters = ReverseHelperInput.model_json_schema()

    def __init__(self, workspace_dir: Optional[Path] = None):
        super().__init__()
        self.workspace_dir = (workspace_dir or default_config.workspace_dir).resolve()
        self.workspace_dir.mkdir(parents=True, exist_ok=True)

    def _validate_path_safety(self, file_path_str: str) -> Path:
        """Asegura que el archivo inspeccionado no escape de workspace/."""
        clean = file_path_str.strip().strip("'\"")
        if not clean:
            raise ValueError("Ruta de archivo no especificada.")

        target = (self.workspace_dir / clean).resolve()
        try:
            target.relative_to(self.workspace_dir)
        except ValueError:
            raise PermissionError(
                f"ACCESO DENEGADO: El archivo '{file_path_str}' intenta escapar de '{self.workspace_dir}'."
            )

        if not target.exists():
            raise FileNotFoundError(f"El archivo objetivo '{clean}' no existe en {self.workspace_dir}.")

        if not target.is_file():
            raise IsADirectoryError(f"'{clean}' es un directorio, no un archivo.")

        return target

    def execute(
        self,
        target_file: str,
        min_string_len: int = 4,
        max_strings: int = 50,
        include_hashes: bool = True,
        pattern_filter: Optional[str] = None,
        **kwargs
    ) -> ToolResult:
        try:
            params = ReverseHelperInput(
                target_file=target_file,
                min_string_len=min_string_len,
                max_strings=max_strings,
                include_hashes=include_hashes,
                pattern_filter=pattern_filter
            )
        except ValidationError as ve:
            return ToolResult(
                success=False,
                output="",
                error=f"Error de validación de parámetros en ReverseHelperTool: {ve}"
            )

        try:
            file_path = self._validate_path_safety(params.target_file)
        except (PermissionError, FileNotFoundError, IsADirectoryError, ValueError) as err:
            return ToolResult(success=False, output="", error=str(err))

        try:
            # 1. Metadatos básicos
            file_stat = file_path.stat()
            file_size = file_stat.st_size

            # 2. Análisis de encabezados y Magic Bytes
            format_info = self._detect_format(file_path)

            # 3. Hashes criptográficos (streaming por chunks para velocidad y baja memoria)
            hashes = {}
            if params.include_hashes:
                hashes = self._compute_hashes(file_path)

            # 4. Extracción de cadenas imprimibles
            strings_found = self._extract_printable_strings(
                file_path,
                min_len=params.min_string_len,
                max_count=params.max_strings,
                pattern=params.pattern_filter
            )

            # Formatear reporte de salida
            lines = [
                f"🔬 [REVERSE ENGINEERING STATIC ANALYSIS: {file_path.name}]",
                f"• Formato identificado: {format_info['format']} ({format_info['description']})",
                f"• Tamaño: {file_size:,} bytes ({file_size / 1024:.2f} KB)",
                f"• Modificado: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(file_stat.st_mtime))}"
            ]

            if hashes:
                lines.append(f"• SHA-256: {hashes.get('sha256')}")
                lines.append(f"• MD5:     {hashes.get('md5')}")

            lines.append(f"\n📝 [STRINGS IMPRIMIBLES EXTRAÍDAS] (Mostrando {len(strings_found)} de máx {params.max_strings}):")
            if strings_found:
                for idx, s in enumerate(strings_found, 1):
                    lines.append(f"  [{idx:02d}] {s}")
            else:
                lines.append("  (No se encontraron cadenas imprimibles que coincidan con los criterios)")

            return ToolResult(
                success=True,
                output="\n".join(lines),
                data={
                    "file_name": file_path.name,
                    "file_size": file_size,
                    "format": format_info["format"],
                    "hashes": hashes,
                    "strings_count": len(strings_found),
                    "strings": strings_found
                }
            )

        except Exception as exc:
            return ToolResult(
                success=False,
                output="",
                error=f"Error durante el análisis estático de '{params.target_file}': {exc}"
            )

    def _detect_format(self, path: Path) -> Dict[str, str]:
        """Inspecciona los primeros bytes del encabezado (Magic Numbers)."""
        with open(path, "rb") as f:
            header = f.read(256)

        if not header:
            return {"format": "EMPTY_FILE", "description": "Archivo vacío (0 bytes)"}

        if header.startswith(b"MZ"):
            is_pe = b"PE\x00\x00" in header
            return {
                "format": "PE_BINARY",
                "description": "Ejecutable/DLL nativo de Windows (Portable Executable - PE32/PE32+)" if is_pe else "Binario DOS/Windows MZ"
            }
        elif header.startswith(b"\x7fELF"):
            bitness = "64-bit" if len(header) > 4 and header[4] == 2 else "32-bit"
            return {"format": "ELF_BINARY", "description": f"Binario ejecutable o biblioteca compartida de Linux ({bitness})"}
        elif header.startswith((b"\xfe\xed\xfa\xce", b"\xfe\xed\xfa\xcf", b"\xcf\xfa\xed\xfe", b"\xce\xfa\xed\xfe")):
            return {"format": "MACHO_BINARY", "description": "Binario ejecutable de Apple macOS/iOS (Mach-O)"}
        elif header.startswith(b"PK\x03\x04"):
            return {"format": "ZIP_ARCHIVE", "description": "Archivo comprimido ZIP o contenedor empaquetado (JAR/APK/DOCX)"}
        elif header.startswith(b"%PDF"):
            return {"format": "PDF_DOCUMENT", "description": "Documento en formato Adobe PDF"}
        elif header.startswith(b"\x1f\x8b"):
            return {"format": "GZIP_ARCHIVE", "description": "Archivo comprimido GZIP"}
        elif header.startswith(b"#!"):
            shebang = header.split(b"\n")[0].decode("latin-1", errors="replace")
            return {"format": "SCRIPT_SHEBANG", "description": f"Script ejecutable interpretado: {shebang}"}
        elif path.suffix in [".py", ".pyw"]:
            return {"format": "PYTHON_SCRIPT", "description": "Código fuente en lenguaje Python"}
        elif path.suffix in [".ps1", ".psm1"]:
            return {"format": "POWERSHELL_SCRIPT", "description": "Script de automatización de Windows PowerShell"}
        elif path.suffix in [".bat", ".cmd"]:
            return {"format": "BATCH_SCRIPT", "description": "Script de comandos de Windows Batch"}

        # Intento de detección de texto plano
        try:
            header.decode("utf-8")
            return {"format": "TEXT_PLAIN", "description": "Archivo de texto plano o configuración"}
        except UnicodeDecodeError:
            return {"format": "GENERIC_BINARY", "description": "Archivo de datos binarios sin firma estándar"}

    def _compute_hashes(self, path: Path) -> Dict[str, str]:
        """Calcula SHA256 y MD5 por bloques de 64KB."""
        h_sha256 = hashlib.sha256()
        h_md5 = hashlib.md5()
        with open(path, "rb") as f:
            while chunk := f.read(65536):
                h_sha256.update(chunk)
                h_md5.update(chunk)
        return {
            "sha256": h_sha256.hexdigest(),
            "md5": h_md5.hexdigest()
        }

    def _extract_printable_strings(
        self,
        path: Path,
        min_len: int,
        max_count: int,
        pattern: Optional[str]
    ) -> List[str]:
        """Extrae cadenas imprimibles tanto en ASCII como en UTF-16LE."""
        results: Set[str] = set()
        max_bytes_to_scan = 10 * 1024 * 1024  # Escaneo máximo de 10 MB para no degradar memoria

        # Compilar filtro si fue provisto
        regex_filter = None
        if pattern:
            p_lower = pattern.lower().strip()
            if p_lower == "url":
                regex_filter = re.compile(r"https?://[^\s\"'<>]+", re.IGNORECASE)
            elif p_lower == "ip":
                regex_filter = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
            else:
                try:
                    regex_filter = re.compile(pattern, re.IGNORECASE)
                except re.error:
                    pass

        # Patrón de extracción de caracteres ASCII imprimibles
        ascii_regex = re.compile(rf"[A-Za-z0-9_./:\\-]{{{min_len},}}")

        with open(path, "rb") as f:
            data = f.read(max_bytes_to_scan)

        # 1. Búsqueda ASCII
        for match in ascii_regex.finditer(data.decode("latin-1", errors="replace")):
            s = match.group()
            if regex_filter:
                if regex_filter.search(s):
                    results.add(s)
            else:
                results.add(s)
            if len(results) >= max_count:
                break

        # 2. Búsqueda UTF-16LE si no se ha alcanzado el límite
        if len(results) < max_count:
            try:
                # Decodificar secuencias de 2 bytes
                decoded_utf16 = data.decode("utf-16le", errors="ignore")
                for match in ascii_regex.finditer(decoded_utf16):
                    s = match.group()
                    if regex_filter:
                        if regex_filter.search(s):
                            results.add(s)
                    else:
                        results.add(s)
                    if len(results) >= max_count:
                        break
            except Exception:
                pass

        # Ordenar por longitud o contenido
        sorted_strings = sorted(list(results), key=lambda x: (-len(x), x))
        return sorted_strings[:max_count]
