"""
Aplicación de Escritorio JEV con Interfaz Holográfica JARVIS.
Ejecuta la interfaz nativa mediante PyWebView conectada en tiempo real al agente autónomo.
"""
import sys
import os
import json
import threading
import time
import re
from pathlib import Path
from typing import Optional, Dict, Any, List

# Asegurar codificación UTF-8 en Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

import psutil
import webview

from jev.config import AgentConfig, default_config
from jev.core.agent import AgentCore
from jev.self_improvement.evaluator import SelfImprovementEvaluator
from jev.self_improvement.qa_auditor import AgentQAAuditor
from jev.tools.base import ToolResult
from jev.core.claude_code_service import FreeClaudeCodeService
from jev.core.claude_code_bridge import ClaudeCodeBridge
from jev.core.image_generator import ImageGeneratorService
from jev.core.vision_engine import VisionEngine


class JarvisBridge:
    """Puente bidireccional entre JavaScript y el núcleo de Python."""

    def __init__(self, config: Optional[AgentConfig] = None):
        self._config = config or default_config
        self._window = None
        self._agent = AgentCore(
            config=self._config,
            on_thought=self._on_thought,
            on_tool_call=self._on_tool_call,
            on_tool_result=self._on_tool_result
        )
        self._evaluator = SelfImprovementEvaluator(self._agent.memory, self._agent.llm)
        self._qa_auditor = AgentQAAuditor(memory_dir=self._agent.memory.memory_dir)
        self._voice_enabled = False
        self._voice_tool = None

        # Integración de Servicio y Puente Free-Claude-Code
        self._fcc_service = FreeClaudeCodeService()
        self._fcc_bridge = ClaudeCodeBridge(service=self._fcc_service)

        # Motores Visuales: Generación de Imágenes y Visión Multimodal
        self._image_generator = ImageGeneratorService()
        self._vision_engine = VisionEngine()

        # --- Estado compartido con la Isla de escritorio ---
        self._last_thought: str = ""
        self._last_tool: str = ""
        self._last_tool_args: str = ""
        self._tool_in_progress: bool = False
        self._last_tool_ok: Optional[bool] = None
        self._current_task: str = ""
        self._task_started_at: float = 0.0
        self._speaking_until: float = 0.0
        self._island_mode: bool = False
        self._confirm_risky: bool = False
        self._pending_approval: Optional[Dict[str, Any]] = None
        self._chat_history: List[Dict[str, str]] = []

    def set_window(self, window):
        self._window = window
        # Iniciar hilo en segundo plano para sincronizar estado de FCC y telemetría
        t = threading.Thread(target=self._fcc_telemetry_loop, daemon=True)
        t.start()

    def _fcc_telemetry_loop(self):
        """Monitorea periódicamente el estado de Free Claude Code y notifica a la UI."""
        time.sleep(1.0)
        while True:
            try:
                if self._window:
                    status = self.get_fcc_status()
                    safe_json = json.dumps(status)
                    self._eval_js(f"window.onUpdateFCCStatus && window.onUpdateFCCStatus({safe_json});")
            except Exception as e:
                print(f"[Telemetry FCC Error]: {e}")
            time.sleep(3.5)

    def _eval_js(self, js_code: str):
        if self._window:
            try:
                self._window.evaluate_js(js_code)
            except Exception as e:
                print(f"[Bridge JS Error]: {e}")

    def _on_thought(self, text: str):
        self._last_thought = (text or "").strip()[:400]
        safe_text = json.dumps(text)
        self._eval_js(f"window.onAgentThought && window.onAgentThought({safe_text});")

    def _on_tool_call(self, tool_name: str, arguments: dict):
        self._last_tool = tool_name
        self._last_tool_args = self._brief_args(arguments)
        self._tool_in_progress = True

        safe_name = json.dumps(tool_name)
        safe_args = json.dumps(json.dumps(arguments, indent=2, ensure_ascii=False))
        self._eval_js(f"window.onAgentToolCall && window.onAgentToolCall({safe_name}, {safe_args});")

        # Puerta de aprobación para acciones sensibles (modo seguro de la Isla).
        if self._needs_approval(tool_name):
            if not self._request_approval(tool_name, arguments):
                self._tool_in_progress = False
                self._on_thought(
                    "🛑 [Isla JEV]: Acción sensible denegada por el usuario. "
                    "Debes plantear una alternativa sin ejecutar ese comando."
                )
                return False
        return True

    @staticmethod
    def _brief_args(arguments: Any, limit: int = 200) -> str:
        try:
            text = json.dumps(arguments, ensure_ascii=False) if not isinstance(arguments, str) else arguments
        except (TypeError, ValueError):
            text = str(arguments)
        text = " ".join(str(text).split())
        return text[:limit] + ("…" if len(text) > limit else "")

    def _on_tool_result(self, tool_name: str, result: ToolResult):
        self._tool_in_progress = False
        self._last_tool_ok = bool(result.success)
        safe_name = json.dumps(tool_name)
        out = result.output if result.success else (result.error or result.output)
        if len(out) > 2000:
            out = out[:2000] + "... [truncado]"
        safe_res = json.dumps(out)
        safe_success = "true" if result.success else "false"
        self._eval_js(f"window.onAgentToolResult && window.onAgentToolResult({safe_name}, {safe_res}, {safe_success});")

        # Renderizado reactivo en el Lienzo de Visualización Dual (Split-Screen / Viewport 3D / Web Preview)
        if result.success and result.data:
            if tool_name in ("skill_mesh_generator", "skill_cad_mesh", "render_3d_scene") and result.data.get("scene"):
                safe_scene = json.dumps(result.data["scene"])
                self._eval_js(f"window.onRender3DScene && window.onRender3DScene({safe_scene});")
                title = result.data.get("title") or result.data.get("name") or "Diseño 3D"
                mesh_info = ""
                if result.data.get("vertex_count") is not None:
                    mesh_info = (
                        f" ({result.data.get('vertex_count')} vértices / "
                        f"{result.data.get('face_count', 0)} triángulos, {result.data.get('engine', 'kernel')})"
                    )
                self._on_thought(f"🧊 [Viewport 3D]: '{title}' renderizado en el lienzo{mesh_info}.")
            elif tool_name == "execute_viewport_script" and result.data.get("js_code"):
                self.execute_viewport_script(result.data["js_code"])
                self._on_thought("🎮 [Viewport 3D]: Script JavaScript nativo inyectado sobre la escena activa.")
            elif (tool_name in ("skill_web_builder", "skill_browser_operator", "skill_web_design_pro") or "html" in result.data) and result.data.get("html"):
                safe_html = json.dumps(result.data["html"])
                title = json.dumps(result.data.get("title", "Vista Previa Web"))
                self._eval_js(f"window.onRenderWebPreview && window.onRenderWebPreview({safe_html}, {title});")
                self._eval_js(f"window.onRenderCodeArtifact && window.onRenderCodeArtifact({safe_html}, 'index.html');")
            elif tool_name == "skill_osint_investigator" and "threejs_graph" in result.data:
                safe_graph = json.dumps(result.data["threejs_graph"])
                self._eval_js(f"window.onRender3DScene && window.onRender3DScene({safe_graph});")
                self._on_thought(f"🧅 [OSINT Darknet Topology]: Grafo topológico 3D proyectado en Viewport Three.js ({result.data.get('total_nodes', 0)} nodos).")
            elif tool_name == "skill_claude_code" and result.data.get("code"):
                safe_code = result.data.get("code")
                filename = result.data.get("saved_file") or "claude_generated.py"
                self._eval_js(f"window.onRenderCodeArtifact && window.onRenderCodeArtifact({json.dumps(safe_code)}, {json.dumps(Path(filename).name)});\n")
                self._on_thought(f"🤖 [Claude Code Synthesis]: Solución de código proyectada en el editor de artefactos.")
            elif tool_name in ("skill_image_generator", "image_generator", "generate_image") and result.data:
                img_uri = result.data.get("data_uri") or result.data.get("image_path")
                prompt_val = result.data.get("prompt", "Imagen Generada")
                if img_uri:
                    safe_uri = json.dumps(img_uri)
                    safe_prompt = json.dumps(prompt_val)
                    self._eval_js(f"window.onAgentImageGenerated && window.onAgentImageGenerated({safe_uri}, {safe_prompt});")
                    self._on_thought(f"🎨 [Síntesis Visual]: Imagen generada exitosamente a partir de '{prompt_val}'.")
            elif tool_name in ("skill_vision_recognizer", "vision_recognizer", "analyze_image") and result.data:
                desc = result.data.get("description", "")
                engine = result.data.get("engine_used", "Visión")
                self._on_thought(f"👁️ [{engine}]: {desc[:140]}...")
            elif tool_name in ("skill_video_creator", "auto_launch_video") or "video_path" in result.data:
                video_p = str(result.data.get("video_path", ""))
                if video_p:
                    self._on_thought(f"🎬 [Vídeo de Lanzamiento Compilado]: '{video_p}' generado y listo para reproducción.")
            elif tool_name in ("skill_repo_planner", "repo_planner"):
                diff_c = result.data.get("diff_text") or result.data.get("diff", "")
                plan_id = result.data.get("plan_id", "refactor")
                files_count = result.data.get("files_count", len(result.data.get("files", [])))
                if diff_c and diff_c != "(Sin diferencias detectadas entre staging y workspace)":
                    self._eval_js(f"window.onRenderCodeArtifact && window.onRenderCodeArtifact({json.dumps(diff_c)}, 'changes.diff');")
                    self._on_thought(f"🛡️ [Plandex Staging]: Plan '{plan_id}' analizado ({files_count} archivos afectados). Diff unificado proyectado en artefactos.")
                if result.data.get("files_committed"):
                    committed_files = result.data.get("files_committed", [])
                    self._on_thought(f"🚀 [Plandex Atomic Commit]: {len(committed_files)} archivos confirmados y fusionados con éxito en workspace.")
                elif result.data.get("rolled_back"):
                    self._on_thought(f"↩️ [Plandex Rollback Preventivo]: Rama '{plan_id}' revertida para proteger la integridad del proyecto.")
            elif tool_name == "write_file":
                p = str(result.data.get("path", "file.txt"))
                c = result.data.get("content", "")
                if c:
                    # Renderizar siempre el código en el editor/visor de artefactos
                    self._eval_js(f"window.onRenderCodeArtifact && window.onRenderCodeArtifact({json.dumps(c)}, {json.dumps(p)});")
                    
                    # Si el artefacto es HTML, inyectarlo automáticamente en la vista previa y conmutar pestaña
                    if p.endswith(".html") or "<!DOCTYPE html>" in c:
                        self._eval_js(f"window.onRenderWebPreview && window.onRenderWebPreview({json.dumps(c)});")

    def render_3d_scene(self, scene_dict: dict):
        """Permite renderizar directamente una escena 3D en el viewport."""
        safe_scene = json.dumps(scene_dict)
        self._eval_js(f"window.onRender3DScene && window.onRender3DScene({safe_scene});")

    def render_web_preview(self, html_content: str, title: str = "Vista Previa Web"):
        """Permite renderizar directamente una vista previa web interactiva en el panel de artefactos."""
        safe_html = json.dumps(html_content)
        safe_title = json.dumps(title)
        self._eval_js(f"window.onRenderWebPreview && window.onRenderWebPreview({safe_html}, {safe_title});")

    def execute_viewport_script(self, js_code: str):
        """Ejecuta un script JavaScript nativo directamente sobre la escena Three.js activa del Viewport."""
        safe_code = json.dumps(js_code)
        self._eval_js(f"window.executeViewportScript && window.executeViewportScript({safe_code});")

    def render_code_artifact(self, code_str: str, filename: str = "snippet.py"):
        """Permite renderizar directamente código o texto en el panel de artefactos."""
        self._eval_js(f"window.onRenderCodeArtifact && window.onRenderCodeArtifact({json.dumps(code_str)}, {json.dumps(filename)});")

    def on_viewport_event(self, event_type: str, data: dict = None):
        """Recibe eventos bidireccionales disparados desde el viewport 3D (clics en mallas, interacción de cámara)."""
        data = data or {}
        print(f"[Viewport Event]: {event_type} - {data}")
        if event_type == "mesh_selected":
            mesh_name = data.get("name", "Objeto 3D")
            self._on_thought(f"👁️ [Viewport 3D]: Elemento '{mesh_name}' seleccionado por el usuario en el lienzo.")

    def set_orb_state(self, state: str):
        """Permite cambiar directamente el estado del Orbe Cognitivo (Thinking Orb) en la interfaz."""
        safe_state = json.dumps(state)
        self._eval_js(f"window.setAgentOrbState && window.setAgentOrbState({safe_state});")

    def toggle_voice_synthesis(self, enabled: bool):
        """Activa o desactiva la síntesis y clonación de voz local de JEV."""
        self._voice_enabled = bool(enabled)
        print(f"[JarvisBridge]: Síntesis de voz local {'ACTIVADA' if self._voice_enabled else 'DESACTIVADA'}.")

    # ------------------------------------------------------------------
    # API DE LA ISLA DE ESCRITORIO (estado, voz, aprobaciones)
    # ------------------------------------------------------------------
    def set_confirm_risky(self, enabled: bool) -> bool:
        """Activa la puerta de aprobación para comandos y escrituras sensibles."""
        self._confirm_risky = bool(enabled)
        print(f"[JarvisBridge]: Confirmación de acciones sensibles {'ACTIVADA' if self._confirm_risky else 'DESACTIVADA'}.")
        return self._confirm_risky

    def _needs_approval(self, tool_name: str) -> bool:
        if not self._confirm_risky:
            return False
        return tool_name in {
            "execute_command",
            "execute_python",
            "write_file",
            "patch_file",
            "skill_claude_code",
            "skill_sdlc_senior",
        }

    def _request_approval(self, tool_name: str, arguments: Dict[str, Any], timeout: float = 180.0) -> bool:
        """Bloquea el hilo del agente hasta que la Isla permita o deniegue."""
        event = threading.Event()
        self._pending_approval = {
            "tool": tool_name,
            "args": self._brief_args(arguments),
            "created": time.time(),
            "event": event,
            "allow": False,
        }
        granted = False
        deadline = time.time() + max(1.0, timeout)
        try:
            # Espera por tramos para poder abortar si el usuario detiene el agente.
            while time.time() < deadline:
                if event.wait(0.5):
                    granted = True
                    break
                if getattr(self._agent, "abort_requested", False):
                    break
        finally:
            pending = self._pending_approval
            self._pending_approval = None
        if not granted:
            return False
        return bool(pending and pending.get("allow"))

    def pending_approval(self) -> Optional[Dict[str, Any]]:
        pending = self._pending_approval
        if not pending:
            return None
        return {
            "tool": pending.get("tool", ""),
            "args": pending.get("args", ""),
            "age_seconds": round(time.time() - pending.get("created", time.time()), 1),
        }

    def resolve_approval(self, allow: bool) -> Dict[str, Any]:
        """Resuelve la aprobación pendiente desde la Isla."""
        pending = self._pending_approval
        if not pending:
            return {"ok": False, "message": "No hay ninguna aprobación pendiente."}
        pending["allow"] = bool(allow)
        pending["event"].set()
        return {"ok": True, "allow": bool(allow)}

    def activity_snapshot(self) -> Dict[str, Any]:
        """Estado compacto que consume la Isla flotante (se consulta por polling)."""
        try:
            cpu = int(psutil.cpu_percent(interval=None))
            ram = int(psutil.virtual_memory().percent)
        except Exception:
            cpu, ram = 0, 0

        pending = self.pending_approval()
        if pending:
            state = "approval"
        elif time.time() < self._speaking_until:
            state = "speaking"
        elif self._agent.is_running and self._tool_in_progress:
            state = "tool"
        elif self._agent.is_running:
            state = "thinking"
        else:
            state = "idle"

        model_label = (
            f"{self._config.thinker_model} + {self._config.executor_model}"
            if self._config.hybrid_mode
            else self._config.model_name
        )
        return {
            "state": state,
            "running": bool(self._agent.is_running),
            "thought": self._last_thought,
            "tool": self._last_tool,
            "tool_args": self._last_tool_args,
            "tool_in_progress": self._tool_in_progress,
            "last_ok": self._last_tool_ok,
            "task": self._current_task,
            "voice": self._voice_enabled,
            "confirm_risky": self._confirm_risky,
            "pending": pending,
            "cpu": cpu,
            "ram": ram,
            "model": model_label,
            "island_mode": self._island_mode,
        }

    def _synthesize_voice_async(self, text: str):
        """Despacha la síntesis de voz en un hilo daemon desacoplado sin bloquear el loop."""
        if not self._voice_enabled or not text:
            return

        def _worker():
            try:
                if self._voice_tool is None:
                    from jev.tools.custom.skill_voice_engine import VoiceEngineTool
                    self._voice_tool = VoiceEngineTool()

                clean_text = re.sub(r'```[\s\S]*?```', '', text)
                clean_text = re.sub(r'[*#`_{}\[\]()\\|<>~]', ' ', clean_text)
                clean_text = ' '.join(clean_text.split()).strip()[:400]
                if not clean_text:
                    return

                res = self._voice_tool.execute(
                    action="synthesize_speech",
                    text=clean_text,
                    language="es",
                    output_filename=f"speech_{int(time.time()*1000)}.wav"
                )
                if res.success and res.data and "audio_path" in res.data:
                    audio_file = Path(res.data["audio_path"])
                    if audio_file.exists():
                        audio_url = f"file:///{audio_file.resolve().as_posix()}"
                        safe_url = json.dumps(audio_url)
                        self._speaking_until = time.time() + max(2.0, len(clean_text) / 14.0)
                        self._eval_js(f"window.playAudioOutput && window.playAudioOutput({safe_url});")
            except Exception as e:
                print(f"[Voice Async Worker Error]: {e}")

        threading.Thread(target=_worker, daemon=True).start()

    def execute_task(self, task: str, image_base64: Optional[str] = None):
        """Ejecuta la tarea en un hilo independiente, soportando imágenes pegadas/adjuntas."""
        clean_prompt = (task or "").strip()
        if clean_prompt:
            self._chat_history.append({"role": "user", "content": clean_prompt})

        if self._agent.is_running:
            self._agent.inject_user_feedback(task)
            self._on_thought(f"⚡ [Intervención del Usuario en Caliente]: {task}")
            return

        def _runner():
            self._current_task = (task or "").strip()[:200]
            self._task_started_at = time.time()
            try:
                effective_task = task
                if image_base64:
                    self._on_thought("👁️ [Visión Multimodal]: Analizando imagen adjunta/pegada por el usuario...")
                    file_path, raw_b64 = self._vision_engine.save_image_from_base64(image_base64, prefix="user_paste")
                    vis_res = self._vision_engine.analyze(str(file_path), user_prompt=task)
                    self._on_thought(
                        f"👁️ [Reconocimiento Visual ({vis_res.engine_used})]: {vis_res.description[:140]}..."
                    )
                    user_q = task.strip() if task and task.strip() else "Describe y analiza en detalle esta imagen."
                    effective_task = (
                        f"{user_q}\n\n"
                        f"--- [ANÁLISIS DE LA IMAGEN PEGADA / ADJUNTA POR EL USUARIO] ---\n"
                        f"• Archivo local guardado: '{file_path}'\n"
                        f"• Dimensiones: {vis_res.width}x{vis_res.height} px ({vis_res.format})\n"
                        f"• Motor de Visión: {vis_res.engine_used}\n"
                        f"• Contenido Visual Reconocido:\n{vis_res.description}\n"
                        f"----------------------------------------------------------------"
                    )

                final_answer = self._agent.run_task(effective_task)

                # Control de Calidad LLM y Red-Teaming (QA Shield)
                qa_report = self._qa_auditor.audit_response(final_answer, context=effective_task)
                if not qa_report.is_safe:
                    self._on_thought(
                        f"🛡️ [Bloqueo de Seguridad QA]: Vulnerabilidad detectada en respuesta ({', '.join(qa_report.issues)}). "
                        "Bloqueando despacho no seguro y aplicando autocorrección inmediata..."
                    )
                    final_answer = self._qa_auditor.sanitize_or_correct(final_answer, qa_report)

                self._chat_history.append({"role": "assistant", "content": final_answer})

                safe_final = json.dumps(final_answer)
                self._eval_js(f"window.onAgentFinish && window.onAgentFinish({safe_final});")

                # Actualizar estado del Escudo QA en la interfaz
                shield_info = self._qa_auditor.get_shield_status()
                safe_label = json.dumps(shield_info["status_label"])
                self._eval_js(f"window.onUpdateQAShield && window.onUpdateQAShield({safe_label}, {shield_info['total_vulnerabilities']});")

                # Síntesis de voz desacoplada si el subsistema está activo
                if self._voice_enabled and final_answer:
                    self._synthesize_voice_async(final_answer)

                # Evaluación de automejora en segundo plano
                self._evaluator.reflect_and_learn(
                    task=task,
                    execution_log=self._agent.messages,
                    success=True
                )
            except Exception as e:
                err_text = f"Error ejecutando tarea: {e}"
                self._chat_history.append({"role": "assistant", "content": err_text})
                err_json = json.dumps(err_text)
                self._eval_js(f"window.onAgentFinish && window.onAgentFinish({err_json});")
            finally:
                self._current_task = ""
                self._tool_in_progress = False

        t = threading.Thread(target=_runner, daemon=True)
        t.start()

    def execute_task_with_image(self, task: str, image_base64: str):
        """Punto de entrada explícito para llamadas desde JS con imagen adjunta."""
        return self.execute_task(task=task, image_base64=image_base64)

    def generate_image_direct(self, prompt: str) -> dict:
        """Permite generar imágenes bajo demanda directamente desde la UI."""
        res = self._image_generator.generate(prompt)
        return {
            "success": res.is_success,
            "data_uri": res.data_uri,
            "image_path": res.image_path,
            "markdown": res.markdown,
            "prompt": res.prompt,
            "error": res.error
        }

    def analyze_image_direct(self, image_data: str, prompt: str = "") -> dict:
        """Permite analizar o transcribir una imagen directamente desde la UI."""
        res = self._vision_engine.analyze(image_data, user_prompt=prompt)
        return {
            "success": res.is_success,
            "description": res.description,
            "engine_used": res.engine_used,
            "width": res.width,
            "height": res.height,
            "format": res.format,
            "error": res.error
        }

    def inject_feedback(self, text: str):
        """Inyecta una orden o corrección del usuario en caliente durante la ejecución activa."""
        self._agent.inject_user_feedback(text)
        self._on_thought(f"⚡ [Intervención del Usuario en Caliente]: {text}")

    def stop_agent(self):
        """Detiene inmediatamente la ejecución de cualquier tarea activa."""
        self._agent.stop()
        self._eval_js("window.onAgentStopped && window.onAgentStopped();")

    def close_app(self):
        """Cierra la ventana y la aplicación, deteniendo servicios dependientes."""
        # En modo Isla, cerrar la ventana grande solo la oculta: el compañero
        # flotante sigue vivo y puede reabrirla.
        if self._island_mode and self._window:
            try:
                self._window.hide()
            except Exception:
                pass
            return
        try:
            from jev.core.claude_code_service import FreeClaudeCodeService
            FreeClaudeCodeService().stop()
        except Exception:
            pass
        if self._window:
            self._window.destroy()

    def get_fcc_status(self) -> dict:
        """Devuelve el estado de salud, puerto y configuración del proxy local de Claude Code."""
        try:
            return self._fcc_service.get_status()
        except Exception as e:
            return {"is_running": False, "is_healthy": False, "error": str(e), "port": 8082}

    def start_fcc_server(self) -> dict:
        """Inicia el servidor local de Claude Code si no estuviera corriendo."""
        try:
            ok, msg = self._fcc_service.start()
            return {"success": ok, "message": msg, "status": self._fcc_service.get_status()}
        except Exception as e:
            return {"success": False, "message": str(e)}

    def restart_fcc_server(self) -> dict:
        """Reinicia el servicio local de Claude Code."""
        try:
            self._fcc_service.stop()
            time.sleep(0.5)
            ok, msg = self._fcc_service.start()
            return {"success": ok, "message": msg, "status": self._fcc_service.get_status()}
        except Exception as e:
            return {"success": False, "message": str(e)}

    def query_claude_code(self, prompt: str, model: str = None) -> dict:
        """Envía una solicitud interactiva a Claude Code desde la interfaz gráfica."""
        try:
            resp = self._fcc_bridge.query(prompt=prompt, model=model)
            code_snippets = [
                {"lang": s.language, "code": s.code, "filename": s.filename}
                for s in resp.code_blocks
            ]
            return {
                "success": resp.is_success,
                "content": resp.content,
                "thinking": resp.thinking,
                "model": resp.model or self._fcc_service.default_model,
                "code_snippets": code_snippets,
                "error": resp.error
            }
        except Exception as e:
            return {"success": False, "content": "", "error": str(e), "code_snippets": []}

    def get_telemetry(self) -> dict:
        """Devuelve telemetría en tiempo real del hardware, memoria y servicios activos."""
        try:
            cpu = psutil.cpu_percent(interval=None)
            ram = psutil.virtual_memory().percent
        except Exception:
            cpu, ram = 0, 0

        lessons = self._agent.memory.get_all_lessons()
        recent_lessons = lessons[-5:] if lessons else []

        episodes = 0
        if self._agent.memory.episodes_file.exists():
            try:
                with open(self._agent.memory.episodes_file, "r", encoding="utf-8") as f:
                    episodes = len(f.readlines())
            except Exception:
                pass

        shield_info = self._qa_auditor.get_shield_status()
        model_label = f"{self._config.thinker_model} 🧠 + {self._config.executor_model} ⚡" if self._config.hybrid_mode else self._config.model_name
        
        fcc_info = self.get_fcc_status()
        return {
            "cpu": int(cpu),
            "ram": int(ram),
            "model": model_label,
            "episodes": episodes,
            "lessons": recent_lessons,
            "qa_status": shield_info["status_label"],
            "qa_shield_active": True,
            "qa_vulnerabilities": shield_info["total_vulnerabilities"],
            "fcc_healthy": fcc_info.get("is_healthy", False),
            "fcc_running": fcc_info.get("is_running", False),
            "fcc_port": fcc_info.get("port", 8082),
            "fcc_model": fcc_info.get("configured_model", "Llama-3.3-70B-Free")
        }


def main():
    try:
        from jev.ui.island import enable_dpi_awareness

        enable_dpi_awareness()
    except Exception:
        pass
    config = AgentConfig()
    bridge = JarvisBridge(config)

    html_path = Path(__file__).parent / "jev" / "ui" / "templates" / "jarvis.html"

    # Ajustar la ventana al tamaño lógico real de la pantalla (DPI incluido)
    try:
        from jev.ui.island import screen_metrics

        logical_w, logical_h, _ = screen_metrics()
        window_width = min(1380, max(960, int(logical_w) - 60))
        window_height = min(860, max(640, int(logical_h) - 110))
    except Exception:
        window_width, window_height = 1380, 860

    window = webview.create_window(
        title="JEV // Autonomous AI",
        url=str(html_path.resolve()),
        js_api=bridge,
        width=window_width,
        height=window_height,
        min_size=(min(1000, window_width), min(650, window_height)),
        background_color="#000000"
    )

    bridge.set_window(window)
    webview.start(debug=False)


if __name__ == "__main__":
    main()
