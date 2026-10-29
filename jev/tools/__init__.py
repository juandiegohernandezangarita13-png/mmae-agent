"""
Inicializador del módulo de herramientas y ensamblador del registro por defecto.
"""
from jev.tools.base import ToolRegistry, BaseTool, ToolResult
from jev.tools.screen import (
    ScreenInfoTool,
    ScreenCaptureTool,
    MouseClickTool,
    MouseMoveTool,
    KeyboardTypeTool,
    KeyboardPressTool,
    MouseScrollTool
)
from jev.tools.web import WebSearchTool, WebFetchTool
from jev.tools.filesystem import ReadFileTool, WriteFileTool, PatchFileTool, ListDirTool
from jev.tools.code_runner import PythonRunnerTool, ShellCommandTool, PackageManagerTool
from jev.tools.dynamic_loader import DynamicToolManager, CreateCustomTool
from jev.tools.github import (
    GitHubSearchReposTool,
    GitHubRepoInspectTool,
    GitHubCloneRepoTool,
    GitHubSkillAssimilatorTool
)
from jev.tools.system_info import SystemEnvironmentTool
from jev.tools.mythos_runner import OpenMythosRunnerTool
from jev.tools.video_generator import HyperFramesVideoTool
from jev.tools.smolvm_runner import SmolvmRunnerTool, SmolfileGeneratorTool
from jev.tools.ui_grounding import FindUIElementTool, ClickElementByTextTool
from jev.tools.ui_inspector import UIInspectorTool
from jev.tools.viewport import Render3DSceneTool, ExecuteViewportScriptTool
from jev.core.scheduler import ScheduleTaskTool, ListScheduledTasksTool
from jev.core.subagents import DelegateSubagentTool, SubagentOrchestrator
from jev.core.doctor import SystemDoctorTool, SystemDoctor

from typing import Optional, Any


def build_default_registry(config: Optional[Any] = None) -> tuple[ToolRegistry, DynamicToolManager]:
    """Crea y puebla el registro de herramientas con todas las capacidades por defecto."""
    registry = ToolRegistry()
    ws = config.workspace_dir if config else None

    # Herramientas de pantalla y GUI
    registry.register(ScreenInfoTool())
    registry.register(ScreenCaptureTool())
    registry.register(MouseClickTool())
    registry.register(MouseMoveTool())
    registry.register(KeyboardTypeTool())
    registry.register(KeyboardPressTool())
    registry.register(MouseScrollTool())

    # Herramientas de inspección de entorno
    registry.register(SystemEnvironmentTool(workspace_dir=ws))

    # Herramientas web
    registry.register(WebSearchTool())
    registry.register(WebFetchTool())

    # Herramientas de GitHub y asimilación de código abierto
    registry.register(GitHubSearchReposTool())
    registry.register(GitHubRepoInspectTool())
    registry.register(GitHubCloneRepoTool(workspace_dir=ws) if ws else GitHubCloneRepoTool())
    registry.register(GitHubSkillAssimilatorTool(workspace_dir=ws) if ws else GitHubSkillAssimilatorTool())

    # Herramientas de archivos
    registry.register(ReadFileTool(workspace_dir=ws))
    registry.register(WriteFileTool(workspace_dir=ws))
    registry.register(PatchFileTool(workspace_dir=ws))
    registry.register(ListDirTool(workspace_dir=ws))

    # Herramientas de código, shell y gestión de paquetes
    registry.register(PythonRunnerTool(workspace_dir=ws))
    registry.register(ShellCommandTool(workspace_dir=ws))
    registry.register(PackageManagerTool())
    registry.register(OpenMythosRunnerTool())
    registry.register(HyperFramesVideoTool(workspace_dir=ws) if ws else HyperFramesVideoTool())
    registry.register(SmolvmRunnerTool(workspace_dir=ws))
    registry.register(SmolfileGeneratorTool(workspace_dir=ws))

    # Generador y estructurador de artefactos web reactivos
    from jev.tools.skill_web_builder import WebBuilderTool
    registry.register(WebBuilderTool(workspace_dir=ws))

    # Control del Viewport 3D en vivo (escenas declarativas y scripts nativos)
    registry.register(Render3DSceneTool())
    registry.register(ExecuteViewportScriptTool())

    # Anclaje visual de UI y clics por etiqueta
    finder = FindUIElementTool(workspace_dir=ws)
    registry.register(finder)
    registry.register(ClickElementByTextTool(finder_tool=finder))
    registry.register(UIInspectorTool())

    # Tareas programadas en segundo plano
    registry.register(ScheduleTaskTool())
    registry.register(ListScheduledTasksTool())

    # Enjambre y delegación a subagentes en paralelo
    registry.register(DelegateSubagentTool(orchestrator=SubagentOrchestrator(base_registry=registry)))

    # Auditoría de salud y auto-reparación preventiva
    registry.register(SystemDoctorTool(doctor=SystemDoctor(workspace_dir=ws)))

    # Herramientas dinámicas y de automejora asistida por Gemini
    from jev.tools.gemini_improver import ConsultGeminiAndSelfImproveTool
    from jev.core.auto_improver import GeminiSelfImprover
    improver = GeminiSelfImprover(registry=registry, config=config)
    registry.register(ConsultGeminiAndSelfImproveTool(improver=improver, registry=registry, config=config))

    # Motor de edición atómica y staging Plandex
    from jev.tools.custom.skill_repo_planner import RepoPlannerTool
    registry.register(RepoPlannerTool(workspace_dir=ws))

    # Generador de vídeos promocionales de lanzamiento
    from jev.tools.custom.skill_video_creator import AutoLaunchVideoTool
    registry.register(AutoLaunchVideoTool(workspace_dir=ws))

    # Protocolo SDLC Senior con checkpoints y testing obligatorio
    from jev.tools.custom.skill_sdlc_senior import SDLCSeniorTool
    registry.register(SDLCSeniorTool())

    # Suite OSINT de Inteligencia Multi-Vector
    from jev.tools.custom.skill_osint_toolkit import OSINTToolkitTool
    registry.register(OSINTToolkitTool())

    # Motor de Diseño Web Anti-Genericidad Pro Max
    from jev.tools.custom.skill_web_design_pro import WebDesignProTool
    registry.register(WebDesignProTool(workspace_dir=ws))

    # Conector e Interfaz con Claude Code (Free-Claude-Code + OpenRouter)
    from jev.tools.custom.skill_claude_code import ClaudeCodeTool
    registry.register(ClaudeCodeTool(workspace_dir=ws))

    # Síntesis Visual de Alta Calidad (Pollinations FLUX / Fallback Local)
    from jev.tools.custom.skill_image_generator import ImageGeneratorTool
    registry.register(ImageGeneratorTool())

    # Reconocimiento Visual y Análisis Multimodal (Ollama moondream / Gemini / Cloud)
    from jev.tools.custom.skill_vision_recognizer import VisionRecognizerTool
    registry.register(VisionRecognizerTool())

    dynamic_mgr = DynamicToolManager(registry)
    registry.register(CreateCustomTool(dynamic_mgr))

    # Cargar herramientas existentes previamente creadas por el agente
    dynamic_mgr.load_all()

    return registry, dynamic_mgr
