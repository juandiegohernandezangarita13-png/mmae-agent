"""
Motor cognitivo inspirado en OpenMythos (Claude Mythos Theoretical Reconstruction).
Implementa:
1. Razonamiento recurrente con inyección de anclaje (Recurrent-Depth Transformer concept)
2. Mecanismo de parada adaptativa ACT (Adaptive Computation Time) para evitar sobrepensar (overthinking)
3. Enrutador MoAE (Mixture of Agent Experts): Expertos compartidos siempre activos + expertos enrutados top-K.
"""
from typing import List, Dict, Any, Optional, Tuple, Set
import re
import math


class MoAERouter:
    """
    Enrutador de Mixture-of-Agent-Experts (MoAE).
    Inspirado en la arquitectura DeepSeekMoE/OpenMythos:
    - Expertos compartidos (Shared Experts): Siempre activos en cada llamada para tareas universales.
    - Expertos enrutados (Routed Experts): Activados dinámicamente según la afinidad semántica de la meta.
    """

    # Expertos Compartidos: Fundamentales para cualquier ejecución
    SHARED_EXPERT_TOOLS: Set[str] = {
        "read_file",
        "write_file",
        "list_dir",
        "execute_command",
        "execute_python"
    }

    # Grupos de Expertos Enrutados por Dominio
    EXPERT_CLUSTERS: Dict[str, Dict[str, Any]] = {
        "web_research": {
            "name": "Web Research & Extraction",
            "keywords": ["buscar", "web", "internet", "google", "noticias", "documentacion", "url", "pagina", "http", "online", "investigar", "search"],
            "tools": ["search_web", "fetch_webpage"]
        },
        "github_assimilator": {
            "name": "GitHub Intelligence & Code Assimilation",
            "keywords": ["github", "repo", "repositorio", "clonar", "asimilar", "libreria", "git", "open-source", "fork", "commit"],
            "tools": ["search_github_repos", "inspect_github_repo", "clone_github_repo", "assimilate_github_library"]
        },
        "computer_use": {
            "name": "Computer & Screen Interaction",
            "keywords": ["pantalla", "screenshot", "captura", "click", "raton", "mouse", "teclado", "escribir", "interfaz", "ventana", "app", "boton"],
            "tools": ["take_screenshot", "get_screen_info", "mouse_move", "mouse_click", "keyboard_type", "keyboard_press"]
        },
        "system_environment": {
            "name": "System Environment & Package Management",
            "keywords": ["instalar", "pip", "paquete", "entorno", "sistema", "hardware", "gpu", "cuda", "cpu", "memoria", "ram", "specs"],
            "tools": ["get_system_environment", "install_python_package"]
        },
        "neural_mythos": {
            "name": "OpenMythos Neural Engine & GPU Inference",
            "keywords": ["mythos", "openmythos", "neural", "tensor", "gpu", "modelo neuronal", "recurrente", "rdt", "act", "spectral", "cuda", "bench"],
            "tools": ["run_open_mythos"]
        },
        "code_crafting": {
            "name": "Code Architecture, Repos & Patching",
            "keywords": ["codigo", "refactorizar", "parchear", "bug", "error", "sintaxis", "funcion", "clase", "test", "prueba", "script", "repositorio", "rama", "diff"],
            "tools": ["patch_file", "create_custom_tool", "skill_repo_planner", "skill_sdlc_senior", "skill_code_linter", "skill_claude_code"]
        },
        "video_production": {
            "name": "HyperFrames Video Production",
            "keywords": ["video", "render", "animacion", "mp4", "hyperframes", "reel", "short", "tiktok", "clip", "presentacion", "motion"],
            "tools": ["render_hyperframes_video", "skill_video_creator"]
        },
        # --- Diseño 3D / CAD / fabricación digital -------------------------
        # Sin este cluster, el router MoAE ocultaba skill_cad_mesh y el agente
        # intentaba improvisar JS dentro de Python para "diseñar en 3D".
        "3d_design": {
            "name": "3D CAD Design & Parametric Modeling",
            "keywords": [
                "3d", "3-d", "cad", "malla", "mesh", "gltf", "glb", "stl", "obj",
                "engranaje", "gear", "brida", "flange", "resorte", "spring",
                "polea", "pulley", "rodamiento", "bearing", "tuerca", "perno",
                "tornillo", "carcasa", "escuadra", "soporte", "cremallera",
                "parametric", "paramétric", "parametrico", "geometria", "geometría",
                "modelado", "modelar", "modelo 3d", "modelo tridimensional",
                "diseno 3d", "diseño 3d", "disenar", "diseñar", "pieza",
                "mecanic", "mecánic", "prototipo", "volumetric", "viewport",
                "escena 3d", "imprimir en 3d", "impresion 3d", "stl",
            ],
            "tools": [
                "skill_cad_mesh", "skill_mesh_generator",
                "render_3d_scene", "execute_viewport_script",
            ]
        },
        "visual_synthesis": {
            "name": "Image Generation & Multimodal Vision",
            "keywords": ["imagen", "foto", "ilustracion", "ilustración", "dibujo", "logo", "logotipo",
                         "poster", "cartel", "banner", "icono", "avatar", "render visual", "grafico",
                         "analiza la imagen", "describe la imagen", "ocr", "reconoce"],
            "tools": ["skill_image_generator", "skill_vision_recognizer"]
        },
        "web_design": {
            "name": "Web UI/UX Design & Browser Automation",
            "keywords": ["web", "html", "css", "landing", "pagina web", "página web", "sitio", "frontend",
                         "ui", "ux", "interfaz web", "react", "tailwind", "dashboard", "navegador",
                         "browser", "web design", "diseño web"],
            "tools": ["skill_web_builder", "skill_web_design_pro", "skill_browser_operator"]
        },
        "engineering_analysis": {
            "name": "Scientific Simulation, Networks & Security",
            "keywords": ["cfd", "fluido", "simulacion", "simulación", "cuantico", "cuántico", "quantum",
                         "base de datos", "sql", "consulta", "red", "ping", "wifi", "adsb", "avion",
                         "meshtastic", "telemetria", "fotogrametria", "fotogrametría", "vision", "camara",
                         "criptografia", "criptografía", "hash", "boveda", "permutacion", "combinatoria",
                         "osint", "camerina", "camarilla"],
            "tools": [
                "fluid_dynamics_pde_solver", "skill_quantum_circuit_sim",
                "skill_database_query_optimizer", "skill_net_diagnostics",
                "network_presence_sensing", "skill_cryptographic_vault",
                "skill_rf_adsb_tracker", "skill_meshtastic_gateway",
                "skill_openpilot_telemetry", "skill_odm_photogrammetry",
                "skill_frigate_vision_bridge", "skill_combinatorial_analytics",
                "skill_osint_investigator", "offline_vault", "safe_sandbox_runner",
            ]
        }
    }

    def route_tools(
        self,
        goal: str,
        all_tools: List[Dict[str, Any]],
        top_k: int = 3
    ) -> Tuple[List[Dict[str, Any]], List[str]]:
        """
        Selecciona las herramientas activas combinando los expertos compartidos
        con los top-K expertos enrutados de mayor afinidad.

        Retorna:
            (filtered_tools, active_expert_names)
        """
        if not all_tools:
            return [], []

        goal_lower = (goal or "").lower()
        tool_map = {t.get("function", {}).get("name", ""): t for t in all_tools}

        # 1. Puntuar cada cluster de expertos por afinidad semántica.
        #    Las palabras clave cortas ("3d", "cad", "ui") se evalúan con límites de
        #    palabra para no activar clusters por coincidencias accidentales.
        scores: Dict[str, float] = {}
        for cluster_id, cluster_data in self.EXPERT_CLUSTERS.items():
            score = 0.0
            for kw in cluster_data["keywords"]:
                if len(kw) <= 3:
                    if re.search(r"(?<![\w-])" + re.escape(kw) + r"(?![\w-])", goal_lower):
                        score += 1.0
                elif kw in goal_lower:
                    score += 1.0
            scores[cluster_id] = score

        # 2. Seleccionar los top-K clusters con afinidad real
        sorted_clusters = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        top_clusters = [cid for cid, s in sorted_clusters if s > 0][:top_k]

        if not top_clusters:
            # Fallback equilibrado: si la meta es genérica, habilitar las herramientas estándar
            top_clusters = ["web_research", "system_environment"]

        # 3. Recolectar nombres de herramientas activas
        active_tool_names: Set[str] = set(self.SHARED_EXPERT_TOOLS)
        active_expert_names: List[str] = ["Core Compartido (Shared Experts)"]

        for cid in top_clusters:
            cluster_info = self.EXPERT_CLUSTERS[cid]
            active_expert_names.append(cluster_info["name"])
            for t_name in cluster_info["tools"]:
                active_tool_names.add(t_name)

        # 4. Salvaguarda: si el usuario nombra una herramienta explícitamente
        #    ("usa skill_cad_mesh"), habilitarla aunque ningún cluster la cubra.
        explicitly_named: List[str] = []
        for t_name in tool_map:
            if t_name and t_name.lower() in goal_lower:
                active_tool_names.add(t_name)
                explicitly_named.append(t_name)
        if explicitly_named:
            active_expert_names.append("Herramientas invocadas explícitamente")

        # 5. Filtrar la lista de herramientas en formato OpenAI
        filtered = [t for t in all_tools if t.get("function", {}).get("name") in active_tool_names]

        # Si por alguna razón el filtrado resulta vacío, devolver todo como salvaguarda
        if not filtered:
            return all_tools, ["Todos los Expertos (Fallback)"]

        return filtered, active_expert_names


