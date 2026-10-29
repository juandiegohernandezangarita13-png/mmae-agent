# MMAE (Macro-Micro Agent Engine)

Un motor de ejecución pragmático para agentes autónomos locales diseñado para romper la lentitud de la inferencia lineal mediante un flujo de dos fases (Macro-Estructura y Micro-Relleno), evitando la compresión destructiva y priorizando datos exactos (logs y rutas).

## Estructura
- `core/macro_engine.py`: Genera el esqueleto lógico y la estrategia global.
- `core/micro_engine.py`: Rellena los detalles de código y llamadas a herramientas.
- `utils/bypass.py`: Canal de alta fidelidad para rutas, errores y datos literales.
