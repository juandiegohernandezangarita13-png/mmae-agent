# 🧠 MMAE (Macro-Micro Autonomous Agent Engine)

**MMAE** es un motor de ejecución y agente autónomo de vanguardia para sistemas locales y distribuidos. Ha sido diseñado específicamente para romper la lentitud y las alucinaciones de la inferencia lineal mediante un flujo de ejecución de **dos fases desacopladas** (Estructura Macro y Relleno Micro), integrando un canal de **Literal Bypass de alta fidelidad**, una suite de herramientas avanzadas, y múltiples interfaces (consola interactiva, control remoto por Telegram y la compañera flotante de escritorio estilo Coucou).

---

## 🏗️ Arquitectura del Sistema

```
                       ┌────────────────────────────────────────┐
                       │           OBJETIVO DE USUARIO          │
                       │   (CLI, Telegram o Isla de Escritorio) │
                       └───────────────────┬────────────────────┘
                                           │
                                  [ Literal Bypass ]
                        (Aísla rutas, hashes, logs de error)
                                           │
                       ┌───────────────────▼────────────────────┐
                       │          FASE 1: MACRO-ENGINE          │
                       │   Generación de Esqueleto Lógico /     │
                       │          Desglose en Bloques           │
                       └───────────────────┬────────────────────┘
                                           │
                                    [ TaskPlanner ]
                               (Plan de subtareas atómicas)
                                           │
                       ┌───────────────────▼────────────────────┐
                       │          FASE 2: MICRO-ENGINE          │
                       │   Relleno Técnico + Llamada a Tools    │
                       │    (Restauración de Literales Exactos) │
                       └───────────────────┬────────────────────┘
                                           │
                               [ ReflectionLoop & AST ]
                                           │
                      ┌────────────────────┼────────────────────┐
                      │                    │                    │
            ┌─────────▼────────┐ ┌─────────▼────────┐ ┌─────────▼────────┐
            │   Terminal & OS  │ │ Vision & Img Gen │ │ Claude Code &    │
            │ (Filesystem, Git)│ │  (Moondream/CAD) │ │ Fast-Path Bypass │
            └──────────────────┘ └──────────────────┘ └──────────────────┘
```

---

## ✨ Características Principales

### 1. Inferencia Dual Macro-Micro
* **Fase Macro (`core/macro_engine.py`):** Modela el plan estratégico global y las subtareas sin desgastar tokens en código prematuro ni sufrir compresión destructiva de contexto.
* **Fase Micro (`core/micro_engine.py`):** Rellena los detalles minuciosos, escribe código validado con AST y emite llamadas estructuradas a herramientas.

### 2. Canal de Alta Fidelidad (Literal Bypass) (`utils/bypass.py`)
* Protege rutas de archivos (`C:\...`, `/var/...`), hashes criptográficos (Git, SHA) y fragmentos de logs o errores en consola reemplazándolos con tokens temporales (`__LITERAL_TOKEN_x__`).
* El LLM procesa la lógica sin distorsionar ni mutilar los datos literales, los cuales se restauran de forma 100% fidedigna en la ejecución final.

### 3. Núcleo Cognitivo y Resiliencia
* **Planificador (`core/planner.py`):** Supervisa el avance secuencial o DAG de cada subtarea.
* **Ciclo de Reflexión (`core/reflection_loop.py`):** Reintenta acciones fallidas con contexto enriquecido y previene bucles infinitos.
* **Evaluador AST (`core/evaluator.py`):** Validación previa de sintaxis de Python antes de cualquier despliegue.
* **Memoria Jerárquica y Persistencia (`core/memory.py`, `core/persistence.py`):** Base relacional SQLite para snippets y soluciones procedimentales, junto con instantáneas de estado en disco (`.mmae_state.json`).

### 4. Múltiples Interfaces de Control
* **CLI Autónomo e Interactivo (`main.py`):** Modos `--goal "..."` y consola interactiva estilo REPL con tablas de herramientas.
* **Isla Dinámica de Escritorio (`jev_desktop.py`):** Compañero flotante transparente y *topmost* basado en el diseño Coucou / Mochi:
  * Motor Canvas 2D Superellipsoid ($r(y) = (1 - |y|^{2.7})^{1/2.7}$) con seguimiento de ojos y parpadeo.
  * Cuadrícula compacta 2x2 de Mini-Mochis animados (`#2DD4BF`, `#F59E0B`, `#8B5CF6`, `#EF4444`).
  * Tarjeta de permisos interactiva con atajos de teclado (`Allow [Y]`, `Deny [N]`, `Always`).
  * Muelle de chat integrado (`bonjour Mochi`) y soporte para soltar archivos (Drag & Drop).
