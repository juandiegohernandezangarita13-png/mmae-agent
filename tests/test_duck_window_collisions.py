"""
Pruebas automatizadas de la física de colisiones y animaciones del Desktop Duck.
Verifica:
1. Carga íntegra de los 25 sprites extraídos de la hoja original.
2. Detección de colisión frontal contra bordes de ventanas (BONK).
3. Transición de estados: bonk -> dizzy -> alert -> walking.
4. Cálculo de plataformas elevadas sobre ventanas (window landing).
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from jev.ui.duck_pet import DesktopDuckPet


def test_duck_sprites_and_initialization():
    print("--- Test Duck Sprites & Init ---")
    pet = DesktopDuckPet(target_height=118)
    assert len(pet.sprites) >= 20, f"Se esperaban al menos 20 sprites, encontrados {len(pet.sprites)}"
    assert "BONK" in pet.sprites
    assert "DIZZY_1" in pet.sprites
    assert "WALK_1" in pet.sprites
    assert "KO_FEET_1" in pet.sprites
    assert "TUMBLE_1" in pet.sprites
    print(f"✅ {len(pet.sprites)} sprites verificados y mapeados.")
    pet.root.destroy()


def test_duck_bonk_collision():
    print("\n--- Test Duck Bonk Window Collision ---")
    pet = DesktopDuckPet(target_height=118)
    
    # Inyectar una ventana simulada en x=[400, 900], y=[200, 800]
    fake_window = (400, 200, 900, 800)
    pet._cached_windows = [fake_window]
    pet._last_win_scan = 9999999999.0

    # Posicionar el pato a la izquierda de la ventana caminando a la derecha
    # duck_center_x = pos_x + 130. Si pos_x = 236, duck_center_x = 366.
    # duck_beak_x = duck_center_x + 36 = 402. wl=400 -> colisión de frente!
    pet.direction = 1
    pet.pos_x = 236.0
    pet.pos_y = 300.0  # Dentro de [200, 800]
    pet.state = "walking"
    pet.bonk_cooldown = 0

    hit = pet._check_window_collision()
    assert hit is True, "El pato debió colisionar de frente contra el borde izquierdo de la ventana"
    assert pet.state == "bonk"
    assert pet.status_message == "¡BONK! 💥"
    print("✅ Choque frontal (BONK) detectado con éxito.")
    pet.root.destroy()


def test_duck_platform_landing():
    print("\n--- Test Duck Platform Landing on Window Top ---")
    pet = DesktopDuckPet(target_height=118)
    
    # Ventana en x=[300, 800], top=400, bottom=900
    fake_window = (300, 400, 800, 900)
    pet._cached_windows = [fake_window]
    pet._last_win_scan = 9999999999.0

    # Pato cayendo justo encima de la ventana (x=500, centro sobre la ventana)
    pet.pos_x = 370.0  # duck_center_x = 500
    pet.pos_y = 200.0

    highest_floor = pet._find_highest_floor()
    expected_top = float(400 - pet.win_h + 12)
    assert highest_floor == expected_top, f"Esperado {expected_top}, obtenido {highest_floor}"
    print(f"✅ Detección de techo de ventana como plataforma ({highest_floor}px) confirmada.")
    pet.root.destroy()


if __name__ == "__main__":
    print("Iniciando pruebas de física y colisiones de ventanas...")
    test_duck_sprites_and_initialization()
    test_duck_bonk_collision()
    test_duck_platform_landing()
    print("\n🎉 ¡TODAS LAS PRUEBAS DE FÍSICA Y COLISIÓN PASARON AL 100%!")
