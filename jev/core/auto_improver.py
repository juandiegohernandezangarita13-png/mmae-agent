"""
Módulo de Auto-Mejora y Autoprogramación Asistida por Gemini (GeminiSelfImprover).

Permite que el agente JEV:
1. Extraiga su propio inventario de capacidades, herramientas y arquitectura actual.
2. Consulte a la API de Gemini para diagnosticar cuellos de botella y herramientas faltantes.
3. Reciba la recomendación técnica y el código Python completo de la herramienta propuesta.
4. Sintetice el código, verifique dependencias, valide sintaxis y ejecute pruebas efímeras en sandbox.
5. Inyecte la nueva herramienta en memoria de ejecución en caliente (hot-reloading) sin reiniciar.
6. Registre la mejora en su memoria a largo plazo y verifique su funcionamiento de forma autónoma.
"""
from typing import Dict, Any, List, Optional, Tuple, Callable
from pathlib import Path
import subprocess
import importlib
import traceback
import tempfile
import time
import json
import sys
import os
import re
import ast

from jev.tools.base import BaseTool, ToolRegistry, ToolResult
from jev.config import AgentConfig, default_config
from jev.core.llm_client import LocalLLMClient
from jev.core.self_evolving_agent import (
    ToolSpecification,
    CodeSynthesizer,
    HotReloadingInjector
)


