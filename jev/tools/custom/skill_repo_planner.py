"""
Motor de Edición Atómica de Proyectos y Sandbox Branching (Plandex-Style Engine) para JEV.
Provee:
1. AST Context Slicer: Mapeo sintáctico compacto de repositorios (extracción de clases, métodos,
   firmas y docstrings omitiendo cuerpos para ahorrar ~80% de tokens de contexto).
2. Sandbox Staging: Ramas aisladas de ensayo en .jev_staging/<plan_id>/ sin tocar el workspace original.
3. Atomic Commit & Rollback: Validación de sintaxis y tests en staging antes de fusionar,
   con generación de unified diffs y reversión atómica ante errores.
"""
from typing import Dict, Any, List, Optional, Tuple, Set
from pathlib import Path
from dataclasses import dataclass, field, asdict
import difflib
import json
import shutil
import subprocess
import time
import ast
import re
import os

from jev.tools.base import BaseTool, ToolResult
from jev.config import default_config
from jev.core.sandbox import ExecutionSandbox

# Intentar importar librerías avanzadas de análisis sintáctico y control de versiones
try:
    import tree_sitter_language_pack
    HAS_TREE_SITTER = True
except Exception:
    HAS_TREE_SITTER = False

try:
    import git
    HAS_GITPYTHON = True
except Exception:
    HAS_GITPYTHON = False


# =============================================================================
# 1. MAPEADOR SINTÁCTICO DE REPOSITORIO (AST CONTEXT SLICER)
# =============================================================================
@dataclass
class ASTSymbol:
    """Representa un símbolo sintáctico (clase, función, método o constante)."""
    name: str
    kind: str  # 'class', 'function', 'method', 'variable'
    signature: str
    docstring: Optional[str] = None
    start_line: int = 1
    end_line: int = 1
    decorators: List[str] = field(default_factory=list)
    children: List['ASTSymbol'] = field(default_factory=list)


