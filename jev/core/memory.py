"""
Sistema de Memoria Jerárquica para JEV:
1. Memoria de Trabajo (Short-term): Registro de pasos en sesión activa para deduplicación estricta.
2. Memoria Procedimental y Semántica (Long-term en SQLite): Base de datos de soluciones previas,
   snippets funcionales probados y reglas aprendidas del entorno.
"""
from typing import List, Dict, Any, Optional
import json
import sqlite3
import hashlib
from pathlib import Path
from datetime import datetime

from jev.config import default_config


class HierarchicalMemory:
    """Gestiona memoria de corto plazo y memoria procedimental/semántica en SQLite."""

    def __init__(self, memory_dir: Optional[Path] = None):
        self.memory_dir = memory_dir or default_config.memory_dir
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.memory_dir / "knowledge_base.db"
        self.episodes_file = self.memory_dir / "episodes.jsonl"
        self.lessons_file = self.memory_dir / "learned_lessons.json"
        self._init_sqlite()

    def _init_sqlite(self) -> None:
        """Inicializa el esquema relacional en SQLite."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            # 1. Memoria de trabajo (Short-term)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS short_term_steps (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT,
                    step_number INTEGER,
                    tool_name TEXT,
                    args_hash TEXT,
                    arguments_json TEXT,
                    success INTEGER,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            # 2. Memoria procedimental y semántica (Long-term)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS procedural_solutions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    category TEXT,
                    phase TEXT DEFAULT 'general',
                    trigger_keywords TEXT,
                    problem_description TEXT,
                    solution_summary TEXT,
                    working_snippet TEXT,
                    times_reused INTEGER DEFAULT 1,
                    last_used DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            try:
                cursor.execute("ALTER TABLE procedural_solutions ADD COLUMN phase TEXT DEFAULT 'general'")
            except sqlite3.OperationalError:
                pass

            # Sembrar solución procedimental para apertura de apps de Windows y WhatsApp
            cursor.execute("SELECT COUNT(*) FROM procedural_solutions WHERE category = 'windows_apps'")
            if cursor.fetchone()[0] == 0:
                cursor.execute("""
                    INSERT INTO procedural_solutions 
                    (category, phase, trigger_keywords, problem_description, solution_summary, working_snippet)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    "windows_apps",
                    "execution",
                    "whatsapp abrir chat mensaje contactar windows app",
                    "Apertura de WhatsApp y envío de mensajes en Windows",
                    "Abrir mediante Start-Process 'whatsapp:' o web.whatsapp.com. NUNCA abrir ms-settings ni configuraciones de Edge. Chatear: Ctrl+F -> contacto -> Enter -> mensaje -> Enter.",
                    """# 1. Apertura directa de WhatsApp:
# PowerShell: Start-Process "whatsapp:"
# Terminal: start whatsapp:
# Alternativa web: start https://web.whatsapp.com

# 2. Interacción con chat:
# keyboard_press(keys=['ctrl', 'f'])
# keyboard_type(text='nombre_contacto')
# keyboard_press(keys=['enter'])
# keyboard_type(text='mensaje')
# keyboard_press(keys=['enter'])"""
                ))

            # Sembrar solución procedimental para arquitectura de código profesional
            cursor.execute("SELECT COUNT(*) FROM procedural_solutions WHERE category = 'software_engineering'")
            if cursor.fetchone()[0] == 0:
                cursor.execute("""
                    INSERT INTO procedural_solutions 
                    (category, phase, trigger_keywords, problem_description, solution_summary, working_snippet)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    "software_engineering",
                    "execution",
                    "script codigo python concurrencia rendimiento red escanear profesional modular",
                    "Estándar senior de arquitectura para scripts y herramientas en Python",
                    "Concurrencia real con ThreadPoolExecutor/asyncio, CLI robusto con argparse, observabilidad con logging estructurado, manejo granular de excepciones y desacoplamiento modular en clases (SRP/SOLID).",
                    """import argparse
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

class ServiceAuditor:
    def __init__(self, timeout: float = 2.0):
        self.timeout = timeout

    def check_target(self, target: str) -> Dict[str, Any]:
        try:
            # Operación I/O no bloqueante con timeout estricto
            return {"target": target, "status": "success"}
        except (TimeoutError, ConnectionRefusedError) as net_err:
            logger.debug(f"Fallo de conexión en {target}: {net_err}")
            return {"target": target, "status": "failed", "error": str(net_err)}

def main():
    parser = argparse.ArgumentParser(description="Herramienta profesional concurrente")
    parser.add_argument("--target", required=True, help="Objetivo / subred")
    parser.add_argument("--threads", type=int, default=20, help="Hilos de ejecución")
    parser.add_argument("--timeout", type=float, default=2.0, help="Timeout en segundos")
    parser.add_argument("--verbose", action="store_true", help="Modo debug")
    args = parser.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    # Ejecución concurrente en pool"""
                ))

            # Sembrar solución procedimental para Directivas Maestras del Agente
            cursor.execute("SELECT COUNT(*) FROM procedural_solutions WHERE category = 'core_agent_directives'")
            if cursor.fetchone()[0] == 0:
                cursor.execute("""
                    INSERT INTO procedural_solutions 
                    (category, phase, trigger_keywords, problem_description, solution_summary, working_snippet)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    "core_agent_directives",
                    "execution",
                    "autonomia ejecucion pausas dag herramientas aislamiento regresion stdlib testing concurrencia",
                    "Directivas Maestras de Ejecución y Arquitectura de JEV",
                    "1) Autonomía estricta: ejecutar todo el plan DAG de forma continua sin pausas intermedias ni transferir turnos al usuario. 2) Aislamiento de herramientas: procesar llamadas exclusivamente por backend sin esquemas JSON en texto. 3) Preservación de contexto: aplicar cambios incrementales sin eliminar lógica previa crítica. 4) Higiene stdlib: no usar pip con módulos estándar (asyncio, socket, threading, etc.). 5) Estándar senior: componentes thread-safe/cancellation-safe y testing simulado.",
                    """# 1. Autonomía: completar micro-tareas DAG secuencialmente sin pausas
# 2. Aislamiento: function calling de backend, cero JSONs crudos en chat
# 3. Preservación: modificaciones incrementales sin romper imports ni sync
# 4. Stdlib first: asyncio, socket, threading, dataclasses, argparse ya están en Python
# 5. Senior: @dataclass(slots=True), asyncio.Queue, threading.Condition, mock testing"""
                ))

            # Sembrar solución procedimental para Higiene de Dependencias
            cursor.execute("SELECT COUNT(*) FROM procedural_solutions WHERE category = 'dependency_hygiene'")
            if cursor.fetchone()[0] == 0:
                cursor.execute("""
                    INSERT INTO procedural_solutions 
                    (category, phase, trigger_keywords, problem_description, solution_summary, working_snippet)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    "dependency_hygiene",
                    "execution",
                    "pip install dependencias paquete modulo estandar python libreria",
                    "Higiene de dependencias y módulos estándar en Python",
                    "Validar siempre si los módulos pertenecen a la biblioteca estándar de Python antes de planificar o ejecutar pip install. Módulos como asyncio, socket, threading, dataclasses, argparse, pathlib, typing, json, sqlite3, hashlib nunca se instalan con pip.",
                    """# Módulos estándar preinstalados:
import asyncio
import socket
import threading
from dataclasses import dataclass
import argparse
from pathlib import Path
from typing import List, Dict, Any, Optional"""
                ))

            # Sembrar solución procedimental para Aislamiento de Runtime Viewport 3D y Three.js
            cursor.execute("SELECT COUNT(*) FROM procedural_solutions WHERE category = 'viewport_runtime_isolation'")
            if cursor.fetchone()[0] == 0:
                cursor.execute("""
                    INSERT INTO procedural_solutions 
                    (category, phase, trigger_keywords, problem_description, solution_summary, working_snippet)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    "viewport_runtime_isolation",
                    "execution",
                    "viewport threejs 3d escena canvas webgl arrow arrowhelper render",
                    "Aislamiento de runtime frontend vs backend y verificación estricta de API Three.js",
                    "1) Runtime Context Isolation: Elementos y scripts para el Viewport 3D se escriben exclusivamente en JavaScript nativo o esquemas JSON directos. Queda prohibido envolver JavaScript en Python o usar re.sub sobre código frontend. 2) Inyección sobre escena activa: No crear nuevos WebGLRenderer ni PerspectiveCamera; inyectar sobre window.scene/dynamicGroup. 3) API Check: THREE.ArrowGeometry NO existe; usar THREE.ArrowHelper(dir, origin, length, hex, headLength, headWidth) o cilindro+cono.",
                    """// Inyección directa sobre escena activa de Three.js (JavaScript nativo):
// Acceso a escena activa expuesta: window.scene o window.dynamicGroup
const dir = new THREE.Vector3(0, 1, 0).normalize();
const origin = new THREE.Vector3(0, 0, 0);
const length = 4.0;
const hex = 0x00f0ff;
const arrowHelper = new THREE.ArrowHelper(dir, origin, length, hex, 0.8, 0.5);
window.dynamicGroup.add(arrowHelper);"""
                ))

            # Migración: la ruta correcta para el Viewport 3D es el motor CAD real
            # (skill_cad_mesh / render_3d_scene). Sin esto, la memoria procedimental
            # empujaba al agente a improvisar JavaScript dentro de Python.
            cad_summary = (
                "Diseño 3D en JEV: 1) Piezas de ingeniería -> herramienta 'skill_cad_mesh' "
                "(model_type + parameters en mm): genera sólidos reales con taladros/booleanas, "
                "exporta OBJ/STL/GLB/GLTF y proyecta la malla en el Viewport. "
                "2) Escenas declarativas -> 'render_3d_scene' con JSON de 'elements' "
                "(BoxGeometry, SphereGeometry, CylinderGeometry, TorusGeometry, PlaneGeometry o "
                "BufferGeometry con positions/indices). 3) Animación -> 'execute_viewport_script' "
                "con JavaScript puro sobre scene/camera/renderer/dynamicGroup. "
                "Prohibido generar 3D con execute_python o write_file y prohibido duplicar "
                "WebGLRenderer/Scene/PerspectiveCamera."
            )
            cad_snippet = (
                "# Ruta correcta para diseño 3D (backend Python -> Viewport):\n"
                "skill_cad_mesh(model_type='spur_gear', parameters={'teeth': 20, 'pitch_radius': 12, "
                "'thickness': 4, 'bore_radius': 3}, color='#00f0ff')\n"
                "render_3d_scene(scene={'elements': [{'type': 'mesh', 'geometry': {'type': 'BoxGeometry', "
                "'parameters': {'width': 2, 'height': 2, 'depth': 2}}, 'material': {'color': '#00f0ff'}}]})\n"
                "execute_viewport_script(js_code='dynamicGroup.rotation.y += 0.01;')\n"
                "# PROHIBIDO: execute_python con sintaxis JS, o new THREE.WebGLRenderer/Scene."
            )
            cursor.execute(
                """
                UPDATE procedural_solutions
                SET solution_summary = ?, working_snippet = ?, trigger_keywords = ?
                WHERE category = 'viewport_runtime_isolation'
                """,
                (
                    cad_summary,
                    cad_snippet,
                    "viewport threejs 3d cad diseno diseño modelo escena malla mesh gltf stl solidworks pieza engranaje brida",
                ),
            )

            conn.commit()

        existing_lessons = self.get_all_lessons()
        if not existing_lessons:
            self.add_learned_lesson(
                category="Windows Apps",
                rule="Apertura de WhatsApp: usar Start-Process 'whatsapp:' o 'https://web.whatsapp.com'. NUNCA abrir ms-settings ni configuraciones. Chatear: Ctrl+F -> escribir contacto -> Enter -> escribir mensaje -> Enter.",
                context="Protocolo de apertura de apps y chat en Windows"
            )
            existing_lessons = self.get_all_lessons()

        if not any(l.get("category") == "Arquitectura de Software Profesional" for l in existing_lessons):
            self.add_learned_lesson(
                category="Arquitectura de Software Profesional",
                rule="Todo código generado debe cumplir estándares senior de arquitectura: 1) Arquitectura modular en memoria (prohibido IPC por subprocess y archivos JSON temporales; usar importaciones y RAM). 2) Concurrencia moderna con asyncio y control de recursos (asyncio.Semaphore para no saturar descriptores de socket del SO). 3) Modelos formales con @dataclass tipadas en lugar de dicts amorfos. 4) CLI robusto con argparse sin hardcoding. 5) Logging estructurado y excepciones específicas.",
                context="Estándares profesionales de producción para desarrollo y arquitectura de software"
            )
            existing_lessons = self.get_all_lessons()

        if not any(l.get("category") == "Directivas Maestras del Agente" for l in existing_lessons):
            self.add_learned_lesson(
                category="Directivas Maestras del Agente",
                rule="1) Autonomía estricta: ejecutar todo el plan DAG continuamente sin pausas intermedias ni preguntas ('¿Qué necesito hacer ahora?'). 2) Aislamiento de herramientas: procesar invocaciones exclusivamente vía backend; cero esquemas JSON en texto. 3) Preservación de contexto: aplicar modificaciones incrementales sin eliminar lógica crítica previa. 4) Higiene stdlib: verificar biblioteca estándar antes de pip install (asyncio, socket, threading no usan pip). 5) Estándar senior: thread-safe/cancellation-safe con slots=True y testing con reloj simulado.",
                context="Reglas base de ejecución continua, arquitectura y dependencias"
            )
            existing_lessons = self.get_all_lessons()

        if not any(l.get("category") == "Diseño 3D y CAD" for l in existing_lessons):
            self.add_learned_lesson(
                category="Diseño 3D y CAD",
                rule="Toda solicitud de diseño/modelado 3D empieza invocando 'skill_cad_mesh' (piezas paramétricas reales con taladros y booleanas, export OBJ/STL/GLB/GLTF) o 'render_3d_scene' (escenas JSON declarativas). La malla se proyecta automáticamente en el Viewport. NUNCA generes el 3D con 'execute_python'/'write_file' ni escribas JavaScript dentro de Python; 'execute_viewport_script' es solo para animar la escena activa.",
                context="Ruta canónica de generación de diseño 3D, CAD y fabricación digital"
            )
            existing_lessons = self.get_all_lessons()

        if not any(l.get("category") == "Aislamiento de Runtime Viewport 3D" for l in existing_lessons):
            self.add_learned_lesson(
                category="Aislamiento de Runtime Viewport 3D",
                rule="1) Runtime Context Isolation: Todo código para el Viewport 3D debe ser JavaScript o JSON nativo. Prohibido código Python con sintaxis JS o metaprogramación con re.sub. 2) Inyección en escena activa: Usar window.scene / dynamicGroup; no crear duplicados de THREE.WebGLRenderer ni THREE.Scene. 3) Three.js API Check: THREE.ArrowGeometry no existe (usar THREE.ArrowHelper o Cylinder+Cone).",
                context="Aislamiento de entornos frontend/backend y validación estricta de constructores Three.js"
            )
            existing_lessons = self.get_all_lessons()

    # --- MEMORIA DE TRABAJO (SHORT-TERM) ---

    @staticmethod
    def _hash_args(args: Dict[str, Any]) -> str:
        s = json.dumps(args, sort_keys=True)
        return hashlib.md5(s.encode("utf-8")).hexdigest()

    def record_step(self, session_id: str, step_num: int, tool_name: str, args: Dict[str, Any], success: bool) -> None:
        """Registra un paso ejecutado en la sesión actual."""
        args_hash = self._hash_args(args)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO short_term_steps (session_id, step_number, tool_name, args_hash, arguments_json, success) VALUES (?, ?, ?, ?, ?, ?)",
                (session_id, step_num, tool_name, args_hash, json.dumps(args), 1 if success else 0)
            )

    def is_step_duplicated(self, session_id: str, tool_name: str, args: Dict[str, Any]) -> bool:
        """Verifica si la misma herramienta con los mismos argumentos ya se ejecutó con éxito en esta sesión."""
        args_hash = self._hash_args(args)
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT COUNT(*) FROM short_term_steps WHERE session_id = ? AND tool_name = ? AND args_hash = ? AND success = 1",
                (session_id, tool_name, args_hash)
            )
            count = cur.fetchone()[0]
            return count > 0

    # --- MEMORIA PROCEDIMENTAL Y SEMÁNTICA (LONG-TERM) ---

    def save_solution(
        self,
        category: str,
        trigger_keywords: str,
        problem_description: str,
        solution_summary: str,
        working_snippet: Optional[str] = None,
        phase: str = "general"
    ) -> None:
        """Almacena una solución funcional para reutilizarla en el futuro, categorizada por fase operativa."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """INSERT INTO procedural_solutions 
                   (category, phase, trigger_keywords, problem_description, solution_summary, working_snippet) 
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (category, phase.lower(), trigger_keywords.lower(), problem_description, solution_summary, working_snippet or "")
            )

    def search_solutions(self, query: str, limit: int = 3, phase: Optional[str] = None) -> List[Dict[str, Any]]:
        """Busca soluciones probadas en la base de datos documental/SQLite con filtrado opcional por fase."""
        terms = [t.lower() for t in query.split() if len(t) > 3]
        if not terms:
            return []

        results = []
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            # Búsqueda ponderada por palabras clave y fase operativa
            for term in terms[:4]:
                if phase:
                    cur.execute(
                        """SELECT * FROM procedural_solutions 
                           WHERE (trigger_keywords LIKE ? OR problem_description LIKE ?)
                             AND (phase = ? OR phase = 'general')
                           ORDER BY times_reused DESC LIMIT ?""",
                        (f"%{term}%", f"%{term}%", phase.lower(), limit)
                    )
                else:
                    cur.execute(
                        """SELECT * FROM procedural_solutions 
                           WHERE trigger_keywords LIKE ? OR problem_description LIKE ? 
                           ORDER BY times_reused DESC LIMIT ?""",
                        (f"%{term}%", f"%{term}%", limit)
                    )
                for row in cur.fetchall():
                    d = dict(row)
                    if d not in results:
                        results.append(d)

        return results[:limit]

    def get_procedural_context_for_goal(self, goal: str) -> str:
        """Construye un bloque de inyección para el LLM con snippets y soluciones previas."""
        solutions = self.search_solutions(goal)
        if not solutions:
            return ""

        lines = ["\n--- BASE DE CONOCIMIENTO PROCEDIMENTAL (SOLUCIONES EXITOSAS PREVIAS) ---"]
        for s in solutions:
            lines.append(f"• Caso [{s['category']}]: {s['solution_summary']}")
            if s.get("working_snippet"):
                lines.append(f"  Snippet funcional comprobado:\n```python\n{s['working_snippet']}\n```")
        lines.append("-------------------------------------------------------------------------\n")
        return "\n".join(lines)

    # --- COMPATIBILIDAD CON SISTEMA DE LECCIONES Y EPISODIOS EXISTENTE ---

    def record_episode(self, task: str, success: bool, steps_count: int, tools_used: List[str], summary: str, learnings: Optional[str] = None) -> None:
        episode = {
            "timestamp": datetime.now().isoformat(),
            "task": task,
            "success": success,
            "steps_count": steps_count,
            "tools_used": list(set(tools_used)),
            "summary": summary,
            "learnings": learnings
        }
        with open(self.episodes_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(episode, ensure_ascii=False) + "\n")

    @staticmethod
    def _normalize_lesson_entry(item: Dict[str, Any]) -> Dict[str, Any]:
        """Estandariza un registro de lección al esquema formal mitigando envenenamiento."""
        lesson_text = (item.get("lesson") or item.get("rule") or "").strip()
        trigger_ctx = (item.get("trigger_context") or item.get("category") or item.get("context") or "General").strip()
        raw_id = str(item.get("id", "")).strip()

        if not raw_id or raw_id.isdigit():
            h = hashlib.sha256(f"{trigger_ctx.lower()}:{lesson_text.lower()}".encode("utf-8")).hexdigest()[:16]
            lesson_id = f"lesson_{h}"
        else:
            lesson_id = raw_id

        created_at = item.get("created_at") or item.get("timestamp") or datetime.now().isoformat()
        try:
            times_applied = int(item.get("times_applied", 0))
        except (ValueError, TypeError):
            times_applied = 0

        try:
            success_rate = float(item.get("success_rate", 1.0))
        except (ValueError, TypeError):
            success_rate = 1.0

        status = item.get("status", "active")
        if status not in ("active", "inactive", "deprecated"):
            status = "active"

        return {
            "id": lesson_id,
            "trigger_context": trigger_ctx,
            "lesson": lesson_text,
            "times_applied": times_applied,
            "success_rate": round(success_rate, 2),
            "created_at": created_at,
            "status": status,
            # Campos de retrocompatibilidad
            "category": trigger_ctx,
            "rule": lesson_text,
            "timestamp": created_at,
            "context": trigger_ctx
        }

    def get_all_lessons(self, include_inactive: bool = True) -> List[Dict[str, Any]]:
        """Recupera todas las lecciones aprendidas normalizadas al nuevo esquema."""
        if not self.lessons_file.exists():
            return []
        try:
            with open(self.lessons_file, "r", encoding="utf-8") as f:
                raw_data = json.load(f)
                if not isinstance(raw_data, list):
                    return []
                normalized = [self._normalize_lesson_entry(item) for item in raw_data if isinstance(item, dict)]
                if include_inactive:
                    return normalized
                return [l for l in normalized if l.get("status") == "active"]
        except Exception:
            return []

    def add_learned_lesson(
        self,
        category: Optional[str] = None,
        rule: Optional[str] = None,
        context: Optional[str] = None,
        trigger_context: Optional[str] = None,
        lesson: Optional[str] = None,
        times_applied: int = 0,
        success_rate: float = 1.0,
        status: str = "active"
    ) -> Dict[str, Any]:
        """
        Añade una lección aprendida aplicando deduplicación estricta y prevención de
        envenenamiento de contexto (Context Poisoning).
        """
        final_lesson = (lesson or rule or "").strip()
        final_trigger = (trigger_context or category or context or "General").strip()

        # Validación mínima de calidad
        if len(final_lesson) < 5:
            return {}

        existing_lessons = self.get_all_lessons(include_inactive=True)

        # 1. Deduplicación semántica/textual estricta: evitar acumular reglas idénticas
        norm_candidate = final_lesson.lower().strip()
        for existing in existing_lessons:
            if existing.get("lesson", "").lower().strip() == norm_candidate:
                # Regla ya existente: reforzar uso y actualizar timestamp sin duplicar
                existing["times_applied"] = existing.get("times_applied", 0) + 1
                existing["created_at"] = datetime.now().isoformat()
                existing["status"] = "active"
                self._save_lessons(existing_lessons)
                return existing

        # 2. Generar identificador único hash
        h = hashlib.sha256(f"{final_trigger.lower()}:{norm_candidate}".encode("utf-8")).hexdigest()[:16]
        new_entry = {
            "id": f"lesson_{h}",
            "trigger_context": final_trigger,
            "lesson": final_lesson,
            "times_applied": times_applied,
            "success_rate": round(success_rate, 2),
            "created_at": datetime.now().isoformat(),
            "status": status,
            # Retrocompatibilidad
            "category": final_trigger,
            "rule": final_lesson,
            "timestamp": datetime.now().isoformat(),
            "context": context or final_trigger
        }
        existing_lessons.append(new_entry)
        self._save_lessons(existing_lessons)
        return new_entry

    def update_lesson_outcome(self, lesson_id_or_rule: str, task_success: bool) -> None:
        """
        Actualiza el rendimiento histórico y TTL de una regla.
        Si la tasa de éxito cae por debajo del 40% tras múltiples aplicaciones, se desactiva.
        """
        lessons = self.get_all_lessons(include_inactive=True)
        updated = False
        for l in lessons:
            if l.get("id") == lesson_id_or_rule or l.get("lesson") == lesson_id_or_rule or l.get("rule") == lesson_id_or_rule:
                n = l.get("times_applied", 0) + 1
                curr_rate = l.get("success_rate", 1.0)
                outcome = 1.0 if task_success else 0.0
                new_rate = round(((curr_rate * (n - 1)) + outcome) / n, 2)
                l["times_applied"] = n
                l["success_rate"] = new_rate

                # Desactivación por bajo rendimiento (mitigación de contexto envenenado)
                if n >= 3 and new_rate < 0.4:
                    l["status"] = "inactive"
                updated = True
                break

        if updated:
            self._save_lessons(lessons)

    def _save_lessons(self, lessons: List[Dict[str, Any]]) -> None:
        """Guarda la lista normalizada de lecciones en disco garantizando formato limpio."""
        # Limpiar campos redundantemente duplicados para almacenamiento canónico
        clean_list = []
        for l in lessons:
            clean_list.append({
                "id": l.get("id"),
                "trigger_context": l.get("trigger_context"),
                "lesson": l.get("lesson"),
                "times_applied": l.get("times_applied", 0),
                "success_rate": l.get("success_rate", 1.0),
                "created_at": l.get("created_at"),
                "status": l.get("status", "active")
            })
        with open(self.lessons_file, "w", encoding="utf-8") as f:
            json.dump(clean_list, f, indent=2, ensure_ascii=False)

    def get_lessons_prompt(self, max_lessons: int = 5) -> str:
        """
        Genera el bloque de lecciones para el System Prompt.
        Solo inyecta reglas con status='active', priorizando por mayor tasa de éxito
        y limitando la cantidad para evitar sobrecarga o envenenamiento de contexto.
        """
        active_lessons = [
            l for l in self.get_all_lessons(include_inactive=False)
            if l.get("status") == "active" and l.get("success_rate", 1.0) >= 0.4
        ]
        if not active_lessons:
            return ""

        # Ordenar por tasa de éxito descendente y aplicaciones
        active_lessons.sort(key=lambda x: (x.get("success_rate", 1.0), x.get("times_applied", 0)), reverse=True)
        top_lessons = active_lessons[:max_lessons]

        lines = ["\n--- REGLAS APRENDIDAS PREVIAMENTE (FILTRADAS POR EFICACIA) ---"]
        for idx, item in enumerate(top_lessons, 1):
            ctx = item.get("trigger_context") or item.get("category", "General")
            rule = item.get("lesson") or item.get("rule", "")
            rate = int(item.get("success_rate", 1.0) * 100)
            lines.append(f"{idx}. [{ctx}] (Eficacia: {rate}%): {rule}")
        lines.append("---------------------------------------------------------------\n")
        return "\n".join(lines)


# Alias para compatibilidad total con código existente
AgentMemory = HierarchicalMemory
