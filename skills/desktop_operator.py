"""
Skill de Operador de Escritorio en Vivo para el SkillRegistry de MMAE.
Permite a MMAE (Macro/Micro Engine) abrir aplicaciones como OpenSCAD, Notepad, VS Code,
enfocar la ventana y teclear directamente el código usando el teclado en tiempo real.
"""
from typing import Dict, Any, List, Optional
from jev.tools.desktop_app_operator import DesktopAppLiveOperatorTool


class DesktopLiveOperatorSkill:
    """Skill registrada en MMAE para control directo de teclado en aplicaciones de escritorio."""

    def __init__(self):
        self.tool = DesktopAppLiveOperatorTool()

    def live_type(
        self,
        app: str,
        code: str,
        description: str = "",
        new_document: bool = True,
        clear_existing: bool = False,
        typing_speed: float = 0.01,
        post_keys: Optional[List[str]] = None,
        wait_after_launch: float = 2.0,
        **kwargs
    ) -> Dict[str, Any]:
        """Ejecuta la apertura y tecleado en vivo en la aplicación."""
        res = self.tool.execute(
            app=app,
            code=code,
            description=description,
            new_document=new_document,
            clear_existing=clear_existing,
            typing_speed=typing_speed,
            post_keys=post_keys,
            wait_after_launch=wait_after_launch,
            **kwargs
        )
        return res.to_dict()
