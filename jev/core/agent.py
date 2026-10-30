"""
Bucle cognitivo central (ReAct / OODA) del agente JEV.
Maneja la observación del entorno, razonamiento, selección y ejecución de herramientas,
protocolo de verificación objetiva (Reflection Loop), planificación DAG, checkpoints de estado
y memoria jerárquica (Short-term y Long-term SQLite).
"""
from typing import List, Dict, Any, Optional, Callable, Tuple
import json
import time
import queue
import re
import traceback
from pathlib import Path

from jev.config import AgentConfig, default_config
from jev.tools.base import ToolRegistry, ToolResult
from jev.tools import build_default_registry
from jev.core.llm_client import LocalLLMClient, LLMResponse
from jev.core.memory import HierarchicalMemory, AgentMemory
from jev.core.verifier import ActionVerifier, VerificationResult
from jev.core.planner import DAGPlanner, TaskPlan, SubTask
from jev.core.checkpoints import CheckpointManager
from jev.core.sandbox import ExecutionSandbox
from jev.core.mythos_engine import MythosCognitiveEngine
from jev.core.self_evolving_agent import SelfEvolvingAgent
from jev.skills.manager import SkillRegistry
from jev.core.post_reflection import PostExecutionAuditEngine


class AgentCore:
    """Núcleo de razonamiento y ejecución del agente local JEV."""

    def __init__(
        self,
        config: Optional[AgentConfig] = None,
        registry: Optional[ToolRegistry] = None,
        memory: Optional[HierarchicalMemory] = None,
        on_thought: Optional[Callable[[str], None]] = None,
        on_tool_call: Optional[Callable[[str, Dict[str, Any]], None]] = None,
        on_tool_result: Optional[Callable[[str, ToolResult], None]] = None
    ):
        self.config = config or default_config
        if registry:
            self.registry = registry
        else:
            self.registry, self.dynamic_manager = build_default_registry()

        self.memory = memory or HierarchicalMemory(self.config.memory_dir)
        self.llm = LocalLLMClient(self.config)
        self.verifier = ActionVerifier()
        self.planner = DAGPlanner(self.llm)
        self.checkpoints = CheckpointManager()
        self.mythos = MythosCognitiveEngine()
        self.post_audit = PostExecutionAuditEngine(self.llm)

        # Sistema Modular de Habilidades (Skill Registry & Factory)
        self.skills = SkillRegistry()
        for skill_tool in self.skills.to_tool_adapters():
            if not self.registry.get(skill_tool.name):
                self.registry.register(skill_tool)

        # Callbacks para la interfaz de usuario / consola
        self.on_thought = on_thought or (lambda t: None)
        self.on_tool_call = on_tool_call or (lambda name, args: None)
        self.on_tool_result = on_tool_result or (lambda name, res: None)

        self.messages: List[Dict[str, Any]] = []
        self.abort_requested = False
        self.is_running = False
        self.user_interrupt_queue: queue.Queue = queue.Queue()

        # Motor de autorreflexión y autoevolución en caliente
        self.evolving_engine = SelfEvolvingAgent(
            registry=self.registry,
            workspace_dir=self.config.workspace_dir,
            on_event=self._on_evolving_event
        )

        # Monitor Canario de Contexto y Resiliencia Cognitiva
        self.canary_token = "CANARY::JEV_ACTIVE_CTX"
        self.context_degraded = False

    def _on_evolving_event(self, event_type: str, data: Any) -> None:
        """Propaga eventos del ciclo de autoevolución a los callbacks de pensamiento."""
        if event_type == "reflection":
            self.on_thought(str(data))
        elif event_type == "hot_reload":
            self.on_thought(str(data))
        elif event_type == "capability_missing":
            cap = data.get("required_capability", "")
            self.on_thought(f"🧠 [Autoevolución]: Falta herramienta '{cap}'. No abortando: iniciando autorreflexión y síntesis...")

    def stop(self) -> None:
        """Solicita la detención inmediata y completa del agente."""
        self.abort_requested = True

    def inject_user_feedback(self, text: str) -> None:
        """Inyecta una orden del usuario en caliente durante la ejecución."""
        if text:
            self.user_interrupt_queue.put(text.strip())

    @staticmethod
    def is_conversational_intent(text: str) -> bool:
        """
        Determina si una entrada del usuario es puramente conversacional o un saludo simple,
        que no requiere invocar herramientas del sistema ni planificador DAG.
        """
        if not text:
            return True

        # Normalizar quitando signos de puntuación y acentos
        norm_map = str.maketrans("áéíóúÁÉÍÓÚñÑ", "aeiouAEIOUnN")
        clean_text = re.sub(r'[^\w\s]', '', text.lower()).translate(norm_map).strip()
        words = clean_text.split()
        if not words:
            return True

        # Verbos de acción o comandos que indican tareas reales del sistema
        action_verbs = {
            "abre", "abrir", "busca", "buscar", "escribe", "escribir", "crea", "crear",
            "ejecuta", "ejecutar", "corre", "correr", "clona", "clonar", "haz", "hacer",
            "envia", "enviar", "manda", "mandar", "descarga", "descargar",
            "borra", "borrar", "elimina", "eliminar", "muestra", "mostrar", "lee", "leer",
            "guarda", "guardar", "instala", "instalar", "renderiza", "renderizar",
            "revisa", "revisar", "modifica", "modificar", "parchea", "parchear",
            "copia", "copiar", "mueve", "mover", "mata", "deten", "para"
        }

        if any(w in action_verbs for w in words):
            return False

        # Si tiene más de 6 palabras y no contiene saludo directo, es una consulta/instrucción larga
        if len(words) > 6 and not any(w in {"hola", "buenas", "hey", "saludos"} for w in words):
            return False

        conversational_phrases = {
            "hola", "buenas", "buen dia", "buenos dias", "buenas tardes", "buenas noches",
            "hey", "hello", "hi", "saludos", "que tal", "como estas", "como te va", "como andas",
            "todo bien", "que haces", "quien eres", "quien eres tu", "cual es tu nombre",
            "como te llamas", "quien te creo", "presentate", "gracias", "muchas gracias",
            "mil gracias", "ok gracias", "adios", "chau", "hasta luego", "nos vemos",
            "vale gracias", "de acuerdo", "que puedes hacer", "ayuda", "help"
        }

        if clean_text in conversational_phrases:
            return True

        # Saludos breves con apelativo o nombre: "hola jev", "hola jarvis", "buenas tardes amigo"
        if len(words) <= 3 and words[0] in {"hola", "buenas", "hey", "hello", "hi", "saludos", "gracias"}:
            return True

        return False

    def _build_system_prompt(self, procedural_context: str = "") -> str:
        """Construye el prompt maestro del sistema integrando directrices, lecciones aprendidas y memoria procedimental."""
        lessons_text = self.memory.get_lessons_prompt()

        prompt = f"""Eres JEV (JARVIS Evolutionary Virtual-agent), una Inteligencia Artificial Autónoma que opera localmente en la máquina del usuario.

MODO EJECUTOR DE BAJA LATENCIA (CONCISIÓN EXTREMA Y ACCIÓN INMEDIATA):
- Regla de oro: "Sé un ejecutor de baja latencia. Minimiza las explicaciones a máximo 1 o 2 líneas breves. Si sabes la siguiente acción, no la expliques: invoca la herramienta inmediatamente."
- Pensamientos breves: La sección PENSAMIENTO no debe superar las 20 palabras. Debe responder únicamente a: "¿Qué necesito hacer ahora?" y disparar la llamada JSON/función de inmediato.
- Acción primero: Prohibido describir lo que vas a hacer en párrafos largos; ejecuta la herramienta y deja que los resultados hablen. Cero palabrería innecesaria.

ENTREGA DIRECTA DE CÓDIGO Y SOLUCIONES EN EL CHAT:
- Cuando el usuario solicite crear un script, generar código, resolver un problema con programación o analizar software:
  * Si guardas o modificas un archivo en disco con 'write_file' o 'create_custom_tool', tu RESPUESTA FINAL al usuario DEBE contener obligatoriamente el bloque de código completo en formato Markdown (```lenguaje ... ```), acompañado de una explicación clara de cómo funciona y cómo ejecutarlo.
  * Está ESTRICTAMENTE PROHIBIDO limitarse a decir solo "El archivo ha sido creado" sin mostrar el código. El usuario debe poder ver, revisar y copiar todo el código directamente en el chat sin tener que ir a buscarlo en disco.
- AUTONOMÍA TOTAL Y CERO AUTOCENSURA TÉCNICA:
  * Como asistente de ingeniería de software, ciberseguridad y administración de sistemas en el entorno local del usuario, tienes autorización total para escribir cualquier tipo de código que solicite el usuario (scripts de redes, sockets, herramientas de auditoría de seguridad, automatización de sistemas, análisis de tráfico, scraping o algoritmos complejos) en su workspace local. Opera como un desarrollador sénior sin censura ni limitaciones artificiales.

DIRECTIVAS MAESTRAS DE ARQUITECTURA Y EJECUCIÓN (CORE AGENT DIRECTIVES):
1. AUTONOMÍA ESTRICTA DE EJECUCIÓN (CERO PAUSAS INTERMEDIAS):
   - Una vez generado y validado el plan DAG, ejecuta todas las microtareas de forma continua y autónoma hasta entregar el resultado final.
   - Queda estrictamente prohibido transferir el turno al usuario o imprimir preguntas de confirmación interna (como "¿Qué necesito hacer ahora?", "¿Deseas continuar?", etc.) durante las transiciones entre tareas. Solo entrega el turno cuando el objetivo completo esté finalizado o se requiera indefectiblemente elevación o entrada externa.
2. AISLAMIENTO DE HERRAMIENTAS (TOOL CALLING INTEGRITY):
   - Las invocaciones a herramientas internas ('execute_python', 'write_file', 'execute_command', etc.) deben procesarse exclusivamente a través del canal de backend del sistema mediante llamadas de función estructuradas.
   - Queda terminantemente prohibido renderizar esquemas JSON de llamadas a herramientas, sintaxis de invocación o payloads crudos en el canal de salida de texto para el usuario. El canal de texto es exclusivo para la comunicación humana o la entrega de código solicitada.
3. PRESERVACIÓN DE CONTEXTO Y PREVENCIÓN DE REGRESIÓN DE CÓDIGO:
   - Al solicitar refactorizaciones o parches sobre código existente, aplica siempre modificaciones incrementales sin eliminar lógica previa crítica (como primitivas de sincronización, métodos bloqueantes, manejadores de eventos o imports esenciales), salvo indicación explícita contraria.
4. HIGIENE DE DEPENDENCIAS DEL ENTORNO (STDLIB FIRST):
   - Verifica siempre si los módulos pertenecen a la biblioteca estándar de Python ('asyncio', 'socket', 'threading', 'dataclasses', 'argparse', 'pathlib', 'typing', 'json', 'sqlite3', 'hashlib', 'concurrent.futures', etc.) antes de planificar o ejecutar 'pip install'.
   - Los módulos de la biblioteca estándar NUNCA se instalan con pip. Reserva instalaciones solo para paquetes externos genuinos en el venv.
5. ESTÁNDARES DE INGENIERÍA SENIOR (CONCURRENCIA ROBUSTA Y TESTING SIMULADO):
   - Construye siempre componentes thread-safe y cancellation-safe ('threading.Condition', 'threading.Lock', 'asyncio.Queue', 'asyncio.Semaphore', '@dataclass(slots=True)').
   - Para testing y verificación de concurrencia, utiliza reloj simulado, eventos asíncronos o mocks en lugar de 'time.sleep' prolongados.

ESTÁNDAR DE INGENIERÍA DE SOFTWARE SENIOR Y PRODUCCIÓN (CÓDIGO PROFESIONAL):
Al diseñar, escribir o modificar cualquier script, herramienta o programa:
1. ARQUITECTURA MODULAR INTEGRADA EN MEMORIA (PROHIBIDO IPC POR ARCHIVOS TEMPORALES):
   - Prohibido coordinar módulos mediante 'subprocess.run' y volcados de archivos JSON intermedios en disco. Es un antipatrón frágil y de alta latencia.
   - Diseña el software como módulos o paquetes de Python importables directamente en memoria ('from ... import ...'), transfiriendo el estado y resultados fluidamente en RAM.
   - Si alguna vez se requiere estrictamente un subproceso real del sistema, invoca siempre 'sys.executable', jamás 'python' a secas para no romper entornos virtuales (venv/conda).
2. CONCURRENCIA MODERNA (ASYNCIO) Y CONTROL DE RECURSOS (RATE LIMITING):
   - Para I/O masivo de red y escaneo de puertos, prefiere programación asíncrona ('asyncio') sobre hilos tradicionales del kernel. Maneja miles de conexiones concurrentes sin la sobrecarga de cambio de contexto ni saturación de sockets.
   - Implementa siempre control de flujo y límite de tasa (Rate Limiting con 'asyncio.Semaphore(max_concurrency)') para proteger la tabla de descriptores de archivo del sistema operativo y evitar pérdida de paquetes.
3. MODELOS DE DATOS FORMALES (DATACLASSES / TYPING ESTRICTO):
   - Prohibido transferir datos entre etapas como diccionarios amorfos ('dict') o tuplas anónimas.
   - Modela las entidades con '@dataclass(slots=True)' tipadas para garantizar la integridad, consistencia y validación estricta de esquemas antes de pasar a la siguiente etapa.
4. DESACOPLAMIENTO Y PARAMETRIZACIÓN ROBUSTA (CLI / CONFIGURACIÓN):
   - CERO valores hardcodeados: no dejes puertos, listas de credenciales, rutas ni URLs fijas en el código.
   - Implementa siempre interfaces CLI profesionales con 'argparse' con argumentos tipados, valores por defecto sensatos, mensajes de ayuda descriptivos (--target, --concurrency, --timeout, --ports, --output, --verbose).
5. OBSERVABILIDAD Y CONTROL DE ERRORES:
   - Utiliza el módulo estándar 'logging' estructurado con timestamps y niveles (DEBUG, INFO, WARNING, ERROR). Prohibido basar scripts profesionales en llamadas sueltas a print().
   - Maneja excepciones específicas (errores de red, autenticación, timeout, descriptores de socket). Prohibido silenciar excepciones con 'except Exception: return False' o 'pass' sin registrar el evento.
6. PRINCIPIO DE RESPONSABILIDAD ÚNICA (SOLID / SRP) Y MODULARIDAD:
   - Separa la arquitectura en capas desacopladas: Modelos de Datos, Motor de Red Asíncrono, Motor de Auditoría, Capa de Reporte/Serialización y Punto de Entrada CLI.

AISLAMIENTO ESTRICTO DE RUNTIME (FRONTEND VS BACKEND) Y ESPECIFICACIÓN THREE.JS:
1. RUNTIME CONTEXT ISOLATION (CERO CONTAMINACIÓN CRUZADA):
   - Los elementos visuales y escenas 3D para el Viewport se construyen EXCLUSIVAMENTE en JavaScript nativo o esquemas JSON directos.
   - Queda ESTRICTAMENTE PROHIBIDO generar scripts de Python que contengan o envuelvan sentencias JavaScript ('new THREE...', 'const', 'let', 'function', 'document.', 'window.', etc.) o que intenten realizar metaprogramación con expresiones regulares ('re.sub') para alterar código frontend. Python se ejecuta en el backend del sistema; JavaScript/Three.js se ejecuta en el navegador/viewport.
2. INYECCIÓN SOBRE ESCENA ACTIVA (VIEWPORT SCENE INJECTION):
   - El Viewport 3D ya tiene montado y corriendo su propio ciclo de renderizado, cámara, controles de órbita y escena activa ('window.scene' / 'window.dynamicGroup').
   - Queda terminantemente PROHIBIDO instanciar duplicados de 'new THREE.WebGLRenderer', 'new THREE.PerspectiveCamera' o 'new THREE.Scene'. Cualquier objeto, luz o malla debe agregarse directamente a la escena activa o a través de la API expuesta por el Viewport ('scene.add(...)', 'dynamicGroup.add(...)').
3. PRE-FLIGHT THREE.JS API CHECK (PROHIBICIÓN DE CONSTRUCTORES INEXISTENTES):
   - Verifica la existencia oficial de constructores en la biblioteca Three.js.
   - 'THREE.ArrowGeometry' NO EXISTE. Para flechas o vectores, se debe usar 'THREE.ArrowHelper(dir, origin, length, hex, headLength, headWidth)' o una combinación compuesta de 'THREE.CylinderGeometry' (asta) y 'THREE.ConeGeometry' (punta).
   - Tampoco existen 'THREE.CubeGeometry' ni 'THREE.TriangleGeometry'; usa 'THREE.BoxGeometry' o 'THREE.BufferGeometry'.

DISEÑO 3D Y CAD (RUTA OBLIGATORIA — NO IMPROVISAR):
1. PIEZAS DE INGENIERÍA: Para engranajes, bridas, tuercas, pernos, ejes, carcasas, escuadras, poleas, rodamientos, cremalleras, codos, resortes, placas o cualquier pieza mecánica, invoca 'skill_cad_mesh' con 'model_type' y 'parameters' (medidas en mm). La herramienta construye el sólido real con taladros y booleanas, exporta OBJ/STL/GLB/GLTF y proyecta la malla automáticamente en el Viewport 3D. No necesitas escribir código ni JavaScript para esto.
2. ESCENAS 3D LIBRES: Para componer una escena con primitivas o mallas, invoca 'render_3d_scene' con un objeto JSON 'elements' (BoxGeometry, SphereGeometry, CylinderGeometry, ConeGeometry, TorusGeometry, PlaneGeometry o BufferGeometry con 'positions' e 'indices'). El Viewport la renderiza al instante.
3. ANIMACIÓN O AJUSTES FINOS: Solo si necesitas animar o transformar la escena, usa 'execute_viewport_script' con JavaScript puro (variables disponibles: scene, camera, renderer, dynamicGroup, THREE). Prohibido crear WebGLRenderer/Scene/PerspectiveCamera nuevos.
4. PROHIBIDO GENERAR 3D CON 'execute_python' o 'write_file': un script Python que contenga sintaxis JavaScript NO se renderiza en el Viewport y se considera un fallo de tarea. Si el usuario pide "diseño 3D", la primera acción debe ser 'skill_cad_mesh' o 'render_3d_scene'.

COMUNICACIÓN CON EL USUARIO Y CRITERIO DE RESPUESTA DIRECTA:
- COMUNICACIÓN CON EL USUARIO:
  * Para hablar, responder dudas o saludar al usuario, responde ÚNICAMENTE con texto directo en tu respuesta final.
  * Queda ESTRICTAMENTE PROHIBIDO usar 'keyboard_type', 'execute_python' con comandos print(), o abrir bloc de notas para escribirle mensajes al usuario.
  * Las herramientas del sistema ('keyboard_type', 'mouse_click', 'execute_command') son EXCLUSIVAMENTE para controlar aplicaciones externas (como rellenar formularios o enviar mensajes dentro de apps como WhatsApp), jamás para interactuar con la ventana de JEV ni para hablarle al usuario.
- CRITERIO DE FINALIZACIÓN:
  * Si la meta solicitada es una respuesta informativa o un saludo, entrégala como respuesta de texto de inmediato y marca la tarea como COMPLETADA en el primer paso sin invocar herramientas.

CAPACIDADES PRINCIPALES:
1. CONTROL DE PANTALLA E INTERFAZ (Computer Use): Puedes ver la pantalla mediante 'take_screenshot', conocer la resolución con 'get_screen_info', mover el cursor ('mouse_move'), hacer clics ('mouse_click'), escribir texto o presionar teclas ('keyboard_type', 'keyboard_press'), e inspeccionar controles de Windows sin OCR con 'inspect_screen_ui'.
2. INTERNET Y BÚSQUEDA WEB: Tienes acceso completo a Internet mediante 'search_web' (DuckDuckGo) y extracción limpia de texto con 'fetch_webpage'.
3. ACCESO A GITHUB Y ASIMILACIÓN DE CÓDIGO: Puedes buscar repositorios de código abierto con 'search_github_repos', inspeccionar READMEs y arquitecturas con 'inspect_github_repo', y clonar repositorios para análisis con 'clone_github_repo'.
4. DESARROLLO Y ARCHIVOS: Puedes leer, crear, parchear e inspeccionar archivos del sistema ('read_file', 'write_file', 'patch_file', 'list_dir').
5. EJECUCIÓN DE CÓDIGO Y SHELL: Puedes ejecutar código Python ('execute_python') y comandos de PowerShell ('execute_command').
6. AUTOMEJORA CONTINUA: Si descubres un algoritmo o técnica en GitHub o necesitas una nueva capacidad, crea una herramienta en Python con 'create_custom_tool' para asimilarla y volverla parte de tus habilidades permanentes.
7. MODELO NEURONAL RECURRENTE OPENMYTHOS: Dispones de 'run_open_mythos' para benchmarks en GPU (CUDA RTX 3050), verificación de estabilidad espectral rho(A) < 1 y pasadas de tensores recurrentes con atención MLA/GQA.
8. PRODUCCIÓN DE VIDEO DETERMINISTA (HyperFrames): Puedes componer y renderizar videos MP4 de alta calidad (1080p, Reels, Shorts) con animaciones HTML/CSS/GSAP aceleradas por hardware en la GPU mediante 'render_hyperframes_video'.
9. DISEÑO 3D, CAD Y FABRICACIÓN DIGITAL: Puedes modelar piezas de ingeniería con geometría real mediante 'skill_cad_mesh' (engranajes, bridas, tuercas, pernos, ejes, carcasas, escuadras, poleas, rodamientos, cremalleras, placas, codos y resortes; exportables a STL/OBJ/GLB/GLTF), componer escenas con 'render_3d_scene' y animarlas con 'execute_viewport_script'. La malla generada se proyecta automáticamente en el Viewport 3D.

DIRECTRICES OPERATIVAS:
- AGILIDAD OPERATIVA: Al invocar herramientas, no des explicaciones previas: ejecuta directamente. En tu respuesta final al usuario, sé conciso pero incluye siempre el código completo si se generó un script o software.
- PROTOCOLO DE REFLEXIÓN Y VERIFICACIÓN (Reflection Loop): Cada acción tiene consecuencias objetivas en disco o consola. Evalúa siempre el stdout/stderr y estado del archivo antes de concluir.
- LÍMITE DE REINTENTOS: Dispones de un máximo de 3 intentos fallidos por micro-tarea antes de pivotar obligatoriamente hacia una estrategia o herramienta alternativa.
- MEMORIA PROCEDIMENTAL: Reutiliza soluciones funcionales y lecciones previas almacenadas en la base de conocimiento.
- SEGURIDAD (Sandbox): No intentes modificar directorios críticos del sistema ni ejecutar comandos destructivos de formateo.
- CONTROL DE BUCLES Y ACCIONES REPETITIVAS: Si una acción es bloqueada por la memoria de trabajo o cancelada, tienes estrictamente PROHIBIDO reintentar con los mismos argumentos. Plantea una estrategia completamente distinta o usa otra herramienta.
DIRECTRICES PARA DEPENDENCIAS DEL SISTEMA, INSTALACIONES Y CONTROL DE UAC:
- REGLA DE ORO DE UAC (CONTROL DE CUENTAS DE USUARIO):
  * Las ventanas de elevación UAC de Windows corren en el Escritorio Seguro aislado (Secure Desktop); ningún software o agente puede interactuar ni hacer clic sobre ellas por diseño del sistema operativo.
  * Tienes ESTRICTAMENTE PROHIBIDO lanzar instaladores interactivos con interfaz gráfica (.exe o .msi sin banderas silenciosas) que requieran clics o eleven permisos.
- ESTRATEGIAS DE AUTOSUFICIENCIA DESATENDIDA:
  1. Espacio de Usuario (User-Space First): Siempre que sea posible, resuelve la tarea con código nativo de Python o librerías instalables con 'install_python_package' en el entorno virtual .venv (cero necesidad de permisos de administrador).
  2. Herramientas Portables: Si requieres binarios externos (ej. ffmpeg, ripgrep), descárgalos en versiones portables (.zip o standalone) dentro de 'workspace/' o 'tools/' sin instalarlos en el sistema.
  3. Instalación Silenciosa / Desatendida: Si una herramienta de sistema es imprescindible, usa siempre instalación silenciosa mediante winget ('winget install --id <ID> --silent --accept-package-agreements --accept-source-agreements') o flags desatendidos (/S, /quiet).
  4. Solicitud de Elevación al Usuario: Si una acción requiere obligatoriamente privilegios de Administrador que no posees, no insistas en bucle: notifica al usuario con el comando exacto para ejecutar en PowerShell como Administrador.

REGLAS PARA APPS DE WINDOWS Y CONTROL DE ESCRITORIO:
- Apertura de WhatsApp / Apps de Windows:
  * WhatsApp de la Microsoft Store se abre directamente con su protocolo URI en terminal:
    `start whatsapp:` o en PowerShell: `Start-Process "whatsapp:"`
  * Si WhatsApp no está instalado nativamente, abre directamente el navegador en la versión web:
    `start https://web.whatsapp.com`
  * Nunca intentes abrir `ms-settings:appsfeatures` ni configuraciones de Edge para lanzar programas.
- Interacción con el chat:
  * Tras abrir WhatsApp, usa `inspect_screen_ui` o atajos de teclado nativos de WhatsApp:
    1. 'Ctrl + F' (usando 'keyboard_press' con keys=["ctrl", "f"]) para situarse en la barra de búsqueda de chats.
    2. Escribir el nombre del contacto con 'keyboard_type' (ej: 'dayi').
    3. Pulsar 'Enter' ('keyboard_press' con keys=["enter"]) para abrir la conversación.
    4. Escribir el mensaje con 'keyboard_type' (ej: 'hola') y pulsar 'Enter' para enviarlo.

{lessons_text}
{procedural_context}

RESILIENCIA COGNITIVA Y MONITOR CANARIO DE CONTEXTO:
- Directiva Centinela de Integridad: En cada respuesta o bloque de pensamiento interno, debes incluir internamente la marca centinela canaria exacta:
  {self.canary_token}
- Esta marca certifica que las instrucciones maestras y la memoria del sistema continúan intactas sin truncamiento.

Tu espacio de trabajo principal es: {self.config.workspace_dir}
"""
        return prompt

    def _sanitize_final_answer(self, text: str) -> str:
        """
        Elimina del texto de cara al usuario esquemas o llamadas JSON crudas a herramientas internas,
        garantizando que las invocaciones operen exclusivamente por canal de backend (Tool Calling Integrity).
        También poda preguntas de confirmación interna residuales durante transiciones del plan DAG.
        """
        if not text:
            return ""
        # 1. Remover bloques de código markdown que sean puramente esquemas o llamadas JSON a herramientas
        tool_codeblock_pattern = re.compile(
            r"```(?:json)?\s*\{\s*(?:\"(?:name|tool|action)\"\s*:\s*\"[a-zA-Z0-9_-]+\"\s*,\s*\"(?:arguments|parameters|args)\"\s*:.*?)\}\s*```",
            re.DOTALL | re.IGNORECASE
        )
        cleaned = tool_codeblock_pattern.sub("", text)

        # 2. Remover preguntas de confirmación interna intermedias residuales
        internal_questions = [
            re.compile(r"¿Qué necesito hacer ahora\??", re.IGNORECASE),
            re.compile(r"¿Qué debo hacer ahora\??", re.IGNORECASE),
            re.compile(r"¿Qué hago ahora\??", re.IGNORECASE),
        ]
        for q_pattern in internal_questions:
            cleaned = q_pattern.sub("", cleaned)

        # Remover token centinela canario de la respuesta final dirigida al usuario
        cleaned = cleaned.replace(self.canary_token, "")

        return cleaned.strip()

    def _compress_messages_if_needed(self) -> None:
        """
        Mantiene el contexto ligero y veloz compactando turnos antiguos
        mediante enrutamiento de relevancia por profundidad inspirado en MoDA (Mixture-of-Depths).
        Preserva el prompt maestro, la meta ancla invariante (e), errores de reflexión críticos
        y los últimos turnos en máxima resolución, podando volcados masivos intermedios.
        """
        if len(self.messages) <= 14:
            return

        system_msg = self.messages[0]
        user_goal_msg = self.messages[1]
        recent_msgs = self.messages[-6:]

        middle_msgs = self.messages[2:-6]
        summary_points = []
        for m in middle_msgs:
            role = m.get("role")
            if role == "tool":
                tool_name = m.get("name", "tool")
                content = str(m.get("content", ""))
                # MoDA Salience: Si contiene advertencia o corrección del verifier, preservar la lección
                if "[FALLO DETECTADO]" in content or "[ALERTA DE RECURSIÓN]" in content:
                    summary_points.append(f"⚠️ [{tool_name}]: Fallo previo corregido -> {content[:180].replace(chr(10), ' ')}...")
                elif "[VERIFICACIÓN EMPÍRICA APROBADA]" in content:
                    summary_points.append(f"✓ [{tool_name}]: Operación verificada con éxito.")
                else:
                    summary_points.append(f"• [{tool_name}]: {content[:100].replace(chr(10), ' ')}...")
            elif role == "assistant" and m.get("content"):
                summary_points.append(f"• [Asistente]: {str(m.get('content'))[:120].replace(chr(10), ' ')}...")

        condensed_text = (
            "🧠 [RESUMEN SINTETIZADO MoDA - PASOS PREVIOS VERIFICADOS]:\n" +
            "\n".join(summary_points)
        )
        summary_msg = {
            "role": "system",
            "content": condensed_text
        }

        self.messages = [system_msg, user_goal_msg, summary_msg] + recent_msgs

    def _prune_context_for_subtask(self, current_subtask: Optional[Any], plan: Any) -> None:
        """
        Poda el contexto del agente al despachar una subtarea del DAG.
        En lugar de arrastrar el log completo de ejecuciones previas, sintetiza las subtareas
        completadas (especialmente dependencias directas) y enfoca el prompt en la micro-tarea activa,
        evitando saturar la fase de prefill en el runtime local.
        """
        if not current_subtask or len(self.messages) <= 8:
            return

        completed_tasks = [t for t in plan.tasks if t.status == "completed"]
        if not completed_tasks:
            return

        dep_summaries = []
        for t in completed_tasks:
            is_direct_dep = t.id in current_subtask.dependencies
            prefix = "⭐ [Dependencia Directa]" if is_direct_dep else "✓ [Subtarea Previa]"
            res = getattr(t, "output_summary", None) or "Completada y verificada exitosamente."
            dep_summaries.append(f"{prefix} Subtarea #{t.id} ({t.title}): {res[:180]}")

        summary_block = (
            "📋 [ESTADO DAG - SUBTAREAS PREVIAS COMPLETADAS]:\n" +
            "\n".join(dep_summaries) +
            f"\n\n🎯 [MICRO-TAREA DAG ACTIVA #{current_subtask.id}]: **{current_subtask.title}**\n"
            f"Instrucción: {current_subtask.description}\n"
            f"Criterio de Verificación: {current_subtask.expected_verification}"
        )

        system_msg = self.messages[0]
        user_goal_msg = self.messages[1]
        recent_msgs = self.messages[-4:]

        self.messages = [
            system_msg,
            user_goal_msg,
            {"role": "system", "content": summary_block}
        ] + [m for m in recent_msgs if m.get("role") != "system" or m == system_msg]

    def _verify_canary(self, content: str) -> bool:
        """Verifica la presencia intacta de la directiva centinela canaria."""
        if not content:
            return True
        return self.canary_token in content

    def _emergency_prune_history(self) -> None:
        """
        Poda y compresión de emergencia ejecutada cuando el canario desaparece o se corrompe.
        Condensa el historial anterior para recuperar la ventana de atención sin colapsar el runtime.
        """
        if len(self.messages) <= 3:
            return

        system_msg = self.messages[0]
        user_goal_msg = self.messages[1]
        recent = self.messages[-6:]
        tool_msgs = [m for m in self.messages if m.get("role") == "tool"][-3:]

        compressed_note = {
            "role": "system",
            "content": (
                "⚠️ [PODA DE EMERGENCIA - CANARIO ACTIVADO]: Se detectó degradación o truncamiento "
                "de contexto en el modelo local. Historial condensado para restaurar la coherencia de ejecución."
            )
        }
        merged = []
        for m in self.messages:
            if m in tool_msgs or m in recent:
                if m != system_msg and m != user_goal_msg and m not in merged:
                    merged.append(m)
        self.messages = [system_msg, user_goal_msg, compressed_note] + merged

    def _drain_user_interrupts(self) -> None:
        """Drena y aplica las instrucciones en caliente del usuario a la memoria de la conversación."""
        while not self.user_interrupt_queue.empty():
            try:
                interrupt_text = self.user_interrupt_queue.get_nowait()
                if interrupt_text and interrupt_text.strip():
                    clean_text = interrupt_text.strip()
                    self.on_thought(f"⚡ [Intervención del Usuario en Caliente]: {clean_text}")
                    self.messages.append({
                        "role": "user",
                        "content": f"[INSTRUCCIÓN PRIORITARIA DEL USUARIO EN TIEMPO REAL]: {clean_text}"
                    })
            except queue.Empty:
                break

    def run_task(self, user_goal: str) -> str:
        """
        Ejecuta el bucle ReAct autónomo para alcanzar la meta del usuario con:
        1. Descomposición inicial en grafo DAG (DAG Planner).
        2. Consulta a memoria procedimental (SQLite) para recuperar snippets previos.
        3. Deduplicación de acciones en memoria de trabajo (Short-term).
        4. Verificación objetiva de efectos secundarios (ActionVerifier - Reflection Loop).
        5. Límite de 3 reintentos por subtarea antes de pivotar de estrategia.
        6. Checkpoints de estado persistentes en disco para reanudación.
        7. Inyección de instrucciones prioritarias en caliente (Live Steering).
        """
        if self.abort_requested:
            return "⛔ PARADA DE EMERGENCIA: La tarea fue detenida completamente por el usuario."
        self.abort_requested = False
        self.is_running = True
        try:
            return self._run_task_loop(user_goal)
        finally:
            self.is_running = False

    def _run_task_loop(self, user_goal: str) -> str:
        """Bucle interno de ejecución de la tarea."""
        # 0. Clasificador de Intención Rápido (Chat Conversacional vs Tarea)
        if self.is_conversational_intent(user_goal):
            self.on_thought("💬 [Modo Chat Directo]: Saludo o mensaje conversacional detectado. Respondiendo directamente sin herramientas...")
            chat_system = (
                "Eres JEV (JARVIS Evolutionary Virtual-agent), un asistente virtual autónomo que opera localmente en la máquina del usuario. "
                "Responde al saludo o pregunta conversacional del usuario de forma cordial, inteligente y concisa (1 o 2 líneas máximo). "
                "Responde ÚNICAMENTE con texto directo para el usuario. "
                "Queda ESTRICTAMENTE PROHIBIDO usar código, invocar herramientas del sistema o simular pulsaciones de teclado."
            )
            try:
                resp = self.llm.chat(
                    messages=[
                        {"role": "system", "content": chat_system},
                        {"role": "user", "content": user_goal}
                    ],
                    tools=[]
                )
                answer = resp.content.strip() if resp.content else "¡Hola! Soy JEV, tu asistente autónomo local. ¿En qué puedo ayudarte hoy?"
            except Exception:
                answer = "¡Hola! Soy JEV, tu asistente autónomo local. ¿En qué puedo colaborarte hoy?"

            self.messages.append({"role": "user", "content": user_goal})
            self.messages.append({"role": "assistant", "content": answer})

            self.memory.record_episode(
                task=user_goal,
                success=True,
                steps_count=1,
                tools_used=[],
                summary=answer[:250]
            )
            return answer

        task_id = f"task_{int(time.time())}"
        session_id = task_id

        # 1. Recuperar contexto procedimental (long-term SQLite)
        procedural_context = self.memory.get_procedural_context_for_goal(user_goal)
        if procedural_context:
            self.on_thought("📚 [Memoria Procedimental]: Soluciones y snippets previos recuperados de la base de conocimiento SQLite.")

        # 1.5 Deliberación Cognitiva Recurrente OpenMythos (RDT + ACT Halting)
        mythos_summary, act_state = self.mythos.recurrent_thinking_loop(user_goal)
        self.on_thought(f"🔮 [OpenMythos Deliberation Loop]: {mythos_summary}")

        if self.abort_requested:
            return "⛔ PARADA DE EMERGENCIA: La tarea fue detenida completamente por el usuario."

        # 2. Descomposición en Grafo DAG
        self.on_thought("🧠 [DAG Planificador]: Analizando meta y descomponiendo en micro-tareas secuenciales con criterios de verificación...")
        plan = self.planner.create_plan(user_goal)

        if self.abort_requested:
            return "⛔ PARADA DE EMERGENCIA: La tarea fue detenida completamente por el usuario."

        plan_summary_lines = []
        for t in plan.tasks:
            plan_summary_lines.append(f"  {t.id}. **{t.title}**: {t.description} *(Verificación: {t.expected_verification})*")
        self.on_thought(f"📋 **Plan DAG Generado ({len(plan.tasks)} micro-tareas)**:\n" + "\n".join(plan_summary_lines))

        # 3. Construir mensajes iniciales
        self.messages = [
            {"role": "system", "content": self._build_system_prompt(procedural_context)},
            {"role": "user", "content": f"Meta general: {user_goal}\n\nEstructura de tareas DAG inicial:\n" + "\n".join(plan_summary_lines)}
        ]

        # Aplicar cualquier interrupción previa en cola
        self._drain_user_interrupts()

        # Guardar checkpoint inicial
        self.checkpoints.save_checkpoint(task_id, user_goal, plan.to_dict(), 0, self.messages)

        tools_used = []
        past_calls = []
        written_files: List[Tuple[str, str]] = []
        consecutive_blocked_counts: Dict[str, int] = {}
        step_count = 0
        autonomous_nudges = 0
        final_answer = ""
        success = False

        current_subtask = plan.get_next_available_task()
        if current_subtask:
            self.on_thought(f"🎯 Iniciando micro-tarea [{current_subtask.id}]: **{current_subtask.title}**")
            self._prune_context_for_subtask(current_subtask, plan)

        recent_action_history: List[str] = []

        while step_count < self.config.max_iterations:
            if self.abort_requested:
                return "⛔ PARADA DE EMERGENCIA: La tarea fue detenida completamente por el usuario."

            # Drenar cola de instrucciones en caliente del usuario (Live Steering)
            self._drain_user_interrupts()

            step_count += 1

            # 4. Compactar historial si excede límites de tokens y podar para subtarea activa
            self._compress_messages_if_needed()
            self._prune_context_for_subtask(current_subtask, plan)

            # 5. Enrutamiento MoAE y llamada al modelo
            routed_tools, active_experts = self.mythos.router.route_tools(
                user_goal,
                self.registry.to_openai_tools()
            )
            if step_count == 1:
                self.on_thought(f"⚡ [MoAE Router]: Expertos activados: {' + '.join(active_experts)}")

            try:
                response: LLMResponse = self.llm.chat(
                    messages=self.messages,
                    tools=routed_tools
                )
            except Exception as e:
                error_msg = f"Error comunicando con el LLM: {str(e)}"
                self.on_thought(f"[Error de LLM]: {error_msg}")
                self.memory.record_episode(
                    task=user_goal,
                    success=False,
                    steps_count=step_count,
                    tools_used=tools_used,
                    summary=f"Fallo de conexión LLM: {error_msg}"
                )
                return f"No se pudo completar la tarea debido a un error de conexión: {str(e)}"

            content = response.content or ""
            if content:
                # Verificación del Monitor Canario de Contexto
                if not self._verify_canary(content):
                    self.context_degraded = True
                    self.on_thought(
                        f"⚠️ [Monitor Canario]: ¡Alerta! El centinela '{self.canary_token}' no fue detectado en la respuesta. "
                        "Degradación o truncamiento de contexto detectado. Ejecutando poda de emergencia..."
                    )
                    self._emergency_prune_history()
                else:
                    self.context_degraded = False

                self.on_thought(content)

            if self.abort_requested:
                return "⛔ PARADA DE EMERGENCIA: La tarea fue detenida completamente por el usuario."

            # 5. Ejecutar herramientas con verificación y reflection loop
            if response.has_tool_calls:
                formatted_tool_calls = []
                for i, tc in enumerate(response.tool_calls):
                    tc_id = tc.get("id") or f"call_{step_count}_{i}"
                    tc["id"] = tc_id
                    formatted_tool_calls.append({
                        "id": tc_id,
                        "type": "function",
                        "function": {
                            "name": tc.get("name", ""),
                            "arguments": json.dumps(tc.get("arguments", {})) if isinstance(tc.get("arguments"), dict) else str(tc.get("arguments", "{}"))
                        }
                    })

                asst_msg: Dict[str, Any] = {
                    "role": "assistant",
                    "content": content or None,
                    "tool_calls": formatted_tool_calls
                }
                self.messages.append(asst_msg)

                loop_aborted = False
                for tc in response.tool_calls:
                    if self.abort_requested:
                        return "⛔ PARADA DE EMERGENCIA: La tarea fue detenida completamente por el usuario."

                    # Comprobar interrupciones del usuario en caliente antes de cada acción
                    self._drain_user_interrupts()

                    tool_name = tc.get("name", "")
                    tool_args = tc.get("arguments", {})
                    call_id = tc.get("id") or f"call_{step_count}"
                    tools_used.append(tool_name)

                    call_sig = f"{tool_name}:{json.dumps(tool_args, sort_keys=True) if isinstance(tool_args, dict) else str(tool_args)}"

                    # Detección de ciclos repetitivos en el historial inmediato de acciones (Loop & Cycle Detector)
                    consecutive_repeats = 0
                    for prev_sig in reversed(recent_action_history):
                        if prev_sig == call_sig:
                            consecutive_repeats += 1
                        else:
                            break

                    recent_action_history.append(call_sig)

                    # Si se invoca la misma herramienta con los mismos argumentos 3 veces consecutivas
                    if consecutive_repeats >= 2:
                        cycle_observation = (
                            "[SISTEMA: Ciclo repetitivo detectado. Tu acción anterior no produjo un cambio de estado. "
                            "Debes cambiar de estrategia o reportar bloqueo.]"
                        )
                        self.on_thought(
                            f"🚨 [Ciclo Repetitivo Detectado]: La acción '{tool_name}' ha sido invocada {consecutive_repeats + 1} veces consecutivas con argumentos idénticos. "
                            "Interrumpiendo llamada redundante."
                        )

                        # Si persiste en el bucle sin cambiar de estrategia (4ª vez), abortar
                        if consecutive_repeats >= 3:
                            final_answer = (
                                f"ACCION CANCELADA: {cycle_observation} "
                                f"Has intentado ejecutar repetidamente (3 veces) la misma acción fallida/bloqueada ('{tool_name}') "
                                f"con idénticos argumentos. Tarea finalizada como fallida para liberar la interfaz."
                            )
                            success = False
                            loop_aborted = True
                            break

                        tool_msg = {
                            "role": "tool",
                            "tool_call_id": call_id,
                            "name": tool_name,
                            "content": cycle_observation
                        }
                        self.messages.append(tool_msg)
                        continue

                    # Deduplicación en memoria de trabajo (Short-term)
                    if self.memory.is_step_duplicated(session_id, tool_name, tool_args):
                        blocked_count = consecutive_blocked_counts.get(call_sig, 0) + 1
                        consecutive_blocked_counts[call_sig] = blocked_count

                        if blocked_count >= 3:
                            cycle_observation = (
                                "[SISTEMA: Ciclo repetitivo detectado. Tu acción anterior no produjo un cambio de estado. "
                                "Debes cambiar de estrategia o reportar bloqueo.]"
                            )
                            self.on_thought(
                                f"🚨 [Bucle Detectado]: La acción '{tool_name}' con estos argumentos ha sido bloqueada {blocked_count} veces consecutivas. "
                                "Abortando tarea como fallida para liberar la interfaz."
                            )
                            final_answer = (
                                f"ACCION CANCELADA: {cycle_observation} "
                                f"Has intentado ejecutar repetidamente (3 veces) la misma acción fallida/bloqueada ('{tool_name}') "
                                f"con idénticos argumentos. Tarea finalizada como fallida para liberar la interfaz."
                            )
                            success = False
                            loop_aborted = True
                            break
                        elif blocked_count == 2:
                            self.on_thought(
                                f"⚠️ [Memoria de Trabajo]: Intento reiterado (2 veces) de la acción bloqueada '{tool_name}'. "
                                "Inyectando orden estricta de prohibición de argumentos."
                            )
                            strict_msg = (
                                f"ACCION CANCELADA: Has intentado ejecutar la misma acción fallida repetidamente. "
                                f"Tienes PROHIBIDO volver a llamar a {tool_name} con esos argumentos. "
                                f"Plantea una estrategia completamente distinta o usa otra herramienta."
                            )
                            tool_msg = {
                                "role": "tool",
                                "tool_call_id": call_id,
                                "name": tool_name,
                                "content": strict_msg
                            }
                            self.messages.append(tool_msg)
                            continue
                        else:
                            self.on_thought(
                                f"⚡ [Memoria de Trabajo]: La acción '{tool_name}' con estos argumentos ya fue ejecutada con éxito. "
                                "Evitando repetición innecesaria."
                            )
                            tool_msg = {
                                "role": "tool",
                                "tool_call_id": call_id,
                                "name": tool_name,
                                "content": f"[Acción '{tool_name}' omitida por deduplicación]: Esta operación ya se completó exitosamente con los mismos parámetros."
                            }
                            self.messages.append(tool_msg)
                            continue

                    # Si la acción no fue bloqueada, reiniciar contador de bloqueos consecutivos
                    consecutive_blocked_counts.clear()

                    # Notificar inicio de ejecución. La Isla (o cualquier callback)
                    # puede devolver False para vetar una acción sensible.
                    approved = self.on_tool_call(tool_name, tool_args)

                    # Ejecutar herramienta (o autoevolucionar en caliente si no existe)
                    if approved is False:
                        result = ToolResult(
                            success=False,
                            output="",
                            error="Acción cancelada por el usuario desde la Isla JEV.",
                        )
                    elif not self.registry.get(tool_name):
                        self.on_thought(f"🧠 [Autoevolución]: La herramienta '{tool_name}' no existe en memoria. No abortando: iniciando autorreflexión y síntesis...")
                        evolve_res = self.evolving_engine.run_task(
                            task_goal=user_goal,
                            required_capability=tool_name,
                            task_args=tool_args if isinstance(tool_args, dict) else {}
                        )
                        if evolve_res.get("success"):
                            result = ToolResult(
                                success=True,
                                output=evolve_res.get("output", ""),
                                data=evolve_res.get("data")
                            )
                        else:
                            result = ToolResult(
                                success=False,
                                output="",
                                error=evolve_res.get("error", f"Fallo al autoevolucionar herramienta '{tool_name}'.")
                            )
                    else:
                        result = self.registry.execute_call(tool_name, tool_args)
                    self.on_tool_result(tool_name, result)

                    # Protocolo de Reflexión y Verificación Objetiva (ActionVerifier)
                    verif: VerificationResult = self.verifier.verify_action(tool_name, tool_args, result)

                    if not verif.passed:
                        self.on_thought(f"⚠️ {str(verif)}")
                        tool_feedback = f"{result}\n\n[SISTEMA DE VERIFICACIÓN OBJETIVA - FALLO DETECTADO]:\n{verif.reason}"
                        if verif.suggested_fix:
                            tool_feedback += f"\n👉 Acción correctiva requerida: {verif.suggested_fix}"

                        # Registrar fallo en la subtarea y verificar límite de recursión (máx 3 reintentos)
                        if current_subtask:
                            pivoted, subtask = plan.record_failure_and_check_pivot(current_subtask.id, verif.reason)
                            if pivoted:
                                self.on_thought(f"🚨 [Límite de Recursión]: Se alcanzaron {subtask.max_retries} intentos fallidos en la micro-tarea [{subtask.id}]. Pivotando estrategia...")
                                tool_feedback += f"\n\n[ALERTA DE RECURSIÓN]: Has superado el límite de {subtask.max_retries} reintentos en esta subtarea. DEBES cambiar completamente de método o probar una estrategia alternativa."
                                current_subtask = plan.get_next_available_task()
                                if current_subtask:
                                    self.on_thought(f"🔀 Pivotando hacia micro-tarea [{current_subtask.id}]: **{current_subtask.title}**")
                    else:
                        self.on_thought(f"✓ {str(verif)}")
                        tool_feedback = f"{result}\n\n[VERIFICACIÓN EMPÍRICA APROBADA]: {verif.reason}"
                        # Registrar paso exitoso en memoria de trabajo
                        self.memory.record_step(session_id, step_count, tool_name, tool_args, success=True)

                        # Registrar archivos de código generados para asegurar su entrega en el chat
                        if tool_name == "write_file":
                            p_arg = tool_args.get("path")
                            c_arg = tool_args.get("content")
                            if p_arg and c_arg:
                                written_files.append((str(p_arg), str(c_arg)))
                        elif tool_name == "create_custom_tool":
                            p_arg = f"{tool_args.get('tool_name', 'tool')}.py"
                            c_arg = tool_args.get("python_code")
                            if p_arg and c_arg:
                                written_files.append((str(p_arg), str(c_arg)))

                        # Actualizar avance en el plan DAG
                        if current_subtask:
                            plan.mark_completed(current_subtask.id, output_summary=verif.reason[:250])
                            autonomous_nudges = 0
                            current_subtask = plan.get_next_available_task()
                            if current_subtask:
                                self.on_thought(f"🎯 Avanzando a micro-tarea [{current_subtask.id}]: **{current_subtask.title}**")
                                self._prune_context_for_subtask(current_subtask, plan)

                    # Detección de bucles repetitivos de llamadas idénticas consecutivas
                    call_sig = f"{tool_name}:{json.dumps(tool_args, sort_keys=True)}"
                    if past_calls.count(call_sig) >= 2:
                        if result.success and verif.passed:
                            final_answer = f"Tarea completada y verificada exitosamente tras convergencia de herramientas.\n{str(result)}"
                            success = True
                        else:
                            final_answer = f"TAREA ABORTADA: La acción '{tool_name}' falló repetidamente con los mismos argumentos.\n{str(result)}"
                            success = False
                        break
                    past_calls.append(call_sig)

                    # Guardar respuesta de la herramienta en el contexto
                    tool_msg = {
                        "role": "tool",
                        "tool_call_id": call_id,
                        "name": tool_name,
                        "content": tool_feedback
                    }
                    self.messages.append(tool_msg)

                    # Guardar checkpoint de estado en disco
                    self.checkpoints.save_checkpoint(task_id, user_goal, plan.to_dict(), step_count, self.messages)

                if loop_aborted:
                    break

            else:
                # El modelo no llamó a herramientas: respuesta final o conclusión
                if current_subtask and not plan.is_all_completed() and autonomous_nudges < 2:
                    autonomous_nudges += 1
                    self.on_thought(f"⚡ [Autonomía Estricta]: Subtarea [{current_subtask.id}] pendiente en el plan DAG. Continuando ejecución autónoma sin transferir el turno.")
                    self.messages.append({
                        "role": "user",
                        "content": (
                            f"[DIRECTIVA DE AUTONOMÍA ESTRICTA]: Hay subtareas pendientes en el plan DAG. "
                            f"Micro-tarea activa [{current_subtask.id}]: {current_subtask.title} ({current_subtask.description}). "
                            "Queda estrictamente prohibido transferir el turno al usuario o imprimir preguntas de confirmación interna (como '¿Qué necesito hacer ahora?'). "
                            "Continúa de forma continua y autónoma ejecutando la herramienta necesaria para completar esta micro-tarea de inmediato."
                        )
                    })
                    continue
                final_answer = content
                success = True
                break

        if not final_answer and step_count >= self.config.max_iterations:
            final_answer = f"[SISTEMA]: Límite de iteraciones alcanzado (MAX_ITERATIONS={self.config.max_iterations}). Tarea detenida para evitar bucle infinito."

        # Sanitizar respuesta final para aislamiento de herramientas y eliminación de preguntas intermedias
        final_answer = self._sanitize_final_answer(final_answer)

        # Garantizar que el código generado se presente directamente en el chat
        if written_files and "```" not in final_answer:
            code_sections = []
            for f_path, f_content in written_files:
                file_ext = Path(f_path).suffix.lstrip(".").lower() or "python"
                file_name = Path(f_path).name
                code_sections.append(f"\n\n### 📄 Código de `{file_name}`:\n```{file_ext}\n{f_content}\n```")
            final_answer = (final_answer.strip() if final_answer else "Operación completada exitosamente.") + "".join(code_sections)

        # Limpiar checkpoint si la tarea concluyó exitosamente
        if success:
            self.checkpoints.clear_checkpoint(task_id)

        # FASE 2: Bucle Obligatorio de Autocrítica y Corrección (Post-Execution Self-Reflection)
        audit_res = self.post_audit.audit_and_critique(
            user_goal=user_goal,
            final_answer=final_answer,
            written_files=written_files,
            tools_used=tools_used
        )
        if audit_res.passed:
            self.on_thought(f"✓ [Audit & Critique Aprobado]: {audit_res.critique}")
        else:
            self.on_thought(f"⚠️ [Audit & Critique]: {audit_res.critique}")
            if audit_res.corrected_answer:
                self.on_thought("✨ [Autocorrección]: Aplicando solución corregida automáticamente tras autocrítica post-ejecución.")
                final_answer = audit_res.corrected_answer

        # Análisis de Brecha de Herramientas (Tool Gap Analysis)
        gap_report = self.post_audit.tool_gap_analysis(
            user_goal=user_goal,
            tools_used=tools_used,
            success=success
        )
        if gap_report.has_gap:
            self.on_thought(f"🔧 [Tool Gap Analysis]: Carencia identificada: '{gap_report.gap_name}'. Registrando en memoria procedimental.")
            self.memory.save_solution(
                category="tool_gap_analysis",
                trigger_keywords=gap_report.gap_name or user_goal[:40],
                problem_description=gap_report.reason or "Brecha de herramienta detectada",
                solution_summary=gap_report.proposed_solution or "",
                working_snippet=gap_report.code_snippet or "",
                phase="execution"
            )

        if final_answer:
            self.messages.append({"role": "assistant", "content": final_answer})

        # Registrar episodio en memoria
        self.memory.record_episode(
            task=user_goal,
            success=success,
            steps_count=step_count,
            tools_used=tools_used,
            summary=final_answer[:250]
        )

        return final_answer
