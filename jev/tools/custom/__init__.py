"""
Directorio para herramientas creadas dinámicamente o integradas a medida en JEV.

IMPORTANTE (auditoría): las importaciones de herramientas opcionales se realizan
de forma tolerante a fallos. Una dependencia ausente (numpy, scipy, git, playwright,
etc.) en UNA herramienta opcional NO debe impedir el arranque del agente completo.
Cada símbolo no disponible queda como ``None`` y la herramienta se omite del registro.
"""

import logging

logger = logging.getLogger(__name__)

_OPTIONAL_TOOLS = {
    "NetworkSensingTool": "jev.tools.custom.network_sensing",
    "OfflineVaultTool": "jev.tools.custom.offline_vault",
    "SafeSandboxTool": "jev.tools.custom.safe_sandbox",
    "ReverseHelperTool": "jev.tools.custom.reverse_helper",
    "ParametricCadMeshTool": "jev.tools.custom.skill_cad_mesh",
    "CombinatorialAnalyticsTool": "jev.tools.custom.skill_combinatorial_analytics",
    "RFAdsbTrackerTool": "jev.tools.custom.skill_rf_adsb",
    "MeshtasticGatewayTool": "jev.tools.custom.skill_meshtastic",
    "FrigateVisionBridgeTool": "jev.tools.custom.skill_frigate",
    "OdmPhotogrammetryTool": "jev.tools.custom.skill_odm",
    "OpenpilotTelemetryTool": "jev.tools.custom.skill_openpilot",
    "VoiceEngineTool": "jev.tools.custom.skill_voice_engine",
    "BrowserOperatorTool": "jev.tools.custom.skill_browser_use",
    "SkillHubManagerTool": "jev.tools.custom.skill_hub_manager",
    "QAAuditorTool": "jev.tools.custom.skill_qa_auditor",
    "AutoLaunchVideoTool": "jev.tools.custom.skill_video_creator",
    "RepoPlannerTool": "jev.tools.custom.skill_repo_planner",
    "SDLCSeniorTool": "jev.tools.custom.skill_sdlc_senior",
    "OSINTToolkitTool": "jev.tools.custom.skill_osint_toolkit",
    "WebDesignProTool": "jev.tools.custom.skill_web_design_pro",
    "ClaudeCodeTool": "jev.tools.custom.skill_claude_code",
}

import importlib as _importlib

for _symbol, _module in _OPTIONAL_TOOLS.items():
    try:
        globals()[_symbol] = getattr(_importlib.import_module(_module), _symbol)
    except Exception as _exc:  # ImportError, binario ausente, API incompatible...
        globals()[_symbol] = None
        logger.warning(
            "Herramienta opcional '%s' no disponible (%s: %s). El resto del runtime continúa.",
            _symbol, type(_exc).__name__, _exc,
        )

__all__ = [
    "NetworkSensingTool",
    "OfflineVaultTool",
    "SafeSandboxTool",
    "ReverseHelperTool",
    "ParametricCadMeshTool",
    "CombinatorialAnalyticsTool",
    "RFAdsbTrackerTool",
    "MeshtasticGatewayTool",
    "FrigateVisionBridgeTool",
    "OdmPhotogrammetryTool",
    "OpenpilotTelemetryTool",
    "VoiceEngineTool",
    "BrowserOperatorTool",
    "SkillHubManagerTool",
    "QAAuditorTool",
    "AutoLaunchVideoTool",
    "RepoPlannerTool",
    "SDLCSeniorTool",
    "OSINTToolkitTool",
    "WebDesignProTool",
    "ClaudeCodeTool",
]