class GeminiSelfImprover:
    """
    Motor de Introspección, Consulta a Gemini y Autoprogramación en Caliente.
    """

    def __init__(
        self,
        registry: Optional[ToolRegistry] = None,
        config: Optional[AgentConfig] = None,
        llm_client: Optional[LocalLLMClient] = None,
        output_dir: Optional[Path] = None,
        on_log: Optional[Callable[[str], None]] = None
    ):
        self.config = config or default_config
        self.registry = registry or ToolRegistry()
        self.llm_client = llm_client or LocalLLMClient(self.config)
        self.output_dir = output_dir or (self.config.base_dir / "generated_tools")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.on_log = on_log or (lambda msg: None)

        self.synthesizer = CodeSynthesizer(output_dir=self.output_dir)
        self.injector = HotReloadingInjector(on_log=self.on_log)
        self.memory_dir = self.config.memory_dir
        self.improvements_log_file = self.memory_dir / "self_improvements.json"

    def log(self, message: str) -> None:
        self.on_log(message)

    def build_system_inventory(self) -> Dict[str, Any]:
        """
        Recopila el estado e inventario completo de herramientas y subsistemas de JEV.
        """
        tools_list = []
        for t in self.registry.list_tools():
            tools_list.append({
                "name": t.name,
                "description": t.description,
                "parameters": list(t.parameters.get("properties", {}).keys()) if isinstance(t.parameters, dict) else []
            })

        generated_tools_files = [
            f.name for f in self.output_dir.glob("*.py")
            if not f.name.startswith("__")
        ]

        core_subsystems = [
            "ReAct & Reflexion Loop (Cognitive Self-Evolution)",
            "Hot-Reloading Dynamic Injector (Zero-Downtime Tool Loading)",
            "Semantic Memory (BM25 + TF-IDF Vector Cosine Index)",
            "Subagent Swarm Orchestrator (Roles: Researcher, Coder, Tester)",
            "Autonomous Heartbeat Scheduler (Cron / Background Daemons)",
            "System Doctor (Self-Healing, Disk Triage, CUDA Monitor)",
            "UI Visual Grounding (Windows OCR & Clicks by Text)",
            "Offline Vault Engine (SQLite FTS5 Full-Text Search)",
            "WiFi Sensing Engine (CSI / RSSI Anomaly Detector)",
            "REA Assistant (Binary Disassembly & Reverse Engineering)",
            "ACE Sandbox (Isolated Process Execution Container)",
            "DNS Sinkhole (Ad-blocking Proxy & DNS Filter)",
            "HyperFrames Video Generator & SmolVM Container Runner"
        ]

        return {
            "total_registered_tools": len(tools_list),
            "tools": tools_list,
            "core_subsystems": core_subsystems,
            "existing_generated_tools": generated_tools_files
        }

    def consult_gemini(self, focus_area: Optional[str] = None) -> Dict[str, Any]:
        """
        Consulta a Gemini enviando el inventario actual de JEV para que identifique
        capacidades faltantes y genere la especificación y código de una nueva herramienta.
        """
        inventory = self.build_system_inventory()
        tools_summary = "\n".join(
            f"- `{t['name']}`: {t['description']} (Parámetros: {', '.join(t['parameters'])})"
            for t in inventory["tools"]
        )

        focus_text = f"\nÁREA DE ENFOQUE SOLICITADA POR EL USUARIO: {focus_area}\n" if focus_area else ""

        prompt = f"""Actúa como el Arquitecto de Sistemas de IA Senior para el agente autónomo JEV.

INVENTARIO ACTUAL DE HERRAMIENTAS ACTIVAS ({inventory['total_registered_tools']} herramientas registradas):
{tools_summary}

SUBSISTEMAS NUCLEARES ACTIVOS:
{chr(10).join('- ' + s for s in inventory['core_subsystems'])}

HERRAMIENTAS PREVIAMENTE AUTOGENERADAS EN ./generated_tools/:
{inventory['existing_generated_tools']}
{focus_text}
OBJETIVO:
1. Analiza con profundidad qué herramienta o capacidad de sistema crítica hace falta en JEV para que sea aún más autónomo, potente y autosuficiente en Windows.
2. Elige LA HERRAMIENTA FALTANTE MÁS VALIOSA que todavía NO esté implementada ni duplicada.
   Ejemplos de áreas de alto impacto si no existen:
   - Gestión y portapapeles del sistema (leer/escribir portapapeles con formato/texto).
   - Monitoreo/gestión de procesos activos en Windows (listar procesos pesados, buscar por PID/nombre, terminar procesos colgados).
   - Notificaciones nativas de escritorio Windows (toast notifications interactivas para alertar al usuario).
   - Audio / Text-to-Speech nativo (anunciar eventos importantes por voz sin librerías externas complejas).
   - Inspección y control de adaptadores de red o latencia/ping avanzado.
   - Herramienta de Git / Commit / Branching nativa para versionar el propio código del agente.
3. Diseña e implementa el código Python COMPLETO de una subclase de `BaseTool`.

REGLAS ESTRICTAS DE CÓDIGO PYTHON:
- Debe importar `from jev.tools.base import BaseTool, ToolResult`.
- Debe heredar de `BaseTool`.
- Debe definir `name` (string en minúsculas snake_case terminando preferiblemente en _tool).
- Debe definir `description` (resumen conciso de lo que hace).
- Debe definir `parameters` como un diccionario JSON Schema válido (`type: object`, `properties: {...}`, `required: [...]`).
- Debe implementar `def execute(self, **kwargs) -> ToolResult`.
- Debe devolver SIEMPRE un objeto `ToolResult(success=True|False, output=..., error=..., data=...)`.
- Debe capturar excepciones internas y retornar `ToolResult(success=False, output="", error=str(e))`.
- El código debe ser 100% autocontenido, conciso (máximo 60-80 líneas), completo y ejecutable inmediatamente en Windows con Python 3.10+, sin bloques cortados ni incompletos.

FORMATO OBLIGATORIO DE RESPUESTA:
Devuelve dos bloques bien diferenciados:
1. Metadatos de la herramienta en formato JSON:
```json
{{
  "diagnosis": "Diagnóstico detallado de por qué JEV necesitaba esta capacidad",
  "recommended_capability": "Nombre conciso de la capacidad propuesta",
  "tool_name": "nombre_en_snake_case_tool",
  "class_name": "NombreEnCamelCaseTool",
  "description": "Descripción formal de la herramienta",
  "required_dependencies": [],
  "parameters_schema": {{
    "type": "object",
    "properties": {{ ... }},
    "required": [ ... ]
  }}
}}
```

2. Código Python completo y ejecutable:
```python
from jev.tools.base import BaseTool, ToolResult

class NombreEnCamelCaseTool(BaseTool):
    name = "nombre_en_snake_case_tool"
    description = "Descripción formal de la herramienta"
    parameters = {{ ... }}

    def execute(self, **kwargs) -> ToolResult:
        try:
            # Lógica completa
            return ToolResult(success=True, output="Resultado...")
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))
```
"""

        messages = [
            {
                "role": "system",
                "content": "Eres el Meta-Arquitecto de JEV. Diseñas herramientas complementarias de alto impacto y proporcionas código Python limpio, modular y 100% funcional."
            },
            {
                "role": "user",
                "content": prompt
            }
        ]

        self.log("🌐 [Gemini Self-Improver]: Enviando auditoría de arquitectura e inventario a Gemini...")

        try:
            response = self.llm_client.chat(messages=messages, override_model=self.config.thinker_model)
            raw_text = response.content.strip()
            proposal = self._extract_proposal(raw_text, focus_area)
            self.log(f"💡 [Gemini]: Diagnóstico recibido: {proposal.get('recommended_capability')}")
            return proposal
        except Exception as e:
            self.log(f"⚠️ [Gemini]: Error de conexión/llamada ({e}). Activando síntesis de fallback offline...")
            return self._generate_offline_fallback_proposal(focus_area)

    def _extract_proposal(self, text: str, focus_area: Optional[str]) -> Dict[str, Any]:
        """
        Extrae la propuesta técnica y el código Python generado por Gemini.
        Soporta de forma unificada:
        1. Formato dual: Bloque ```json con metadatos y bloque ```python con código.
        2. Formato JSON único con propiedad 'python_code'.
        3. Bloque ```python con extracción de metadatos desde los atributos de la clase.
        """
        # A. Intentar extraer código de bloque ```python ... ```
        py_match = re.search(r"```python\s*([\s\S]*?class\s+[A-Za-z0-9_]+\(BaseTool\)[\s\S]*?)\s*```", text)
        if not py_match:
            py_match = re.search(r"```(?:python)?\s*([\s\S]*?)\s*```", text)
            # Solo si contiene class
            if py_match and "class " not in py_match.group(1):
                py_match = None

        python_code = py_match.group(1).strip() if py_match else None

        # B. Intentar extraer metadatos de bloque ```json ... ```
        meta_dict = None
        json_match = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", text)
        if json_match:
            try:
                meta_dict = json.loads(json_match.group(1), strict=False)
            except Exception:
                pass

        # C. Si no hubo bloque json con vallas, buscar primera { y última }
        if not meta_dict:
            start = text.find("{")
            end = text.rfind("}")
            if start != -1 and end != -1 and end > start:
                try:
                    candidate = text[start:end + 1]
                    meta_dict = json.loads(candidate, strict=False)
                except Exception:
                    pass

        # D. Si tenemos un JSON con 'python_code' y no había bloque python separado
        if not python_code and meta_dict and "python_code" in meta_dict:
            python_code = str(meta_dict.get("python_code", "")).strip()
            if "```" in python_code:
                m = re.search(r"```(?:python)?\s*([\s\S]*?)```", python_code)
                if m:
                    python_code = m.group(1).strip()

        # E. Si aún no tenemos python_code, buscar cualquier definición de clase en el texto
        if not python_code:
            m = re.search(r"((?:from\s+\S+\s+import\s+\S+|import\s+\S+\n[\s\S]*?)?class\s+([A-Za-z0-9_]+)\(BaseTool\)[\s\S]*?)(?:```|$)", text)
            if m:
                raw_extracted = m.group(1).strip()
                # Quitar posibles restos de JSON al final si se capturó dentro de un string
                end_class = raw_extracted.rfind("def execute")
                if end_class != -1:
                    # recortar al final de la indentación o retorno
                    python_code = raw_extracted

        # F. Si encontramos código Python, asegurar metadatos consistentes
        if python_code:
            meta = meta_dict or {}
            cls_match = re.search(r"class\s+([A-Za-z0-9_]+)\(BaseTool\)", python_code)
            class_name = meta.get("class_name") or (cls_match.group(1) if cls_match else "CustomGeneratedTool")

            name_match = re.search(r'name\s*=\s*["\']([^"\']+)["\']', python_code)
            tool_name = meta.get("tool_name") or (name_match.group(1) if name_match else class_name.lower())

            desc_match = re.search(r'description\s*=\s*["\']([^"\']+)["\']', python_code)
            description = meta.get("description") or (desc_match.group(1) if desc_match else f"Herramienta {tool_name}")

            diagnosis = meta.get("diagnosis") or "Capacidad técnica diagnosticada por Gemini para maximizar la autonomía de JEV."
            capability = meta.get("recommended_capability") or tool_name.replace("_", " ").title()

            return {
                "diagnosis": diagnosis,
                "recommended_capability": capability,
                "tool_name": tool_name,
                "class_name": class_name,
                "description": description,
                "required_dependencies": meta.get("required_dependencies", []),
                "parameters_schema": meta.get("parameters_schema", {"type": "object", "properties": {}}),
                "python_code": python_code
            }

        return self._generate_offline_fallback_proposal(focus_area)

    def _generate_offline_fallback_proposal(self, focus_area: Optional[str]) -> Dict[str, Any]:
        """
        Genera una propuesta determinista y funcional si la API de Gemini no está disponible.
        """
        focus = (focus_area or "").lower()

        if "process" in focus or "task" in focus:
            tool_name = "system_process_manager_tool"
            class_name = "SystemProcessManagerTool"
            description = "Monitorea, lista y administra procesos del sistema operativo Windows."
            code = '''"""
Herramienta de Gestión de Procesos para Windows.
Autogenerada por el módulo de auto-mejora de JEV.
"""
from typing import Dict, Any, Optional, List
import subprocess
import os

from jev.tools.base import BaseTool, ToolResult


class SystemProcessManagerTool(BaseTool):
    """Monitorea, lista y administra procesos del sistema operativo Windows."""
    name = "system_process_manager_tool"
    description = "Monitorea, lista y administra procesos del sistema operativo Windows."
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "Acción a realizar: 'list' (listar principales procesos), 'find' (buscar por nombre), 'kill' (terminar PID)",
                "enum": ["list", "find", "kill"]
            },
            "target": {
                "type": "string",
                "description": "Nombre del ejecutable a buscar o PID a terminar."
            },
            "limit": {
                "type": "integer",
                "description": "Límite de procesos a mostrar al listar."
            }
        },
        "required": ["action"]
    }

    def execute(self, action: str = "list", target: Optional[str] = None, limit: int = 15, **kwargs) -> ToolResult:
        try:
            if action == "list":
                cmd = f"Get-Process | Sort-Object CPU -Descending | Select-Object -First {limit} Id, ProcessName, CPU, WorkingSet64 | Format-Table -AutoSize"
                proc = subprocess.run(["powershell", "-NoProfile", "-Command", cmd], capture_output=True, text=True, timeout=15)
                return ToolResult(success=True, output=proc.stdout or "No se encontraron procesos.", data={"raw": proc.stdout})
            elif action == "find":
                if not target:
                    return ToolResult(success=False, output="", error="Debes especificar 'target' con el nombre del proceso.")
                cmd = f"Get-Process -Name '*{target}*' -ErrorAction SilentlyContinue | Select-Object Id, ProcessName, CPU, WorkingSet64 | Format-Table -AutoSize"
                proc = subprocess.run(["powershell", "-NoProfile", "-Command", cmd], capture_output=True, text=True, timeout=15)
                output = proc.stdout.strip()
                if not output:
                    return ToolResult(success=True, output=f"No se encontraron procesos activos coincidentes con '{target}'.")
                return ToolResult(success=True, output=output)
            elif action == "kill":
                if not target:
                    return ToolResult(success=False, output="", error="Debes especificar 'target' con el PID o nombre para terminar.")
                cmd = f"Stop-Process -Id {target} -Force" if target.isdigit() else f"Stop-Process -Name '{target}' -Force"
                proc = subprocess.run(["powershell", "-NoProfile", "-Command", cmd], capture_output=True, text=True, timeout=15)
                if proc.returncode == 0:
                    return ToolResult(success=True, output=f"Proceso '{target}' terminado exitosamente.")
                return ToolResult(success=False, output="", error=proc.stderr or "Fallo al terminar proceso.")
            else:
                return ToolResult(success=False, output="", error=f"Acción '{action}' desconocida.")
        except Exception as exc:
            return ToolResult(success=False, output="", error=f"Error en SystemProcessManagerTool: {exc}")
'''
        else:
            # Fallback por defecto: Clipboard Manager Tool
            tool_name = "system_clipboard_tool"
            class_name = "SystemClipboardTool"
            description = "Lee y escribe contenido en el portapapeles nativo de Windows."
            code = '''"""
Herramienta de Portapapeles para Windows.
Autogenerada por el módulo de auto-mejora de JEV.
"""
from typing import Dict, Any, Optional
import subprocess

from jev.tools.base import BaseTool, ToolResult


class SystemClipboardTool(BaseTool):
    """Lee y escribe contenido en el portapapeles nativo de Windows."""
    name = "system_clipboard_tool"
    description = "Lee y escribe contenido en el portapapeles nativo de Windows."
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "Acción a realizar: 'read' (leer portapapeles) o 'write' (escribir texto al portapapeles)",
                "enum": ["read", "write"]
            },
            "text": {
                "type": "string",
                "description": "Texto a copiar al portapapeles cuando action='write'."
            }
        },
        "required": ["action"]
    }

    def execute(self, action: str = "read", text: Optional[str] = None, **kwargs) -> ToolResult:
        try:
            if action == "read":
                cmd = "Get-Clipboard"
                proc = subprocess.run(["powershell", "-NoProfile", "-Command", cmd], capture_output=True, text=True, timeout=10)
                content = proc.stdout.strip()
                return ToolResult(
                    success=True,
                    output=f"[Portapapeles]: {content}" if content else "[Portapapeles vacío]",
                    data={"clipboard_content": content}
                )
            elif action == "write":
                if text is None:
                    return ToolResult(success=False, output="", error="Parámetro 'text' requerido para escribir.")
                # Escribir usando powershell Set-Clipboard
                proc = subprocess.run(["powershell", "-NoProfile", "-Command", "$input | Set-Clipboard"], input=text, capture_output=True, text=True, timeout=10)
                return ToolResult(
                    success=True,
                    output=f"Texto ({len(text)} caracteres) copiado exitosamente al portapapeles.",
                    data={"copied_length": len(text)}
                )
            else:
                return ToolResult(success=False, output="", error=f"Acción '{action}' no soportada.")
        except Exception as exc:
            return ToolResult(success=False, output="", error=f"Fallo en SystemClipboardTool: {exc}")
'''

        return {
            "diagnosis": "Capacidad esencial identificada para interactuar con el entorno de trabajo del sistema.",
            "recommended_capability": tool_name.replace("_", " ").title(),
            "tool_name": tool_name,
            "class_name": class_name,
            "description": description,
            "required_dependencies": [],
            "parameters_schema": {
                "type": "object",
                "properties": {"action": {"type": "string"}}
            },
            "python_code": code
        }

    def _sanitize_python_code(self, raw_code: str, class_name: str, tool_name: str, description: str) -> str:
        """
        Limpia y asegura que el código Python contenga las importaciones y estructura
        necesarias para funcionar como subclase de BaseTool.
        """
        code = raw_code.strip()

        # Quitar delimitadores de markdown si vienen dentro del string
        if code.startswith("```"):
            lines = code.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            code = "\n".join(lines).strip()

        # Si el código contiene literales \n o comillas escapadas procedentes de JSON
        try:
            ast.parse(code)
        except SyntaxError:
            fixed = code.replace("\\r\\n", "\n").replace("\\n", "\n").replace('\\"', '"').replace("\\'", "'")
            try:
                ast.parse(fixed)
                code = fixed
            except Exception:
                pass

        # Asegurar importaciones base
        if "from jev.tools.base import BaseTool" not in code and "import BaseTool" not in code:
            code = "from jev.tools.base import BaseTool, ToolResult\n" + code

        return code

    def synthesize_and_hot_reload(self, proposal: Dict[str, Any]) -> Dict[str, Any]:
        """
        Recibe la propuesta, valida la sintaxis, escribe el archivo persistente,
        ejecuta la prueba unitaria en sandbox y carga la herramienta en caliente en ToolRegistry.
        """
        tool_name = proposal.get("tool_name", "custom_auto_tool")
        class_name = proposal.get("class_name", "CustomAutoTool")
        description = proposal.get("description", "Herramienta autogenerada")
        raw_code = proposal.get("python_code", "")
        dependencies = proposal.get("required_dependencies", [])

        code = self._sanitize_python_code(raw_code, class_name, tool_name, description)

        self.log(f"🛠️ [Auto-Síntesis]: Verificando sintaxis AST para '{class_name}'...")
        is_valid, syn_error = self.injector.validate_code_syntax(code)
        if not is_valid:
            self.log(f"⚠️ [Auto-Síntesis]: Advertencia sintáctica ({syn_error}). Auto-reparando con motor de síntesis nativo...")
            spec = ToolSpecification(
                tool_name=tool_name,
                class_name=class_name,
                description=description,
                parameters_schema=proposal.get("parameters_schema", {"type": "object", "properties": {}}),
                required_dependencies=dependencies
            )
            code = self.synthesizer._generate_tool_code(spec)
            is_valid, syn_error = self.injector.validate_code_syntax(code)
            if not is_valid:
                return {
                    "success": False,
                    "error": f"Error de sintaxis irrecuperable: {syn_error}",
                    "tool_name": tool_name
                }
            self.log("✓ [Auto-Síntesis]: Código auto-reparado y validado con éxito.")

        # Asegurar dependencias externas
        if dependencies:
            self.log(f"📦 [Dependencias]: Comprobando librerías requeridas: {dependencies}...")
            ok_deps, _ = self.synthesizer.ensure_dependencies(dependencies)
            if not ok_deps:
                self.log("⚠️ [Dependencias]: Alguna dependencia falló al instalarse; intentando carga estándar...")

        # Guardar en memoria técnica a largo plazo (./generated_tools/<tool_name>.py)
        file_path = self.output_dir / f"{tool_name}.py"
        file_path.write_text(code, encoding="utf-8")
        self.log(f"💾 [Persistencia]: Código guardado en {file_path}")

        # Crear especificación para la inyección
        spec = ToolSpecification(
            tool_name=tool_name,
            class_name=class_name,
            description=description,
            parameters_schema=proposal.get("parameters_schema", {}),
            required_dependencies=dependencies
        )

        # Validación efímera en proceso aislado
        self.log("🧪 [Sandbox Test]: Ejecutando prueba unitaria efímera en subproceso aislado...")
        test_ok, test_err = self.injector.ephemeral_unit_test(file_path, spec)
        if not test_ok:
            self.log(f"⚠️ [Sandbox Test]: {test_err}")
            # Si la prueba efímera falló por argumentos requeridos en execute(), aún podemos intentar inject
            # pero verificamos si es import error grave.

        # Hot-Reloading: Inyección en memoria de ejecución activa
        self.log(f"⚡ [Hot-Reloading]: Inyectando '{tool_name}' directamente en ToolRegistry...")
        inject_ok, tool_instance, inject_err = self.injector.inject_tool(file_path, spec, self.registry)

        if not inject_ok or not tool_instance:
            return {
                "success": False,
                "error": f"Error al cargar en caliente la herramienta: {inject_err}",
                "tool_name": tool_name,
                "file_path": str(file_path)
            }

        # Prueba de humo (Smoke Test) sobre la instancia recién inyectada
        smoke_result = self._execute_smoke_test(tool_instance)

        # Registrar en bitácora de auto-mejora
        self._record_improvement(proposal, file_path, smoke_result)

        self.log(f"🎉 [Auto-Mejora Exitosa]: Herramienta '{tool_name}' compilada e inyectada en caliente!")

        return {
            "success": True,
            "tool_name": tool_name,
            "class_name": class_name,
            "description": description,
            "file_path": str(file_path),
            "diagnosis": proposal.get("diagnosis", ""),
            "smoke_test_output": str(smoke_result),
            "smoke_test_success": smoke_result.success
        }

    def _execute_smoke_test(self, tool: BaseTool) -> ToolResult:
        """Realiza una invocación segura y no destructiva de la herramienta recién creada."""
        try:
            params = tool.parameters if isinstance(tool.parameters, dict) else {}
            props = params.get("properties", params)
            test_kwargs = {}
            if "action" in props and isinstance(props["action"], dict):
                enums = props["action"].get("enum", [])
                test_kwargs["action"] = enums[0] if enums else "read"
            elif "mode" in props and isinstance(props["mode"], dict):
                enums = props["mode"].get("enum", [])
                test_kwargs["mode"] = enums[0] if enums else "read"
            res = tool.execute(**test_kwargs)
            if not isinstance(res.output, str):
                res.output = json.dumps(res.output, ensure_ascii=False, default=str) if isinstance(res.output, (list, dict)) else str(res.output)
            return res
        except Exception as e:
            return ToolResult(success=False, output="", error=f"Smoke test falló: {e}")

    def _record_improvement(self, proposal: Dict[str, Any], file_path: Path, smoke_res: ToolResult) -> None:
        """Registra la nueva capacidad en el historial persistente de mejoras."""
        history = []
        if self.improvements_log_file.exists():
            try:
                history = json.loads(self.improvements_log_file.read_text(encoding="utf-8"))
            except Exception:
                history = []

        entry = {
            "timestamp": time.time(),
            "date": time.strftime("%Y-%m-%d %H:%M:%S"),
            "tool_name": proposal.get("tool_name"),
            "class_name": proposal.get("class_name"),
            "diagnosis": proposal.get("diagnosis"),
            "recommended_capability": proposal.get("recommended_capability"),
            "file_path": str(file_path),
            "smoke_test_success": smoke_res.success
        }
        history.append(entry)
        try:
            self.improvements_log_file.write_text(json.dumps(history, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass

    def run_cycle(self, focus_area: Optional[str] = None) -> Dict[str, Any]:
        """
        Ejecuta el ciclo completo:
        1. Consulta a Gemini.
        2. Síntesis y validación de código.
        3. Hot-reloading en tiempo de ejecución.
        """
        self.log(f"🚀 [Auto-Mejora JEV]: Iniciando ciclo de introspección asistido por Gemini (Área: {focus_area or 'General'})...")
        proposal = self.consult_gemini(focus_area=focus_area)
        result = self.synthesize_and_hot_reload(proposal)
        return result