class ACTState:
    """Estado y métricas de parada adaptativa (Adaptive Computation Time)."""
    def __init__(self, max_loops: int = 4, threshold: float = 0.85):
        self.max_loops = max_loops
        self.threshold = threshold
        self.current_loop = 0
        self.cumulative_halt_prob = 0.0
        self.halted_early = False
        self.reasoning_trace: List[Dict[str, Any]] = []

    def update(self, loop_idx: int, step_confidence: float, delta_change: float, thoughts: str) -> bool:
        """
        Actualiza el estado de acumulación ACT.
        step_confidence: probabilidad de convergencia [0, 1] en este paso.
        delta_change: magnitud del cambio respecto al paso anterior.
        Retorna True si debe detenerse (halted).
        """
        self.current_loop = loop_idx + 1

        # Probabilidad de parada proporcional a la confianza y inversamente proporcional a la novedad delta
        # p_halt = confidence * (1.0 - delta_change)
        p_halt = max(0.05, min(0.99, step_confidence * (1.0 - min(delta_change, 0.9))))
        self.cumulative_halt_prob += p_halt * (1.0 - self.cumulative_halt_prob)

        self.reasoning_trace.append({
            "loop": self.current_loop,
            "p_halt_step": round(p_halt, 3),
            "cum_halt": round(self.cumulative_halt_prob, 3),
            "delta": round(delta_change, 3),
            "summary": thoughts
        })

        if self.cumulative_halt_prob >= self.threshold or self.current_loop >= self.max_loops:
            self.halted_early = (self.current_loop < self.max_loops)
            return True

        return False


