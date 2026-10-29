"""
Handler para skill_database_query_optimizer.
Analizador y optimizador de consultas SQL.
"""
from typing import Dict, Any, List
import re

def handle(**kwargs) -> Dict[str, Any]:
    query = kwargs.get("query", "").strip()
    if not query:
        return {"status": "error", "error": "Query SQL vacío."}

    recommendations: List[str] = []
    complexity_score = 100

    # 1. Detección de SELECT *
    if "SELECT *" in query.upper() or "SELECT  *" in query.upper():
        recommendations.append("Antipatrón 'SELECT *' detectado. Proyectar explícitamente únicamente las columnas requeridas para reducir I/O y uso de memoria.")
        complexity_score -= 20

    # 2. Falta de LIMIT en queries SELECT
    if "SELECT" in query.upper() and "LIMIT" not in query.upper():
        recommendations.append("Consulta no acotada sin cláusula 'LIMIT'. Riesgo de saturación de cursor en producción.")
        complexity_score -= 15

    # 3. Detección de joins sin índices o productos cartesianos en FROM
    from_part = query.upper().split("FROM")[1].split("WHERE")[0] if "FROM" in query.upper() else ""
    if "," in from_part and "JOIN" not in from_part:
        recommendations.append("Sintaxis de JOIN implícito antiguo detectada. Utilizar 'INNER JOIN ... ON' explícito para evitar producto cartesiano accidental.")
        complexity_score -= 25

    # 4. Búsqueda con comodín inicial LIKE '%...'
    if "LIKE '%" in query.upper() or 'LIKE "%' in query.upper():
        recommendations.append("Operador LIKE con comodín inicial ('%...') invalida índices B-Tree estándar; forzará Full Table Scan.")
        complexity_score -= 30

    table_match = re.search(r"FROM\s+([a-zA-Z0-9_]+)", query, re.IGNORECASE)
    table_name = table_match.group(1) if table_match else "tabla"

    return {
        "status": "success",
        "target_table": table_name,
        "health_score": max(complexity_score, 10),
        "issues_detected": len(recommendations),
        "recommendations": recommendations,
        "is_production_ready": len(recommendations) == 0
    }
