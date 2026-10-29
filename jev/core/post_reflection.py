"""
Submódulo de Autocrítica y Corrección Post-Ejecución (Post-Execution Self-Reflection).
Implementa:
1. Audit & Critique: Evaluación estricta de restricciones, sintaxis y detección de placeholders.
2. Tool Gap Analysis: Identificación de herramientas faltantes para optimizar futuras tareas.
"""
from typing import Dict, Any, List, Tuple, Optional
import ast
import re
from dataclasses import dataclass, field

from jev.core.llm_client import LocalLLMClient, LLMResponse
from jev.skills.skill_code_linter.handler import lint_python_code


@dataclass(slots=True)
class AuditResult:
    passed: bool
    issues: List[str] = field(default_factory=list)
    critique: str = ""
    corrected_answer: Optional[str] = None
    corrected_files: List[Tuple[str, str]] = field(default_factory=list)


@dataclass(slots=True)
class ToolGapReport:
    has_gap: bool = False
    gap_name: Optional[str] = None
    reason: Optional[str] = None
    proposed_solution: Optional[str] = None
    code_snippet: Optional[str] = None


class PostExecutionAuditEngine:
    """Motor de auditoría ineludible post-ejecución antes de cerrar cualquier tarea."""

    VALID_THREE_CLASSES = {
        # Geometrías oficiales estándar
        "BoxGeometry", "SphereGeometry", "CylinderGeometry", "TorusGeometry", "PlaneGeometry",
        "ConeGeometry", "RingGeometry", "CircleGeometry", "DodecahedronGeometry", "IcosahedronGeometry",
        "OctahedronGeometry", "TetrahedronGeometry", "TorusKnotGeometry", "BufferGeometry",
        "EdgesGeometry", "WireframeGeometry", "LatheGeometry", "ExtrudeGeometry", "ShapeGeometry",
        "PolyhedronGeometry", "TubeGeometry",
        # Materiales
        "MeshBasicMaterial", "MeshStandardMaterial", "MeshPhysicalMaterial", "MeshLambertMaterial",
        "MeshPhongMaterial", "MeshToonMaterial", "MeshNormalMaterial", "MeshDepthMaterial",
        "LineBasicMaterial", "LineDashedMaterial", "PointsMaterial", "ShaderMaterial", "RawShaderMaterial",
        "SpriteMaterial", "ShadowMaterial",
        # Luces
        "AmbientLight", "DirectionalLight", "PointLight", "SpotLight", "HemisphereLight", "RectAreaLight", "Light",
        # Helpers oficiales
        "ArrowHelper", "AxesHelper", "GridHelper", "BoxHelper", "CameraHelper", "DirectionalLightHelper",
        "PointLightHelper", "SpotLightHelper", "PolarGridHelper", "PlaneHelper",
        # Núcleo y Matemáticas
        "Vector2", "Vector3", "Vector4", "Matrix3", "Matrix4", "Euler", "Quaternion", "Color",
        "Raycaster", "Group", "Scene", "Mesh", "Line", "LineSegments", "LineLoop", "Points",
        "Sprite", "Object3D", "PerspectiveCamera", "OrthographicCamera", "WebGLRenderer",
        "Texture", "CanvasTexture", "Clock", "Fog", "FogExp2"
    }

    KNOWN_HALLUCINATIONS = {
        "ArrowGeometry": "Usa 'new THREE.ArrowHelper(dir, origin, length, hex, headLength, headWidth)' o una geometría compuesta (CylinderGeometry para el asta + ConeGeometry para la punta).",
        "CubeGeometry": "Constructor obsoleto removido en Three.js moderno; usa 'new THREE.BoxGeometry'.",
        "TriangleGeometry": "No existe en Three.js; usa 'new THREE.BufferGeometry' con vértices personalizados.",
        "StarGeometry": "No existe en la especificación estándar; usa 'new THREE.ShapeGeometry' con un path poligonal.",
        "PolygonGeometry": "No existe; usa 'new THREE.ShapeGeometry'.",
        "PyramidGeometry": "No existe; usa 'new THREE.ConeGeometry(radius, height, 4)'."
    }

    def __init__(self, llm_client: Optional[LocalLLMClient] = None):
        self.llm = llm_client

    def audit_and_critique(
        self,
        user_goal: str,
        final_answer: str,
        written_files: Optional[List[Tuple[str, str]]] = None,
        tools_used: Optional[List[str]] = None
    ) -> AuditResult:
        """
        Audita internamente la respuesta y el código contra el prompt original:
        a) Pre-flight Syntax & Language Bleeding (Aislamiento estricto de capas Python vs JS).
        b) Inyección sobre escena activa (Prohibido instanciar nuevos WebGLRenderer / escenas desconectadas).
        c) Verificación estática de APIs de Three.js (Detección de constructores alucinados como ArrowGeometry).
        d) Detección de código incompleto o placeholders ('pass', '...', 'TODO').
        e) Cumplimiento de restricciones técnicas impuestas.
        """
        written_files = written_files or []
        tools_used = tools_used or []
        issues = []
        user_goal_lower = user_goal.lower()

        # 1. Pre-flight Syntax & Language Bleeding Check sobre bloques de Markdown
        code_blocks = re.findall(r"```([a-zA-Z0-9_-]*)\r?\n([\s\S]*?)```", final_answer)

        for idx, (lang, block) in enumerate(code_blocks):
            lang_clean = lang.strip().lower()

            # Caso A: Bloque declarado como Python (o por defecto si tiene def/import)
            if lang_clean in ["python", "py"] or (not lang_clean and ("def " in block or "import " in block)):
                # Detectar contaminación cruzada con JavaScript (Language Bleeding)
                js_patterns = [
                    (r"\bnew\s+THREE\.", "instanciación nativa de Three.js ('new THREE.')"),
                    (r"\bconst\s+[a-zA-Z_$]", "declaración de variable JavaScript ('const')"),
                    (r"\blet\s+[a-zA-Z_$]", "declaración de variable JavaScript ('let')"),
                    (r"\bfunction\s*\([^\)]*\)\s*\{", "función nativa JavaScript ('function() {')"),
                    (r"\bdocument\.", "acceso al DOM del navegador ('document.')"),
                    (r"\bwindow\.", "acceso a objeto de navegador ('window.')"),
                    (r"\bconsole\.log\(", "llamada a consola JavaScript ('console.log')"),
                    (r"=>", "función flecha de JavaScript ('=>')")
                ]
                for p_regex, p_desc in js_patterns:
                    if re.search(p_regex, block):
                        issues.append(
                            f"[Snippet #{idx+1}] Contaminación cruzada de lenguajes (Language Bleeding): "
                            f"Se detectó {p_desc} dentro de un bloque Python. "
                            "Para el Viewport 3D genera JavaScript puro en bloque ```javascript o un esquema JSON Three.js."
                        )
                        break

                # Detectar sobreingeniería por metaprogramación innecesaria (wrappers con re.sub o print para frontend)
                if re.search(r"\bre\.sub\(", block) and any(w in block.lower() for w in ["three", "scene", "script", "javascript", "js", "html", "viewport"]):
                    issues.append(
                        f"[Snippet #{idx+1}] Sobreingeniería innecesaria: Prohibido manipular código frontend con scripts de "
                        "Python mediante 're.sub' o wrappers de impresión. Despacha directamente JavaScript puro o JSON Three.js."
                    )

                # Validar sintaxis estricta de Python con ast.parse si no hay bleeding
                lint_res = lint_python_code(block, file_path=f"chat_snippet_{idx+1}.py", strict_placeholders=True)
                if not lint_res["valid"]:
                    for err in lint_res["errors"]:
                        issues.append(f"[Snippet #{idx+1}] Python AST: Línea {err.get('line', '?')}: {err.get('message', 'Error')}")

            # Caso B: Bloque declarado como JavaScript / Three.js
            elif lang_clean in ["javascript", "js", "three", "threejs"]:
                # Detectar Python bleed en JavaScript
                if re.search(r"\bdef\s+[a-zA-Z0-9_]+\s*\(", block) or re.search(r"\bimport\s+sys\b", block) or re.search(r"\belif\b", block):
                    issues.append(
                        f"[Snippet #{idx+1}] Contaminación cruzada: Se detectaron sentencias de Python dentro de un bloque JavaScript."
                    )

                # Detectar duplicación de renderers o escenas desconectadas (No Duplicate Renderers)
                if re.search(r"\bnew\s+THREE\.WebGLRenderer\b", block):
                    issues.append(
                        f"[Snippet #{idx+1}] Duplicación de runtime (No Duplicate Renderers): Prohibido instanciar 'new THREE.WebGLRenderer()'. "
                        "El Viewport 3D ya expone un lienzo montado; inyecta los objetos directamente sobre la escena activa (scene o dynamicGroup)."
                    )
                if re.search(r"\bnew\s+THREE\.PerspectiveCamera\b", block):
                    issues.append(
                        f"[Snippet #{idx+1}] Duplicación de runtime: Prohibido instanciar 'new THREE.PerspectiveCamera()'. "
                        "El visor ya cuenta con una cámara orbital montada (camera / window.camera)."
                    )
                if re.search(r"\bnew\s+THREE\.Scene\b", block):
                    issues.append(
                        f"[Snippet #{idx+1}] Desconexión de escena: Prohibido crear una nueva escena desconectada ('new THREE.Scene()'). "
                        "Añade mallas directamente a la escena activa existente ('scene.add(...)', 'dynamicGroup.add(...)')."
                    )

                # Verificación estática de APIs de Three.js contra constructores alucinados
                three_instances = re.findall(r"\bnew\s+THREE\.([a-zA-Z0-9_]+)\b", block)
                for ctor in three_instances:
                    if ctor in self.KNOWN_HALLUCINATIONS:
                        issues.append(
                            f"[Snippet #{idx+1}] Alucinación de API Three.js: 'THREE.{ctor}' no existe en la especificación oficial. "
                            f"{self.KNOWN_HALLUCINATIONS[ctor]}"
                        )
                    elif ctor not in self.VALID_THREE_CLASSES:
                        issues.append(
                            f"[Snippet #{idx+1}] Alucinación de API Three.js: 'THREE.{ctor}' no pertenece a la especificación oficial de Three.js."
                        )

        # 2. Auditoría de archivos generados en disco
        for path_str, code_content in written_files:
            if path_str.endswith(".py"):
                # Verificar Language Bleeding en archivos Python en disco
                if re.search(r"\bnew\s+THREE\.", code_content) or re.search(r"\bconst\s+[a-zA-Z_$]", code_content):
                    issues.append(
                        f"[{path_str}] Contaminación cruzada: Se detectaron sentencias nativas de JavaScript dentro de un archivo Python."
                    )
                if re.search(r"\bre\.sub\(", code_content) and any(w in code_content.lower() for w in ["three", "scene", "javascript"]):
                    issues.append(
                        f"[{path_str}] Sobreingeniería por metaprogramación: Prohibido usar re.sub para generar código del visor."
                    )
                lint_res = lint_python_code(code_content, file_path=path_str, strict_placeholders=True)
                if not lint_res["valid"]:
                    for err in lint_res["errors"]:
                        issues.append(f"[{path_str}] Línea {err.get('line', '?')}: {err.get('message', 'Error')}")

        # 3. Verificación de restricciones técnicas del prompt original
        technical_keywords = ["asyncio", "concurrencia", "json", "dataclass", "argparse", "three", "3d", "socket"]
        for kw in technical_keywords:
            if kw in user_goal_lower:
                combined_text = (final_answer + " " + " ".join([c for _, c in written_files])).lower()
                if kw not in combined_text:
                    issues.append(f"Restricción técnica '{kw}' solicitada en la meta pero ausente en la solución.")

        if not issues:
            return AuditResult(
                passed=True,
                issues=[],
                critique="Auditoría post-ejecución aprobada: código sintácticamente válido, runtime aislado sin alucinaciones de API ni placeholders."
            )

        critique_summary = "\n".join([f"• {issue}" for issue in issues])

        # 4. Autocorrección determinista inicial (heurística)
        corrected_answer = final_answer

        # Heurística A: Reemplazar constructores Three.js alucinados en el texto
        if "THREE.ArrowGeometry" in corrected_answer:
            corrected_answer = re.sub(
                r"new\s+THREE\.ArrowGeometry\s*\((.*?)\)",
                r"new THREE.ArrowHelper(new THREE.Vector3(0, 1, 0), new THREE.Vector3(0, 0, 0), 3, 0x00f0ff, 0.6, 0.3)",
                corrected_answer
            )
            corrected_answer = corrected_answer.replace("THREE.ArrowGeometry", "THREE.ArrowHelper")

        if "THREE.CubeGeometry" in corrected_answer:
            corrected_answer = corrected_answer.replace("THREE.CubeGeometry", "THREE.BoxGeometry")

        # Heurística B: Si un bloque fue marcado como python pero es 100% JavaScript (tiene new THREE. o const), corregir tag
        def fix_code_block_tag(match):
            lang_tag = match.group(1).strip().lower()
            code_text = match.group(2)
            if lang_tag in ["python", "py", ""] and (("new THREE." in code_text or "const " in code_text) and "def " not in code_text and "import " not in code_text):
                return f"```javascript\n{code_text}```"
            return match.group(0)

        corrected_answer = re.sub(r"```([a-zA-Z0-9_-]*)\r?\n([\s\S]*?)```", fix_code_block_tag, corrected_answer)

        # Si cambió determinísticamente y se corrigió
        if corrected_answer == final_answer:
            corrected_answer = None

        # 5. Intento de autocorrección asistida por LLM si está disponible
        if self.llm:
            try:
                fix_prompt = (
                    f"OBJETIVO ORIGINAL: {user_goal}\n\n"
                    f"FALLOS DETECTADOS EN AUDITORÍA POST-EJECUCIÓN:\n{critique_summary}\n\n"
                    f"SOLUCIÓN ACTUAL QUE DEBE SER CORREGIDA:\n{corrected_answer or final_answer}\n\n"
                    "DIRECTIVAS ESTRICTAS DE CORRECCIÓN:\n"
                    "1. AISLAMIENTO DE RUNTIME: Si el código es para el Viewport 3D o Three.js, genera ÚNICAMENTE JavaScript puro en bloque ```javascript o JSON Three.js. Queda TERMINANTEMENTE PROHIBIDO mezclar JavaScript en Python o envolverlo en scripts con print() o re.sub.\n"
                    "2. ESCENA ACTIVA: No instancies new THREE.WebGLRenderer() ni new THREE.Scene(). Agrega objetos directamente a la escena activa existente (scene.add(...) o dynamicGroup.add(...)).\n"
                    "3. ESPECIFICACIÓN THREE.JS: Prohibido 'THREE.ArrowGeometry' (usa THREE.ArrowHelper o CylinderGeometry + ConeGeometry). Prohibido 'THREE.CubeGeometry' (usa THREE.BoxGeometry).\n"
                    "Devuelve la solución profesional completa y corregida lista para producción."
                )
                res: LLMResponse = self.llm.chat(
                    messages=[
                        {"role": "system", "content": "Eres el Submódulo de Autocorrección y Perfeccionamiento de JEV."},
                        {"role": "user", "content": fix_prompt}
                    ],
                    tools=[]
                )
                if res.content and len(res.content.strip()) > 30:
                    corrected_answer = res.content.strip()
            except Exception:
                pass

        return AuditResult(
            passed=False,
            issues=issues,
            critique=critique_summary,
            corrected_answer=corrected_answer
        )

    def tool_gap_analysis(
        self,
        user_goal: str,
        tools_used: List[str],
        success: bool
    ) -> ToolGapReport:
        """
        Evalúa: '¿Qué herramienta o script auxiliar me faltó para resolver esto de forma más rápida, segura o precisa?'
        Si identifica una carencia recurrente, estructura una propuesta para registrarla como utilidad o habilidad.
        """
        goal_lower = user_goal.lower()

        # Análisis heurístico de brechas operativas
        if any(w in goal_lower for w in ["dns", "latencia", "ping", "rtt"]) and "skill_net_diagnostics" not in tools_used:
            return ToolGapReport(
                has_gap=True,
                gap_name="skill_net_diagnostics",
                reason="Operación de red resuelta de forma manual sin utilizar la habilidad nativa de diagnóstico RTT.",
                proposed_solution="Emplear 'skill_net_diagnostics' para mediciones directas de latencia TCP y resolución DNS.",
                code_snippet="from jev.skills.skill_net_diagnostics.handler import handle as net_diag\nres = net_diag(action='tcp_ping', target='...')\n"
            )

        if any(w in goal_lower for w in ["3d", "mesh", "malla", "geometria"]) and "skill_mesh_generator" not in tools_used:
            return ToolGapReport(
                has_gap=True,
                gap_name="skill_mesh_generator",
                reason="Generación de geometría 3D sin invocar el generador procedural estándar Three.js.",
                proposed_solution="Aprovechar 'skill_mesh_generator' para instanciar mallas Three.js JSON.",
                code_snippet="from jev.skills.skill_mesh_generator.handler import handle as mesh_gen\nres = mesh_gen(shape='composite_scene')\n"
            )

        if any(w in goal_lower for w in ["linter", "ast", "validar codigo"]) and "skill_code_linter" not in tools_used:
            return ToolGapReport(
                has_gap=True,
                gap_name="skill_code_linter",
                reason="Inspección de código realizada sin auditoría estática formal con ast.parse.",
                proposed_solution="Utilizar 'skill_code_linter' para verificación formal de sintaxis y placeholders.",
                code_snippet="from jev.skills.skill_code_linter.handler import handle as linter\nres = linter(code='...')\n"
            )

        # Si una tarea falló repetidamente
        if not success:
            return ToolGapReport(
                has_gap=True,
                gap_name=f"auto_helper_for_{goal_lower[:25].replace(' ', '_')}",
                reason=f"La tarea '{user_goal[:60]}' no pudo converger con las herramientas disponibles.",
                proposed_solution="Sintetizar una herramienta especializada que descomponga los pasos con reintentos guiados.",
                code_snippet="# Helper especializado pendiente de compilación"
            )

        return ToolGapReport(has_gap=False)