class MythosCognitiveEngine:
    """
    Motor Cognitivo inspirado en OpenMythos.
    Aplica:
    - Bucle de pensamiento recurrente con inyección de anclaje (Anchor Injection).
    - Prevención de 'overthinking' mediante parada adaptativa ACT.
    - Enrutamiento dinámico de herramientas mediante MoAE (Mixture of Agent Experts).
    """

    def __init__(self, max_loops: int = 4, act_threshold: float = 0.85):
        self.max_loops = max_loops
        self.act_threshold = act_threshold
        self.router = MoAERouter()

    def assess_complexity(self, goal: str) -> int:
        """
        Evalúa la complejidad intrínseca de la meta del usuario de 1 a 5.
        Determina el número máximo de bucles recurrentes requeridos.
        """
        text = goal.lower()
        score = 1

        # Indicadores de complejidad multi-hop
        multi_hop_indicators = [
            "crear", "desarrollar", "implementar", "analizar", "investigar",
            "asimil", "comparar", "optimizar", "entrenar", "integrar", "solucionar"
        ]
        for ind in multi_hop_indicators:
            if ind in text:
                score += 1

        # Indicadores de longitud o especificaciones múltiples
        if len(goal) > 100:
            score += 1
        if " y " in text or " ademas " in text or " además " in text or " luego " in text:
            score += 1

        return min(self.max_loops, max(1, score))

    # Diferenciación funcional inspirada en loop_index_embedding de OpenMythos
    LOOP_PHASES: Dict[int, Dict[str, str]] = {
        0: {
            "name": "Exploración Semántica y Descomposición",
            "focus": "Delimitar objetivo primordial, entidades clave y dependencias necesarias"
        },
        1: {
            "name": "Verificación de Restricciones y Sandbox",
            "focus": "Analizar restricciones del sistema, sintaxis de herramientas y límites seguros"
        },
        2: {
            "name": "Optimización de Rutas y Post-condiciones",
            "focus": "Enrutar herramientas expertas (MoAE) y diseñar criterios de validación empírica"
        },
        3: {
            "name": "Consolidación y Síntesis de Convergencia",
            "focus": "Verificar completitud del plan sin sobrepensar y consolidar estrategia"
        }
    }

    def recurrent_thinking_loop(self, goal: str) -> Tuple[str, ACTState]:
        """
        Ejecuta el bucle de razonamiento recurrente con inyección de anclaje,
        diferenciación por índice de bucle (RoPE-like loop index phases) y parada ACT.
        - e (Ancla): La meta original del usuario inyectada en cada ciclo para evitar deriva (drift).
        - h_t (Estado cognitivo): Evoluciona iterativamente según la fase especializada del bucle.
        - ACT Halting: Se detiene tan pronto como converge, previniendo el 'overthinking'.
        """
        budget_loops = self.assess_complexity(goal)
        act = ACTState(max_loops=budget_loops, threshold=self.act_threshold)

        # Inyección de anclaje inicial e
        anchor_e = goal.strip()
        h_t = f"Meta base: {anchor_e}"
        prev_keywords: Set[str] = set(re.findall(r"\w+", anchor_e.lower()))

        for loop_idx in range(budget_loops):
            # Fase diferenciada por índice de bucle (Loop Index Embedding)
            phase_info = self.LOOP_PHASES.get(loop_idx, self.LOOP_PHASES[3])
            phase_name = phase_info["name"]
            phase_focus = phase_info["focus"]

            if loop_idx == 0:
                current_thought = f"[{phase_name}]: {phase_focus} para '{anchor_e}'."
                step_confidence = 0.60
            elif loop_idx == 1:
                current_thought = f"[{phase_name}]: {phase_focus} en el entorno local para '{anchor_e}'."
                step_confidence = 0.80
            elif loop_idx == 2:
                current_thought = f"[{phase_name}]: {phase_focus} para '{anchor_e}'."
                step_confidence = 0.90
            else:
                current_thought = f"[{phase_name}]: {phase_focus} para '{anchor_e}'."
                step_confidence = 0.95

            # Medir cambio delta conceptual respecto al bucle previo
            current_keywords = set(re.findall(r"\w+", current_thought.lower()))
            overlap = len(prev_keywords.intersection(current_keywords))
            union = len(prev_keywords.union(current_keywords)) or 1
            jaccard_similarity = overlap / union
            delta_change = 1.0 - jaccard_similarity
            prev_keywords = current_keywords

            # Actualizar estado ACT
            should_halt = act.update(loop_idx, step_confidence, delta_change, current_thought)
            if should_halt:
                break

        # Síntesis final de la deliberación latente
        loops_used = act.current_loop
        halt_type = "Convergencia ACT temprana (sin sobrepensar)" if act.halted_early else "Convergencia alcanzada"
        synthesis = (
            f"Deliberación recurrente OpenMythos completada ({loops_used}/{budget_loops} bucles, {halt_type}). "
            f"Fase final: '{self.LOOP_PHASES.get(loops_used - 1, self.LOOP_PHASES[3])['name']}'. "
            f"Confianza acumulada: {int(act.cumulative_halt_prob * 100)}%."
        )

        return synthesis, act
