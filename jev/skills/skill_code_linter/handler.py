"""
Habilidad de Validación Estática y Linting de Código Python (skill_code_linter).
Utiliza el compilador interno 'ast.parse' para verificar sintaxis,
detectar placeholders incompletos ('pass', '...', 'TODO') y antipatrones.
"""
from typing import Dict, Any, List, Optional
import ast
import re


class CodeAuditVisitor(ast.NodeVisitor):
    def __init__(self, strict_placeholders: bool = True):
        self.strict_placeholders = strict_placeholders
        self.errors: List[Dict[str, Any]] = []
        self.warnings: List[Dict[str, Any]] = []
        self.function_count = 0
        self.class_count = 0
        self.import_count = 0

    def visit_FunctionDef(self, node: ast.FunctionDef):
        self.function_count += 1
        self._check_placeholder_body(node, f"función '{node.name}'")
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
        self.function_count += 1
        self._check_placeholder_body(node, f"función asíncrona '{node.name}'")
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef):
        self.class_count += 1
        self.generic_visit(node)

    def visit_Import(self, node: ast.Import):
        self.import_count += len(node.names)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom):
        self.import_count += len(node.names)
        self.generic_visit(node)

    def visit_Try(self, node: ast.Try):
        # Detectar except Exception: pass
        for handler in node.handlers:
            if len(handler.body) == 1 and isinstance(handler.body[0], ast.Pass):
                self.warnings.append({
                    "line": handler.lineno,
                    "type": "bare_suppressed_exception",
                    "message": "Bloque 'except: pass' silencia excepciones sin registrar eventos ni logging."
                })
        self.generic_visit(node)

    def _check_placeholder_body(self, node, label: str):
        # Si el cuerpo de la función consta únicamente de docstring y/o pass / ...
        body = node.body
        is_placeholder = False

        # Si el cuerpo tiene solo pass
        if len(body) == 1 and isinstance(body[0], ast.Pass):
            is_placeholder = True
        # Si el cuerpo tiene solo Ellipsis (...)
        elif len(body) == 1 and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) and body[0].value.value is Ellipsis:
            is_placeholder = True
        # Si tiene docstring y luego pass
        elif len(body) == 2 and isinstance(body[0], ast.Expr) and isinstance(body[1], ast.Pass):
            is_placeholder = True

        if is_placeholder:
            msg = f"La {label} (línea {node.lineno}) es un placeholder incompleto (cuerpo vacío con pass o ...)."
            if self.strict_placeholders:
                self.errors.append({"line": node.lineno, "type": "empty_placeholder", "message": msg})
            else:
                self.warnings.append({"line": node.lineno, "type": "empty_placeholder", "message": msg})


def lint_python_code(code: str, file_path: str = "script.py", strict_placeholders: bool = True) -> Dict[str, Any]:
    """
    Parsea y audita código fuente de Python.
    Retorna un diccionario detallado con 'valid', 'errors', 'warnings' y 'stats'.
    """
    errors: List[Dict[str, Any]] = []
    warnings: List[Dict[str, Any]] = []

    # 1. Chequeo de sintaxis pura con ast.parse
    try:
        tree = ast.parse(code, filename=file_path)
    except SyntaxError as se:
        return {
            "valid": False,
            "file": file_path,
            "errors": [{
                "line": se.lineno,
                "col": se.offset,
                "type": "SyntaxError",
                "message": se.msg,
                "snippet": se.text.strip() if se.text else ""
            }],
            "warnings": [],
            "stats": {"functions": 0, "classes": 0, "imports": 0}
        }
    except Exception as e:
        return {
            "valid": False,
            "file": file_path,
            "errors": [{
                "line": 0,
                "col": 0,
                "type": "ParseError",
                "message": str(e),
                "snippet": ""
            }],
            "warnings": [],
            "stats": {"functions": 0, "classes": 0, "imports": 0}
        }

    # 2. Búsqueda de comentarios de deuda técnica (TODO / FIXME)
    todo_matches = re.finditer(r"#\s*(TODO|FIXME|XXX):?\s*(.*)", code, re.IGNORECASE)
    for m in todo_matches:
        line_no = code[:m.start()].count("\n") + 1
        warnings.append({
            "line": line_no,
            "type": "todo_marker",
            "message": f"Marcador de tarea incompleta: {m.group(0).strip()}"
        })

    # 3. Recorrido AST
    visitor = CodeAuditVisitor(strict_placeholders=strict_placeholders)
    visitor.visit(tree)
    errors.extend(visitor.errors)
    warnings.extend(visitor.warnings)

    is_valid = len(errors) == 0

    return {
        "valid": is_valid,
        "file": file_path,
        "errors": errors,
        "warnings": warnings,
        "stats": {
            "functions": visitor.function_count,
            "classes": visitor.class_count,
            "imports": visitor.import_count,
            "lines": code.count("\n") + 1
        }
    }


def handle(code: str, file_path: str = "code.py", strict_placeholders: bool = True) -> Dict[str, Any]:
    """Punto de entrada de la habilidad."""
    return lint_python_code(code=code, file_path=file_path, strict_placeholders=strict_placeholders)
