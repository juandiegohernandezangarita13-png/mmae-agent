import ast
from typing import Dict, Any

try:
    from jev.self_improvement.evaluator import SelfImprovementEvaluator
except Exception:
    SelfImprovementEvaluator = None

class OutputEvaluator:
    """
    Analiza código generado en Python y respuestas técnicas para verificar
    integridad sintáctica antes de su reporte final.
    """
    @staticmethod
    def validate_python_code(code_string: str) -> Dict[str, Any]:
        try:
            ast.parse(code_string)
            return {
                "valid": True,
                "message": "Sintaxis de Python verificada correctamente."
            }
        except SyntaxError as e:
            return {
                "valid": False,
                "error": f"Error de sintaxis en línea {e.lineno}: {e.msg}",
                "line": e.lineno
            }
        except Exception as e:
            return {
                "valid": False,
                "error": str(e)
            }
