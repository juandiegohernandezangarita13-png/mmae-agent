from core.macro_engine import MacroEngine
from core.micro_engine import MicroEngine

def run_mmae_agent(prompt: str):
    print("🚀 Iniciando MMAE (Macro-Micro Agent Engine)...")
    
    # Inicializar los motores apuntando al backend local (ej. llama.cpp / vLLM)
    macro = MacroEngine(api_base_url="http://localhost:8000/v1")
    micro = MicroEngine(api_base_url="http://localhost:8000/v1")
    
    print("📋 [Fase 1] Generando esqueleto macro...")
    skeleton_data = macro.generate_skeleton(prompt)
    print("Esqueleto generado con éxito.")
    
    print("⚙️ [Fase 2] Expandiendo detalles en fase micro y restaurando literales...")
    final_result = micro.expand_skeleton(skeleton_data)
    
    print("\n=== RESULTADO FINAL DEL AGENTE ===")
    print(final_result)
    return final_result

if __name__ == "__main__":
    # Ejemplo de prueba para tu agente
    sample_prompt = (
        "Crea un script en Python para procesar un archivo en "
        "/home/user/data/input.csv y maneja cualquier excepción de tipo FileNotFoundError."
    )
    run_mmae_agent(sample_prompt)
