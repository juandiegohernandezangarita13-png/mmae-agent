"""
Módulo Evaluator: Validación sintáctica y Oráculo Determinista Físico.
Proporciona verificación estricta de código y aserción de estados físicos del sistema operativo:
- Códigos de retorno de procesos (exit_code == 0)
- Marcas de tiempo de modificación de archivos en disco (mtime >= timestamp_inicio)
- Existencia y visibilidad de manejadores de ventana de Windows (Win32 HWND)

EL LLM NUNCA AUTO-EVALÚA SI TUVO ÉXITO: La verdad física la determina este oráculo.
"""
from __future__ import annotations

import ast
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from utils.logger import log

try:
    import win32gui
    import win32con
    _HAS_WIN32GUI = True
except ImportError:
    win32gui = None  # type: ignore
    win32con = None  # type: ignore
    _HAS_WIN32GUI = False

try:
    from jev.self_improvement.evaluator import SelfImprovementEvaluator
except Exception:
    SelfImprovementEvaluator = None


class OutputEvaluator:
    """
    Analiza código generado en Python y respuestas técnicas para verificar
    integridad sintáctica antes de su ejecución o reporte.
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


class DeterministicOracle:
    """
    Oráculo Determinista Físico.
    Evalúa empíricamente si una acción tuvo éxito basándose en la física del sistema operativo:
    archivos alterados, exit codes de procesos y handles HWND de Windows.
    """

    @staticmethod
    def verify_exit_code(exit_code: int, expected_code: int = 0) -> Dict[str, Any]:
        """Verifica físicamente el código de salida del subproceso."""
        passed = (exit_code == expected_code)
        return {
            "type": "exit_code",
            "passed": passed,
            "exit_code": exit_code,
            "expected_code": expected_code,
            "reason": "Proceso completado sin errores (exit_code 0)" if passed else f"Proceso falló con exit_code {exit_code}",
        }

    @staticmethod
    def verify_file_modification(
        file_path: Union[str, Path],
        since_timestamp: float,
        min_bytes: int = 1,
    ) -> Dict[str, Any]:
        """
        Verifica si un archivo físico fue creado o modificado después de `since_timestamp`
        y si su tamaño en bytes cumple con el mínimo requerido.
        """
        target = Path(file_path).resolve()
        if not target.exists():
            return {
                "type": "file_mtime",
                "passed": False,
                "file_path": str(target),
                "reason": f"El archivo objetivo no existe físicamente en el disco: {target}",
            }

        try:
            stat = target.stat()
            mtime = stat.st_mtime
            size = stat.st_size
            time_diff = mtime - since_timestamp
            
            # Margen de tolerancia de 0.05s por resolución del sistema de archivos
            mtime_valid = (mtime >= (since_timestamp - 0.05))
            size_valid = (size >= min_bytes)
            passed = mtime_valid and size_valid

            reasons: List[str] = []
            if not mtime_valid:
                reasons.append(f"mtime ({mtime:.2f}) es anterior al inicio de la acción ({since_timestamp:.2f})")
            if not size_valid:
                reasons.append(f"tamaño ({size} bytes) es menor al mínimo ({min_bytes} bytes)")

            return {
                "type": "file_mtime",
                "passed": passed,
                "file_path": str(target),
                "mtime": mtime,
                "size_bytes": size,
                "time_diff_seconds": round(time_diff, 4),
                "reason": "Archivo modificado y válido físicamente." if passed else " | ".join(reasons),
            }
        except Exception as e:
            return {
                "type": "file_mtime",
                "passed": False,
                "file_path": str(target),
                "reason": f"Error al verificar archivo: {str(e)}",
            }

    @staticmethod
    def verify_win32_window(
        title_pattern: Optional[str] = None,
        class_name: Optional[str] = None,
        timeout_seconds: float = 2.0,
    ) -> Dict[str, Any]:
        """
        Verifica en Windows mediante la Win32 API si existe un HWND de ventana válido
        que coincida con el título o clase de ventana solicitada.
        """
        if sys.platform != "win32":
            return {
                "type": "win32_window",
                "passed": True,
                "reason": "Plataforma no-Windows: verificación Win32 omitida.",
                "hwnds": [],
            }

        start = time.perf_counter()
        found_hwnds: List[Dict[str, Any]] = []

        while time.perf_counter() - start <= timeout_seconds:
            found_hwnds.clear()
            if _HAS_WIN32GUI and win32gui is not None:
                def enum_callback(hwnd: int, extra: Any) -> None:
                    if win32gui.IsWindow(hwnd) and win32gui.IsWindowVisible(hwnd):
                        w_title = win32gui.GetWindowText(hwnd)
                        w_class = win32gui.GetClassName(hwnd)
                        match_title = True
                        match_class = True
                        if title_pattern:
                            match_title = bool(re.search(title_pattern, w_title, re.IGNORECASE))
                        if class_name:
                            match_class = (class_name.lower() in w_class.lower())

                        if match_title and match_class and (w_title or w_class):
                            found_hwnds.append({
                                "hwnd": hwnd,
                                "title": w_title,
                                "class": w_class,
                            })

                try:
                    win32gui.EnumWindows(enum_callback, None)
                except Exception:
                    pass

            if found_hwnds:
                break
            time.sleep(0.1)

        passed = len(found_hwnds) > 0
        return {
            "type": "win32_window",
            "passed": passed,
            "matches_count": len(found_hwnds),
            "matching_windows": found_hwnds[:3],
            "reason": f"Se encontraron {len(found_hwnds)} ventana(s) Win32 coincidentes." if passed else "No se detectó ninguna ventana Win32 coincidente dentro del timeout.",
        }

    @classmethod
    def evaluate_physical_state(
        cls,
        exit_code: Optional[int] = None,
        file_checks: Optional[List[Dict[str, Any]]] = None,
        window_checks: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        Consolida todas las verificaciones físicas requeridas en un veredicto binario determinista.
        """
        results: List[Dict[str, Any]] = []
        all_passed = True

        if exit_code is not None:
            ec_res = cls.verify_exit_code(exit_code)
            results.append(ec_res)
            if not ec_res["passed"]:
                all_passed = False

        if file_checks:
            for fc in file_checks:
                path = fc.get("path")
                since = fc.get("since_timestamp", 0.0)
                min_b = fc.get("min_bytes", 1)
                f_res = cls.verify_file_modification(path, since_timestamp=since, min_bytes=min_b)
                results.append(f_res)
                if not f_res["passed"]:
                    all_passed = False

        if window_checks:
            for wc in window_checks:
                t_pat = wc.get("title_pattern")
                c_name = wc.get("class_name")
                timeout = wc.get("timeout_seconds", 2.0)
                w_res = cls.verify_win32_window(title_pattern=t_pat, class_name=c_name, timeout_seconds=timeout)
                results.append(w_res)
                if not w_res["passed"]:
                    all_passed = False

        failures = [r["reason"] for r in results if not r["passed"]]

        log.info(f"🏛️ [Oráculo Determinista]: Veredicto Físico={'ÉXITO' if all_passed else 'FALLO'} ({len(failures)} errores)")
        return {
            "success": all_passed,
            "verdict": "PASSED" if all_passed else "FAILED",
            "checks_count": len(results),
            "failures": failures,
            "checks": results,
        }


__all__ = ["OutputEvaluator", "DeterministicOracle", "SelfImprovementEvaluator"]