* **Bot de Telegram Remoto (`telegram_bot.py`):** Fast-Path determinista por expresiones regulares (latencia cero, 0 tokens) con derivación a inferencia cuando se requiere razonamiento profundo.

---

## 📁 Estructura del Repositorio

```
mmae-agent/
├── core/                       # Núcleo del motor autónomo
│   ├── macro_engine.py         # Fase 1: Esqueleto y arquitectura
│   ├── micro_engine.py         # Fase 2: Relleno técnico y herramientas
│   ├── agent.py                # Orquestador MMAEAutonomousAgent & AgentCore
│   ├── planner.py              # Planificador de tareas y desgloses
│   ├── memory.py               # Memoria de ejecución y memoria jerárquica
│   ├── reflection_loop.py      # Bucle de reintentos y reflexión
│   ├── persistence.py          # Serialización y carga de estado
│   ├── evaluator.py            # Validador sintáctico AST y auditoría
│   ├── executor.py             # Ejecutor de acciones y llamadas a tools
│   └── fast_path.py            # Despachador determinista 0 tokens
├── skills/                     # Registro de herramientas y capacidades
│   ├── base.py                 # SkillRegistry y decoradores
│   ├── terminal.py             # Ejecución de comandos en shell con timeout
│   ├── filesystem.py           # Lectura/escritura segura en workspace
│   ├── git_ops.py              # Operaciones de Git (status, diff, commit)
│   ├── system_monitor.py       # Métricas de CPU, RAM, disco y SO
│   └── web.py                  # Peticiones HTTP seguras
├── utils/                      # Utilidades transversales
│   ├── bypass.py               # Canal de apantallamiento de literales
│   ├── action_parser.py        # Parser de JSON y bloques de código
│   ├── logger.py               # Registro estructurado en consola
│   └── env_manager.py          # Gestión y captura de entorno
├── ui/                         # Interfaces de usuario
│   ├── island.py               # Puente nativo Win32/PyWebView de la isla
│   └── templates/              # HTML/Canvas de la Isla Mochi y Holograma
├── config.py                   # Configuración central unificada
├── main.py                     # Punto de entrada CLI
├── jev_desktop.py              # Lanzador de la Isla de escritorio
├── telegram_bot.py             # Bot de control remoto
├── requirements.txt            # Dependencias del proyecto
└── tests/                      # Suite de pruebas automatizadas
```

---

## 🚀 Puesta en Marcha

### 1. Instalación de dependencias
```bash
python -m venv .venv
source .venv/bin/activate  # En Linux/Mac
.venv\Scripts\activate     # En Windows

pip install -r requirements.txt
```

### 2. Configuración (`.env`)
Crea un archivo `.env` en la raíz (puedes basarte en `.env.example`):
```ini
MMAE_API_URL=http://localhost:8000/v1
MMAE_MODEL=local-model
MMAE_WORKSPACE=./workspace

# Opcional: Proveedores en la nube
OPENROUTER_API_KEY=tu_api_key_aqui
GEMINI_API_KEY=tu_api_key_aqui
TELEGRAM_BOT_TOKEN=tu_token_aqui
ALLOWED_TELEGRAM_USER_ID=tu_id_numerico
```

### 3. Modos de Ejecución

#### Modo Autónomo Macro-Micro (CLI)
```bash
python main.py "Auditar el espacio en disco y listar los archivos del proyecto"
```

#### Modo Consola Interactiva
```bash
python main.py -i
```

#### Modo Isla Dinámica de Escritorio (Mochi Companion)
```bash
python main.py --desktop
# O directamente:
python jev_desktop.py
```

#### Modo Bot de Telegram
```bash
python telegram_bot.py
```

---

## 🧪 Pruebas Automatizadas
Ejecuta la suite completa de pruebas:
```bash
python -m unittest discover tests/
```
