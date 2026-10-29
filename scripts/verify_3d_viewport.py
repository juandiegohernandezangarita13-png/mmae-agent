"""
Verificación visual del Viewport 3D de JEV con Chromium headless (Playwright).

Uso:
    .\.venv\Scripts\python.exe scripts\verify_3d_viewport.py

Renderiza la escena del engranaje de demostración y guarda capturas en
data/screenshots/. Falla con código 1 si Three.js no monta el lienzo o si la
escena no se proyecta.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from jev.tools.custom.skill_cad_mesh import ParametricCadMeshTool  # noqa: E402


def build_scene() -> dict:
    tool = ParametricCadMeshTool()
    result = tool.execute(
        model_type="spur_gear",
        name="Verify_Gear",
        parameters={"teeth": 22, "pitch_radius": 22, "thickness": 8, "bore_radius": 7,
                    "hub_radius": 10, "hub_height": 6, "lightening_holes": 4,
                    "hole_radius": 2.8, "hole_circle_radius": 15},
        color="#00f0ff",
        quality="medium",
    )
    if not result.success:
        raise SystemExit(f"No se pudo generar la pieza: {result.error}")
    return result.data["scene"]


def main() -> int:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("Playwright no está instalado: pip install playwright && playwright install chromium")
        return 1

    scene = build_scene()
    html_uri = (ROOT / "jev" / "ui" / "templates" / "jarvis.html").resolve().as_uri()
    out_dir = ROOT / "data" / "screenshots"
    out_dir.mkdir(parents=True, exist_ok=True)
    errors: list[str] = []

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=True,
            args=[
                "--use-gl=angle",
                "--use-angle=swiftshader",
                "--enable-unsafe-swiftshader",
                "--no-sandbox",
            ],
        )
        page = browser.new_page(viewport={"width": 1600, "height": 1000})
        page.on("pageerror", lambda exc: errors.append(f"pageerror: {exc}"))
        page.goto(html_uri, wait_until="load", timeout=60000)
        page.wait_for_function("() => !!window.renderer && !!window.dynamicGroup", timeout=30000)
        page.evaluate("(scene) => window.onRender3DScene(scene)", scene)
        page.wait_for_timeout(1200)
        stats = page.evaluate(
            "() => ({meshes: document.getElementById('hudCount').innerText,"
            " hud: document.getElementById('hudState').innerText,"
            " canvas: !!document.querySelector('#threeCanvasContainer canvas')})"
        )
        target = out_dir / "3d_viewport_check.png"
        page.locator("#threeCanvasContainer").screenshot(path=str(target))
        browser.close()

    print(json.dumps(stats, ensure_ascii=False))
    print(f"Captura: {target}")
    if errors:
        print("Errores de página:", errors[:5])
    if not stats.get("canvas") or stats.get("meshes") in ("0", 0, ""):
        print("FALLO: el Viewport no renderizó la malla.")
        return 1
    print("OK: malla proyectada en el Viewport 3D.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