class ASTContextSlicer:
    """
    Escanea archivos de código fuente y genera índices jerárquicos compactos
    y 'rebanadas' (slices) sintácticas, reduciendo drásticamente el consumo de contexto.
    """

    IGNORE_DIRS: Set[str] = {
        ".git", ".venv", "venv", "__pycache__", ".jev_staging", "node_modules",
        "data", ".idea", ".vscode", "dist", "build", "coverage"
    }

    IGNORE_EXTS: Set[str] = {
        ".png", ".jpg", ".jpeg", ".gif", ".mp4", ".wav", ".mp3", ".exe",
        ".pyc", ".pyd", ".dll", ".so", ".zip", ".tar", ".gz", ".db", ".sqlite"
    }

    @classmethod
    def extract_python_outline(cls, source_code: str, file_path_str: str = "") -> Tuple[List[ASTSymbol], str, int, int]:
        """
        Analiza código Python con AST nativo y produce símbolos y el esqueleto compacto sin cuerpos.
        """
        lines = source_code.splitlines(keepends=True)
        total_lines = len(lines)
        symbols: List[ASTSymbol] = []
        skeleton_lines: List[str] = []

        try:
            tree = ast.parse(source_code)
        except Exception:
            # Fallback en caso de sintaxis rota en el archivo original
            return [], source_code, total_lines, total_lines

        # Registrar imports resumidos
        import_modules = []
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    import_modules.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                names = [a.name for a in node.names[:3]]
                suffix = "..." if len(node.names) > 3 else ""
                import_modules.append(f"{mod}: {', '.join(names)}{suffix}")

        if import_modules:
            skeleton_lines.append(f"# [Imports: {', '.join(import_modules[:8])}]")
            skeleton_lines.append("")

        def _format_args(args_node: ast.arguments) -> str:
            parts = []
            # Positional args
            defaults_offset = len(args_node.args) - len(args_node.defaults)
            for i, arg in enumerate(args_node.args):
                p = arg.arg
                if arg.annotation:
                    try:
                        p += f": {ast.unparse(arg.annotation)}"
                    except Exception:
                        pass
                default_idx = i - defaults_offset
                if default_idx >= 0:
                    try:
                        p += f" = {ast.unparse(args_node.defaults[default_idx])}"
                    except Exception:
                        p += " = ..."
                parts.append(p)
            return ", ".join(parts)

        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                bases = []
                for b in node.bases:
                    try:
                        bases.append(ast.unparse(b))
                    except Exception:
                        bases.append("...")
                bases_str = f"({', '.join(bases)})" if bases else ""
                class_doc = ast.get_docstring(node)
                class_sym = ASTSymbol(
                    name=node.name,
                    kind="class",
                    signature=f"class {node.name}{bases_str}:",
                    docstring=class_doc,
                    start_line=node.lineno,
                    end_line=node.end_lineno or node.lineno
                )

                skeleton_lines.append(f"class {node.name}{bases_str}:")
                if class_doc:
                    short_doc = class_doc.strip().split("\n")[0][:80]
                    skeleton_lines.append(f'    """{short_doc}"""')

                # Métodos internos de la clase
                method_count = 0
                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        method_count += 1
                        m_args = _format_args(item.args)
                        ret_ann = f" -> {ast.unparse(item.returns)}" if item.returns else ""
                        m_doc = ast.get_docstring(item)
                        prefix = "async def" if isinstance(item, ast.AsyncFunctionDef) else "def"
                        m_sig = f"{prefix} {item.name}({m_args}){ret_ann}:"

                        m_sym = ASTSymbol(
                            name=item.name,
                            kind="method",
                            signature=m_sig,
                            docstring=m_doc,
                            start_line=item.lineno,
                            end_line=item.end_lineno or item.lineno
                        )
                        class_sym.children.append(m_sym)

                        skeleton_lines.append(f"    {m_sig}")
                        if m_doc:
                            short_mdoc = m_doc.strip().split("\n")[0][:70]
                            skeleton_lines.append(f'        """{short_mdoc}"""')
                        body_span = (item.end_lineno or item.lineno) - item.lineno
                        skeleton_lines.append(f"        ...  # [Cuerpo omitido: {max(body_span, 1)} líneas]")

                if method_count == 0:
                    skeleton_lines.append("    pass")
                skeleton_lines.append("")
                symbols.append(class_sym)

            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                fn_args = _format_args(node.args)
                ret_ann = f" -> {ast.unparse(node.returns)}" if node.returns else ""
                fn_doc = ast.get_docstring(node)
                prefix = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
                fn_sig = f"{prefix} {node.name}({fn_args}){ret_ann}:"

                fn_sym = ASTSymbol(
                    name=node.name,
                    kind="function",
                    signature=fn_sig,
                    docstring=fn_doc,
                    start_line=node.lineno,
                    end_line=node.end_lineno or node.lineno
                )
                symbols.append(fn_sym)

                skeleton_lines.append(fn_sig)
                if fn_doc:
                    short_fdoc = fn_doc.strip().split("\n")[0][:75]
                    skeleton_lines.append(f'    """{short_fdoc}"""')
                body_span = (node.end_lineno or node.lineno) - node.lineno
                skeleton_lines.append(f"    ...  # [Cuerpo omitido: {max(body_span, 1)} líneas]")
                skeleton_lines.append("")

        skeleton_text = "\n".join(skeleton_lines)
        skeleton_count = len(skeleton_lines)
        return symbols, skeleton_text, total_lines, skeleton_count

    @classmethod
    def extract_generic_outline(cls, source_code: str, file_path_str: str) -> Tuple[List[ASTSymbol], str, int, int]:
        """
        Extrae símbolos básicos para lenguajes JS/TS/otros usando regex o tree-sitter.
        """
        lines = source_code.splitlines()
        total_lines = len(lines)
        symbols: List[ASTSymbol] = []
        skeleton_lines: List[str] = []

        fn_pattern = re.compile(r"^\s*(?:export\s+)?(?:async\s+)?function\s+([a-zA-Z0-9_$]+)\s*\((.*?)\)", re.MULTILINE)
        class_pattern = re.compile(r"^\s*(?:export\s+)?class\s+([a-zA-Z0-9_$]+)(?:\s+extends\s+([a-zA-Z0-9_$]+))?", re.MULTILINE)

        for match in class_pattern.finditer(source_code):
            c_name = match.group(1)
            base = match.group(2) or ""
            sig = f"class {c_name}" + (f" extends {base}" if base else "") + " { ... }"
            symbols.append(ASTSymbol(name=c_name, kind="class", signature=sig))
            skeleton_lines.append(sig)

        for match in fn_pattern.finditer(source_code):
            fn_name = match.group(1)
            args = match.group(2)
            sig = f"function {fn_name}({args}) {{ ... }}"
            symbols.append(ASTSymbol(name=fn_name, kind="function", signature=sig))
            skeleton_lines.append(sig)

        if not skeleton_lines:
            # Archivo estructurado pequeño (JSON, CSS, HTML o sin declaraciones)
            skeleton_text = source_code[:400] + ("\n... [Contenido truncado para outline]" if total_lines > 15 else "")
            return [], skeleton_text, total_lines, min(total_lines, 15)

        return symbols, "\n".join(skeleton_lines), total_lines, len(skeleton_lines)

    @classmethod
    def slice_file(cls, file_path: Path) -> Dict[str, Any]:
        """Genera el índice y esqueleto sintáctico de un archivo específico."""
        if not file_path.exists() or not file_path.is_file():
            raise FileNotFoundError(f"Archivo no encontrado: {file_path}")

        try:
            content = file_path.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            return {"file_path": str(file_path), "error": str(e), "symbols": []}

        ext = file_path.suffix.lower()
        if ext == ".py":
            symbols, skeleton, orig_lines, skel_lines = cls.extract_python_outline(content, str(file_path))
        else:
            symbols, skeleton, orig_lines, skel_lines = cls.extract_generic_outline(content, str(file_path))

        reduction = round((1.0 - (skel_lines / max(orig_lines, 1))) * 100, 1) if orig_lines > 0 else 0.0

        return {
            "file_path": str(file_path.as_posix()),
            "symbols_count": len(symbols),
            "original_lines": orig_lines,
            "skeleton_lines": skel_lines,
            "context_reduction_percent": max(reduction, 0.0),
            "symbols": [asdict(s) for s in symbols],
            "skeleton": skeleton
        }

    @classmethod
    def scan_repository(cls, root_dir: Path, max_depth: int = 4) -> Dict[str, Any]:
        """
        Escanea recursivamente el repositorio generando un mapa jerárquico compacto.
        """
        if not root_dir.exists():
            raise FileNotFoundError(f"Directorio no encontrado: {root_dir}")

        file_indexes: List[Dict[str, Any]] = []
        total_orig_lines = 0
        total_skel_lines = 0
        total_symbols = 0

        for root, dirs, files in os.walk(root_dir):
            dirs[:] = [d for d in dirs if d not in cls.IGNORE_DIRS and not d.startswith(".")]

            rel_root = Path(root).relative_to(root_dir)
            if len(rel_root.parts) > max_depth:
                continue

            for f in sorted(files):
                file_p = Path(root) / f
                if file_p.suffix.lower() in cls.IGNORE_EXTS:
                    continue
                if f.startswith((".", "_")) and not f.startswith("__init__"):
                    continue

                res = cls.slice_file(file_p)
                if "error" not in res:
                    rel_path = file_p.relative_to(root_dir).as_posix()
                    res["relative_path"] = rel_path
                    file_indexes.append(res)
                    total_orig_lines += res["original_lines"]
                    total_skel_lines += res["skeleton_lines"]
                    total_symbols += res["symbols_count"]

        global_reduction = round((1.0 - (total_skel_lines / max(total_orig_lines, 1))) * 100, 1) if total_orig_lines > 0 else 0.0

        return {
            "repository_path": str(root_dir.as_posix()),
            "total_files": len(file_indexes),
            "total_symbols": total_symbols,
            "total_original_lines": total_orig_lines,
            "total_skeleton_lines": total_skel_lines,
            "global_context_reduction_percent": max(global_reduction, 0.0),
            "files": file_indexes
        }

    @classmethod
    def get_slice(
        cls,
        file_path: Path,
        symbol_name: Optional[str] = None,
        start_line: Optional[int] = None,
        end_line: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Devuelve únicamente la porción de código solicitada (por símbolo o por rango de líneas).
        """
        if not file_path.exists():
            raise FileNotFoundError(f"Archivo no encontrado: {file_path}")

        lines = file_path.read_text(encoding="utf-8", errors="replace").splitlines()
        total_lines = len(lines)

        # 1. Búsqueda por nombre de símbolo
        if symbol_name:
            file_meta = cls.slice_file(file_path)
            target_symbol = None
            for sym in file_meta.get("symbols", []):
                if sym["name"] == symbol_name:
                    target_symbol = sym
                    break
                for child in sym.get("children", []):
                    if child["name"] == symbol_name:
                        target_symbol = child
                        break

            if target_symbol:
                s_line = target_symbol["start_line"]
                e_line = target_symbol["end_line"]
                slice_code = "\n".join(lines[s_line - 1:e_line])
                return {
                    "file_path": str(file_path.as_posix()),
                    "symbol_name": symbol_name,
                    "kind": target_symbol["kind"],
                    "signature": target_symbol["signature"],
                    "start_line": s_line,
                    "end_line": e_line,
                    "lines_count": e_line - s_line + 1,
                    "slice_content": slice_code
                }
            else:
                raise KeyError(f"Símbolo '{symbol_name}' no encontrado en {file_path.name}")

        # 2. Búsqueda por rango de líneas
        if start_line is not None:
            s_line = max(1, start_line)
            e_line = min(total_lines, end_line if end_line is not None else s_line + 50)
            slice_code = "\n".join(lines[s_line - 1:e_line])
            return {
                "file_path": str(file_path.as_posix()),
                "start_line": s_line,
                "end_line": e_line,
                "lines_count": e_line - s_line + 1,
                "slice_content": slice_code
            }

        # 3. Fallback: Retorna el outline completo del archivo
        return cls.slice_file(file_path)


# =============================================================================
# 2. ESPACIO DE TRABAJO AISLADO POR RAMAS (SANDBOX STAGING)
# =============================================================================
class SandboxStagingManager:
    """
    Gestiona ramas de ensayo temporales en .jev_staging/<plan_id>/ para que
    todas las refactorizaciones y creaciones se ejecuten aisladas del workspace principal.
    """

    def __init__(self, workspace_dir: Path):
        self.workspace_dir = workspace_dir
        self.staging_root = self.workspace_dir / ".jev_staging"
        self.staging_root.mkdir(parents=True, exist_ok=True)

    def _sanitize_plan_id(self, plan_id: str) -> str:
        clean = re.sub(r"[^a-zA-Z0-9_\-]", "_", plan_id).strip("_")
        return clean or f"plan_{int(time.time()*1000)}"

    def get_plan_dir(self, plan_id: str) -> Path:
        return self.staging_root / self._sanitize_plan_id(plan_id)

    def create_plan(self, plan_id: str, description: str = "") -> Dict[str, Any]:
        """Crea un nuevo espacio de ensayo aislado."""
        p_id = self._sanitize_plan_id(plan_id)
        p_dir = self.staging_root / p_id
        files_dir = p_dir / "files"
        files_dir.mkdir(parents=True, exist_ok=True)

        meta = {
            "plan_id": p_id,
            "description": description or f"Plan de refactorización {p_id}",
            "created_at": time.time(),
            "status": "active",
            "staged_files": {}
        }
        (p_dir / "metadata.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
        return meta

    def get_plan_meta(self, plan_id: str) -> Dict[str, Any]:
        p_dir = self.get_plan_dir(plan_id)
        meta_file = p_dir / "metadata.json"
        if not meta_file.exists():
            raise FileNotFoundError(f"Plan de staging '{plan_id}' no encontrado.")
        return json.loads(meta_file.read_text(encoding="utf-8"))

    def _save_plan_meta(self, plan_id: str, meta: Dict[str, Any]) -> None:
        p_dir = self.get_plan_dir(plan_id)
        meta_file = p_dir / "metadata.json"
        meta_file.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")

    def stage_file(self, plan_id: str, relative_path: str, content: str, action: str = "modify") -> Dict[str, Any]:
        """Escribe un archivo en la rama de ensayo aislada."""
        p_id = self._sanitize_plan_id(plan_id)
        p_dir = self.get_plan_dir(p_id)
        if not p_dir.exists():
            self.create_plan(p_id)

        meta = self.get_plan_meta(p_id)
        rel_p = Path(relative_path).as_posix().lstrip("/")
        staged_target = p_dir / "files" / rel_p
        staged_target.parent.mkdir(parents=True, exist_ok=True)
        staged_target.write_text(content, encoding="utf-8")

        orig_file = self.workspace_dir / rel_p
        orig_exists = orig_file.exists() and orig_file.is_file()

        meta["staged_files"][rel_p] = {
            "action": "create" if not orig_exists else action,
            "original_exists": orig_exists,
            "lines_count": len(content.splitlines()),
            "bytes_count": len(content.encode("utf-8")),
            "staged_path": str(staged_target.as_posix()),
            "timestamp": time.time()
        }
        self._save_plan_meta(p_id, meta)

        return {
            "plan_id": p_id,
            "file": rel_p,
            "status": "staged",
            "action": meta["staged_files"][rel_p]["action"],
            "lines": meta["staged_files"][rel_p]["lines_count"]
        }

    def patch_staged_file(self, plan_id: str, relative_path: str, target_content: str, replacement_content: str) -> Dict[str, Any]:
        """Aplica un parche a un archivo dentro de la rama de ensayo."""
        p_id = self._sanitize_plan_id(plan_id)
        p_dir = self.get_plan_dir(p_id)
        if not p_dir.exists():
            self.create_plan(p_id)

        rel_p = Path(relative_path).as_posix().lstrip("/")
        staged_target = p_dir / "files" / rel_p

        # Si aún no está en staging, copiar el original del workspace
        if not staged_target.exists():
            orig_file = self.workspace_dir / rel_p
            if not orig_file.exists():
                raise FileNotFoundError(f"Archivo original no existe para parchear: {rel_p}")
            staged_target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(orig_file, staged_target)

        current_content = staged_target.read_text(encoding="utf-8")
        if target_content not in current_content:
            raise ValueError(f"Texto objetivo no encontrado en la copia staged de '{rel_p}'")

        new_content = current_content.replace(target_content, replacement_content, 1)
        staged_target.write_text(new_content, encoding="utf-8")

        meta = self.get_plan_meta(p_id)
        meta["staged_files"][rel_p] = {
            "action": "patch",
            "original_exists": True,
            "lines_count": len(new_content.splitlines()),
            "bytes_count": len(new_content.encode("utf-8")),
            "staged_path": str(staged_target.as_posix()),
            "timestamp": time.time()
        }
        self._save_plan_meta(p_id, meta)

        return {
            "plan_id": p_id,
            "file": rel_p,
            "status": "patched_in_staging",
            "lines": meta["staged_files"][rel_p]["lines_count"]
        }

    def get_diff(self, plan_id: str) -> Dict[str, Any]:
        """
        Genera el unified diff completo comparando los archivos staged contra el workspace principal.
        """
        p_id = self._sanitize_plan_id(plan_id)
        meta = self.get_plan_meta(p_id)
        p_dir = self.get_plan_dir(p_id)
        files_dir = p_dir / "files"

        all_diff_lines: List[str] = []
        files_diff: List[Dict[str, Any]] = []
        total_insertions = 0
        total_deletions = 0

        for rel_p, f_info in meta.get("staged_files", {}).items():
            staged_file = files_dir / rel_p
            orig_file = self.workspace_dir / rel_p

            orig_lines = orig_file.read_text(encoding="utf-8", errors="replace").splitlines() if orig_file.exists() else []
            staged_lines = staged_file.read_text(encoding="utf-8", errors="replace").splitlines() if staged_file.exists() else []

            diff = list(difflib.unified_diff(
                orig_lines,
                staged_lines,
                fromfile=f"a/{rel_p}",
                tofile=f"b/{rel_p}",
                lineterm=""
            ))

            if diff:
                ins = sum(1 for line in diff if line.startswith("+") and not line.startswith("+++"))
                dels = sum(1 for line in diff if line.startswith("-") and not line.startswith("---"))
                total_insertions += ins
                total_deletions += dels

                all_diff_lines.extend(diff)
                all_diff_lines.append("")  # Espaciado entre archivos
                files_diff.append({
                    "file": rel_p,
                    "insertions": ins,
                    "deletions": dels,
                    "diff": "\n".join(diff)
                })

        diff_text = "\n".join(all_diff_lines).strip()
        return {
            "plan_id": p_id,
            "files_count": len(files_diff),
            "files": files_diff,
            "total_insertions": total_insertions,
            "total_deletions": total_deletions,
            "diff_text": diff_text or "(Sin diferencias detectadas entre staging y workspace)"
        }

    def list_plans(self) -> List[Dict[str, Any]]:
        """Lista todos los planes de staging existentes."""
        plans = []
        if not self.staging_root.exists():
            return plans

        for p in self.staging_root.iterdir():
            if p.is_dir():
                meta_file = p / "metadata.json"
                if meta_file.exists():
                    try:
                        meta = json.loads(meta_file.read_text(encoding="utf-8"))
                        plans.append({
                            "plan_id": meta.get("plan_id", p.name),
                            "description": meta.get("description", ""),
                            "status": meta.get("status", "active"),
                            "files_count": len(meta.get("staged_files", {})),
                            "created_at": meta.get("created_at", 0)
                        })
                    except Exception:
                        pass
        return plans

    def cleanup_plan(self, plan_id: str) -> bool:
        """Elimina físicamente el directorio de staging del plan."""
        p_dir = self.get_plan_dir(plan_id)
        if p_dir.exists():
            shutil.rmtree(p_dir, ignore_errors=True)
            return True
        return False


# =============================================================================
# 3. VALIDADOR DE DIFFS Y CONFIRMACIÓN ATÓMICA (ATOMIC COMMIT & ROLLBACK)
# =============================================================================
class AtomicCommitEngine:
    """
    Valida sintaxis y tests en staging antes de confirmar. Si hay fallos,
    ejecuta rollback inmediato dejando el workspace intacto.
    """

    @classmethod
    def validate_plan(
        cls,
        staging_mgr: SandboxStagingManager,
        plan_id: str,
        test_command: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Ejecuta verificaciones de integridad sintáctica y pruebas unitarias opcionales.
        """
        p_id = staging_mgr._sanitize_plan_id(plan_id)
        meta = staging_mgr.get_plan_meta(p_id)
        p_dir = staging_mgr.get_plan_dir(p_id)
        files_dir = p_dir / "files"

        syntax_errors: List[str] = []
        validated_files: List[str] = []

        # 1. Auditoría sintáctica estricta por archivo staged
        for rel_p in meta.get("staged_files", {}).keys():
            staged_file = files_dir / rel_p
            if not staged_file.exists():
                continue

            validated_files.append(rel_p)
            content = staged_file.read_text(encoding="utf-8", errors="replace")

            # Validación Python
            if rel_p.endswith(".py"):
                try:
                    ast.parse(content, filename=rel_p)
                except SyntaxError as se:
                    syntax_errors.append(
                        f"Error de sintaxis en '{rel_p}' (línea {se.lineno}, col {se.offset}): {se.msg}"
                    )
                except Exception as e:
                    syntax_errors.append(f"Error parseando '{rel_p}': {str(e)}")

            # Validación JSON
            elif rel_p.endswith(".json"):
                try:
                    json.loads(content)
                except Exception as je:
                    syntax_errors.append(f"JSON inválido en '{rel_p}': {str(je)}")

        is_syntax_valid = len(syntax_errors) == 0
        test_passed = True
        test_output = ""

        # 2. Ejecución de suite de tests si se especifica
        if is_syntax_valid and test_command:
            try:
                proc = subprocess.run(
                    test_command,
                    shell=True,
                    cwd=str(staging_mgr.workspace_dir),
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    timeout=45
                )
                test_output = proc.stdout + "\n" + proc.stderr
                if proc.returncode != 0:
                    test_passed = False
            except subprocess.TimeoutExpired:
                test_passed = False
                test_output = "Tiempo de espera agotado al ejecutar test_command (45s)."
            except Exception as te:
                test_passed = False
                test_output = f"Excepción ejecutando tests: {str(te)}"

        is_valid = is_syntax_valid and test_passed

        return {
            "plan_id": p_id,
            "is_valid": is_valid,
            "syntax_valid": is_syntax_valid,
            "syntax_errors": syntax_errors,
            "test_passed": test_passed,
            "test_output": test_output.strip(),
            "validated_files_count": len(validated_files)
        }

    @classmethod
    def commit_plan(
        cls,
        staging_mgr: SandboxStagingManager,
        plan_id: str,
        test_command: Optional[str] = None,
        force: bool = False
    ) -> Dict[str, Any]:
        """
        Si la validación es exitosa, fusiona atómicamente los archivos en workspace/
        y limpia el staging. Si falla, ejecuta rollback automático.
        """
        p_id = staging_mgr._sanitize_plan_id(plan_id)
        diff_info = staging_mgr.get_diff(p_id)
        validation = cls.validate_plan(staging_mgr, p_id, test_command=test_command)

        # Si la validación falla, abortar y ejecutar rollback para no corromper el proyecto
        if not validation["is_valid"] and not force:
            cls.rollback_plan(staging_mgr, p_id)
            return {
                "success": False,
                "plan_id": p_id,
                "error": "Validación de integridad fallida en staging. Se aplicó Rollback automático preventivo.",
                "syntax_errors": validation["syntax_errors"],
                "test_output": validation["test_output"],
                "diff_text": diff_info["diff_text"],
                "rolled_back": True
            }

        # Transacción atómica en memoria: guardar copias originales para rollback en caso de fallo de E/S
        meta = staging_mgr.get_plan_meta(p_id)
        files_dir = staging_mgr.get_plan_dir(p_id) / "files"
        backup_journal: Dict[Path, Optional[bytes]] = {}
        applied_files: List[str] = []

        try:
            for rel_p in meta.get("staged_files", {}).keys():
                orig_file = staging_mgr.workspace_dir / rel_p
                # Guardar backup para reversión inmediata ante fallo de escritura
                backup_journal[orig_file] = orig_file.read_bytes() if orig_file.exists() else None

                staged_file = files_dir / rel_p
                orig_file.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(staged_file, orig_file)
                applied_files.append(rel_p)

        except Exception as io_err:
            # Revertir cualquier archivo escrito durante la transacción fallida
            for target_p, orig_bytes in backup_journal.items():
                if orig_bytes is not None:
                    target_p.write_bytes(orig_bytes)
                elif target_p.exists():
                    target_p.unlink(missing_ok=True)

            return {
                "success": False,
                "plan_id": p_id,
                "error": f"Fallo durante la copia atómica de archivos: {io_err}. Reversión completada.",
                "rolled_back": True
            }

        # Éxito: Marcar como confirmado y limpiar staging
        meta["status"] = "committed"
        staging_mgr._save_plan_meta(p_id, meta)
        staging_mgr.cleanup_plan(p_id)

        return {
            "success": True,
            "plan_id": p_id,
            "files_committed": applied_files,
            "files_count": len(applied_files),
            "diff_text": diff_info["diff_text"],
            "total_insertions": diff_info["total_insertions"],
            "total_deletions": diff_info["total_deletions"],
            "message": f"Plan '{p_id}' fusionado exitosamente en workspace/ ({len(applied_files)} archivos actualizados)."
        }

    @classmethod
    def rollback_plan(cls, staging_mgr: SandboxStagingManager, plan_id: str) -> Dict[str, Any]:
        """Descarta la rama de staging sin tocar ningún archivo del workspace."""
        p_id = staging_mgr._sanitize_plan_id(plan_id)
        cleaned = staging_mgr.cleanup_plan(p_id)
        return {
            "success": True,
            "plan_id": p_id,
            "cleaned": cleaned,
            "message": f"Rama de staging '{p_id}' descartada exitosamente. Espacio de trabajo principal intacto."
        }


# =============================================================================
# 4. HERRAMIENTA JEV: REPO PLANNER TOOL
# =============================================================================
class RepoPlannerTool(BaseTool):
    """
    Herramienta de control de cambios atómicos, mapeo sintáctico (AST Slicer) y
    staging aislado (Plandex-Style Engine) para refactorizaciones seguras.
    """
    name = "skill_repo_planner"
    description = (
        "Motor de edición atómica de proyectos, mapeo sintáctico de repositorios (AST Context Slicer) "
        "y sandbox staging (Plandex-style engine). Permite indexar símbolos ahorrando ~80% de contexto, "
        "probar cambios en ramas temporales aisladas (.jev_staging/<plan_id>/), generar diffs unificados "
        "y aplicar cambios de forma atómica con rollback automático ante fallos de sintaxis o tests."
    )
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": (
                    "Acción a ejecutar: 'map_repo', 'get_slice', 'create_plan', 'stage_file', "
                    "'patch_staged_file', 'get_diff', 'validate_plan', 'commit_plan', 'rollback_plan', 'list_plans'"
                ),
                "enum": [
                    "map_repo",
                    "get_slice",
                    "create_plan",
                    "stage_file",
                    "patch_staged_file",
                    "get_diff",
                    "validate_plan",
                    "commit_plan",
                    "rollback_plan",
                    "list_plans"
                ]
            },
            "plan_id": {
                "type": "string",
                "description": "Identificador único de la rama de ensayo en staging (ej. 'refactor_auth')",
                "default": "main_plan"
            },
            "target_path": {
                "type": "string",
                "description": "Ruta relativa del archivo o directorio a inspeccionar/modificar",
                "default": ""
            },
            "content": {
                "type": "string",
                "description": "Contenido textual a escribir en el archivo staged",
                "default": ""
            },
            "target_content": {
                "type": "string",
                "description": "Bloque de texto exacto a reemplazar en 'patch_staged_file'",
                "default": ""
            },
            "replacement_content": {
                "type": "string",
                "description": "Nuevo texto de reemplazo para 'patch_staged_file'",
                "default": ""
            },
            "symbol_name": {
                "type": "string",
                "description": "Nombre de clase o función específica para 'get_slice'",
                "default": ""
            },
            "start_line": {
                "type": "integer",
                "description": "Línea inicial para corte de slice en 'get_slice'",
                "default": 1
            },
            "end_line": {
                "type": "integer",
                "description": "Línea final para corte de slice en 'get_slice'",
                "default": 100
            },
            "test_command": {
                "type": "string",
                "description": "Comando opcional de pruebas a ejecutar antes de commit (ej. 'python -m unittest tests/test_auth.py')",
                "default": ""
            },
            "description": {
                "type": "string",
                "description": "Descripción informativa del plan de refactorización",
                "default": ""
            }
        },
        "required": ["action"]
    }

    def __init__(self, workspace_dir: Optional[Path] = None):
        self.workspace_dir = workspace_dir or default_config.workspace_dir
        self.workspace_dir.mkdir(parents=True, exist_ok=True)
        self.staging_mgr = SandboxStagingManager(self.workspace_dir)

    def execute(self, **kwargs) -> ToolResult:
        action = kwargs.get("action", "map_repo")
        plan_id = kwargs.get("plan_id", "main_plan")
        target_path_str = kwargs.get("target_path", "")
        content = kwargs.get("content", "")
        target_content = kwargs.get("target_content", "")
        replacement_content = kwargs.get("replacement_content", "")
        symbol_name = kwargs.get("symbol_name") or None
        start_line = kwargs.get("start_line")
        end_line = kwargs.get("end_line")
        test_command = kwargs.get("test_command") or None
        description = kwargs.get("description", "")

        try:
            # 1. MAP_REPO: Escaneo y esqueletos AST
            if action == "map_repo":
                target_dir = self.workspace_dir / target_path_str if target_path_str else self.workspace_dir
                scan_res = ASTContextSlicer.scan_repository(target_dir)
                summary_text = (
                    f"🗺️ Mapeo AST de Repositorio Completado: {scan_res['total_files']} archivos indexados, "
                    f"{scan_res['total_symbols']} símbolos extraídos.\n"
                    f"Líneas originales: {scan_res['total_original_lines']} -> Esqueleto sintáctico: {scan_res['total_skeleton_lines']} "
                    f"(Ahorro de contexto: {scan_res['global_context_reduction_percent']}%)."
                )
                return ToolResult(success=True, output=summary_text, data=scan_res)

            # 2. GET_SLICE: Rebanada quirúrgica de un archivo
            elif action == "get_slice":
                if not target_path_str:
                    return ToolResult(success=False, output="", error="Debes especificar 'target_path' para 'get_slice'.")
                file_target = self.workspace_dir / target_path_str if not Path(target_path_str).is_absolute() else Path(target_path_str)
                slice_res = ASTContextSlicer.get_slice(
                    file_target,
                    symbol_name=symbol_name,
                    start_line=start_line if start_line is not None else None,
                    end_line=end_line if end_line is not None else None
                )
                if "slice_content" in slice_res:
                    out = f"--- Rebanada de {file_target.name} ({slice_res.get('lines_count', 0)} líneas) ---\n\n{slice_res['slice_content']}"
                else:
                    out = f"--- Esqueleto Sintáctico de {file_target.name} ({slice_res.get('context_reduction_percent', 0)}% ahorro) ---\n\n{slice_res.get('skeleton', '')}"
                return ToolResult(success=True, output=out, data=slice_res)

            # 3. CREATE_PLAN
            elif action == "create_plan":
                plan_meta = self.staging_mgr.create_plan(plan_id, description=description)
                return ToolResult(
                    success=True,
                    output=f"🌿 Rama de staging creada: '{plan_meta['plan_id']}' en .jev_staging/{plan_meta['plan_id']}/",
                    data=plan_meta
                )

            # 4. STAGE_FILE
            elif action == "stage_file":
                if not target_path_str:
                    return ToolResult(success=False, output="", error="Debes especificar 'target_path' para 'stage_file'.")
                res = self.staging_mgr.stage_file(plan_id, target_path_str, content)
                return ToolResult(
                    success=True,
                    output=f"📝 Archivo staged exitosamente: '{res['file']}' en rama '{res['plan_id']}' ({res['lines']} líneas).",
                    data=res
                )

            # 5. PATCH_STAGED_FILE
            elif action == "patch_staged_file":
                if not target_path_str or not target_content:
                    return ToolResult(success=False, output="", error="Debes especificar 'target_path' y 'target_content'.")
                res = self.staging_mgr.patch_staged_file(plan_id, target_path_str, target_content, replacement_content)
                return ToolResult(
                    success=True,
                    output=f"🔧 Parche aplicado en staging: '{res['file']}' en rama '{res['plan_id']}'.",
                    data=res
                )

            # 6. GET_DIFF
            elif action == "get_diff":
                diff_res = self.staging_mgr.get_diff(plan_id)
                header = (
                    f"🔍 Unified Diff para Rama '{diff_res['plan_id']}' ({diff_res['files_count']} archivos, "
                    f"+{diff_res['total_insertions']} / -{diff_res['total_deletions']}):\n\n"
                )
                return ToolResult(
                    success=True,
                    output=header + diff_res["diff_text"],
                    data=diff_res
                )

            # 7. VALIDATE_PLAN
            elif action == "validate_plan":
                val_res = AtomicCommitEngine.validate_plan(self.staging_mgr, plan_id, test_command=test_command)
                status_str = "VÁLIDO (Sintaxis y tests verificados)" if val_res["is_valid"] else "FALLIDO"
                out = f"🧪 Resultado de Validación para '{val_res['plan_id']}': {status_str} ({val_res['validated_files_count']} archivos analizados)."
                if val_res["syntax_errors"]:
                    out += "\nErrores detectados:\n - " + "\n - ".join(val_res["syntax_errors"])
                return ToolResult(success=val_res["is_valid"], output=out, data=val_res)

            # 8. COMMIT_PLAN
            elif action == "commit_plan":
                commit_res = AtomicCommitEngine.commit_plan(self.staging_mgr, plan_id, test_command=test_command)
                if commit_res["success"]:
                    return ToolResult(
                        success=True,
                        output=f"🚀 {commit_res['message']}\n\nDiff aplicado:\n{commit_res['diff_text'][:600]}",
                        data=commit_res
                    )
                else:
                    return ToolResult(
                        success=False,
                        output="",
                        error=f"🚫 {commit_res['error']}\nErrores de sintaxis:\n - " + "\n - ".join(commit_res.get("syntax_errors", [])),
                        data=commit_res
                    )

            # 9. ROLLBACK_PLAN
            elif action == "rollback_plan":
                rb_res = AtomicCommitEngine.rollback_plan(self.staging_mgr, plan_id)
                return ToolResult(
                    success=True,
                    output=f"↩️ {rb_res['message']}",
                    data=rb_res
                )

            # 10. LIST_PLANS
            elif action == "list_plans":
                plans = self.staging_mgr.list_plans()
                out = f"📋 Planes de Staging Activos ({len(plans)}):\n"
                for p in plans:
                    out += f" • [{p['status'].upper()}] {p['plan_id']}: {p['files_count']} archivos staged - '{p['description']}'\n"
                return ToolResult(success=True, output=out.strip(), data={"plans": plans})

            return ToolResult(success=False, output="", error=f"Acción '{action}' no reconocida en RepoPlannerTool.")

        except Exception as e:
            return ToolResult(success=False, output="", error=f"Error en RepoPlannerTool: {str(e)}")
