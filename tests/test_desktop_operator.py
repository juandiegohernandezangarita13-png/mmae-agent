"""
Pruebas unitarias para la herramienta universal de control de aplicaciones y mecanografía en vivo.
"""
import sys
import os
from pathlib import Path

from jev.tools.desktop_app_operator import DesktopAppLiveOperatorTool
from skills.desktop_operator import DesktopLiveOperatorSkill
from jev.tools import build_default_registry


def test_desktop_app_operator_init():
    tool = DesktopAppLiveOperatorTool()
    assert tool.name == "desktop_app_live_type"
    assert "openscad" in tool.KNOWN_APPS
    assert "notepad" in tool.KNOWN_APPS
    assert "vscode" in tool.KNOWN_APPS


def test_resolve_openscad_path():
    tool = DesktopAppLiveOperatorTool()
    exe = tool._resolve_executable("openscad")
    # En esta laptop OpenSCAD está instalado
    assert exe is not None
    assert "openscad" in exe.lower()
    assert os.path.exists(exe)


def test_resolve_notepad_path():
    tool = DesktopAppLiveOperatorTool()
    exe = tool._resolve_executable("notepad")
    assert exe is not None
    assert "notepad" in exe.lower()


def test_registered_in_default_registry():
    registry, _ = build_default_registry()
    tool = registry.get("desktop_app_live_type")
    assert tool is not None
    assert isinstance(tool, DesktopAppLiveOperatorTool)


def test_skill_wrapper():
    skill = DesktopLiveOperatorSkill()
    # Si pasamos app o code vacíos, debe retornar error de validación sin fallar
    res = skill.live_type(app="", code="")
    assert res["success"] is False
    assert "Debes proporcionar" in res["error"]


if __name__ == "__main__":
    test_desktop_app_operator_init()
    print("[OK] test_desktop_app_operator_init pasado", flush=True)
    test_resolve_openscad_path()
    print("[OK] test_resolve_openscad_path pasado (OpenSCAD detectado en C:\\Program Files\\OpenSCAD\\openscad.exe)", flush=True)
    test_resolve_notepad_path()
    print("[OK] test_resolve_notepad_path pasado", flush=True)
    test_registered_in_default_registry()
    print("[OK] test_registered_in_default_registry pasado", flush=True)
    test_skill_wrapper()
    print("[OK] test_skill_wrapper pasado", flush=True)
    print("\nTODOS LOS TESTS DE DESKTOP LIVE OPERATOR PASARON CON EXITO.", flush=True)
