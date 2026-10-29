# Catálogo de Herramientas Internas y Capacidades Autónomas

Este documento describe las 5 herramientas modulares desarrolladas e integradas localmente en el workspace (`./tools/`). Todas las herramientas están implementadas en código nativo de Python, sin dependencias externas obligatorias, y han sido validadas mediante pruebas unitarias automatizadas.

---

## 1. WiFi CSI / Presence Sensing (`./tools/wifi_sensing/`)
* **Propósito:** Inferencia de presencia y movimiento físico en un espacio mediante el análisis estadístico de perturbaciones electromagnéticas (varianza y multi-path fading) sobre la señal WiFi/RSSI, sin necesidad de cámaras.
* **Archivo principal:** [`./tools/wifi_sensing/analyzer.py`](file:///c:/Users/juand/OneDrive/Desktop/IA_Automejorable/tools/wifi_sensing/analyzer.py)
* **Prueba unitaria:** [`./tools/wifi_sensing/test.py`](file:///c:/Users/juand/OneDrive/Desktop/IA_Automejorable/tools/wifi_sensing/test.py) (4 tests OK)
* **Firma de llamada en Python:**
  ```python
  from tools.wifi_sensing.analyzer import WifiSignalAnalyzer

  analyzer = WifiSignalAnalyzer(variance_threshold=3.5)
  # Análisis sobre una serie temporal de lecturas RSSI o amplitudes CSI
  resultado = analyzer.detect_presence([-60.1, -54.2, -67.1, -58.0, -52.4])
  # Retorna: {"status": "PRESENCE_DETECTED" | "NO_MOTION", "confidence": float, "variance": float, ...}
  ```
* **Uso vía CLI:**
  ```bash
  python ./tools/wifi_sensing/analyzer.py --mode simulate --scenario motion
  python ./tools/wifi_sensing/analyzer.py --mode live --threshold 3.0
  ```

---

## 2. Offline Knowledge & Vault Engine (`./tools/offline_vault/`)
* **Propósito:** Base de conocimiento local y motor documental autónomo (estilo Kiwix/Nomad) para operar sin conexión a internet. Utiliza SQLite nativo con FTS5 (Full-Text Search) y ranking de relevancia BM25.
* **Archivo principal:** [`./tools/offline_vault/vault_engine.py`](file:///c:/Users/juand/OneDrive/Desktop/IA_Automejorable/tools/offline_vault/vault_engine.py)
* **Prueba unitaria:** [`./tools/offline_vault/test.py`](file:///c:/Users/juand/OneDrive/Desktop/IA_Automejorable/tools/offline_vault/test.py) (3 tests OK)
* **Firma de llamada en Python:**
  ```python
  from tools.offline_vault.vault_engine import OfflineVaultEngine

  engine = OfflineVaultEngine()
  # Ingestar manual, documento o snippet
  doc_id = engine.ingest(title="Guía", content="Texto largo...", category="docs", tags=["offline", "python"])

  # Búsqueda por texto completo (FTS5 con operadores booleanos)
  resultados = engine.query_vault("microvm OR sandbox", limit=5)
  # Retorna lista de diccionarios con: id, title, category, tags, snippet (con resaltado <b>), score
  ```
* **Uso vía CLI:**
  ```bash
  python ./tools/offline_vault/vault_engine.py ingest --title "Manual" --content "Contenido técnico..."
  python ./tools/offline_vault/vault_engine.py search "termino de busqueda"
  python ./tools/offline_vault/vault_engine.py stats
  ```

---

## 3. REA (Reverse Engineering Assistant) (`./tools/reverse_engineering/`)
* **Propósito:** Descompilador y analizador estático para diseccionar ejecutables (.exe, .dll, ELF), scripts compilados (.pyc) y código fuente sin requerir el proyecto original. Extrae metadatos, entropía de Shannon, strings imprimibles y clasifica el nivel de riesgo en Markdown.
* **Archivo principal:** [`./tools/reverse_engineering/decompiler_helper.py`](file:///c:/Users/juand/OneDrive/Desktop/IA_Automejorable/tools/reverse_engineering/decompiler_helper.py)
* **Prueba unitaria:** [`./tools/reverse_engineering/test.py`](file:///c:/Users/juand/OneDrive/Desktop/IA_Automejorable/tools/reverse_engineering/test.py) (3 tests OK)
* **Firma de llamada en Python:**
  ```python
  from tools.reverse_engineering.decompiler_helper import ReverseEngineeringAssistant

  assistant = ReverseEngineeringAssistant("ruta/al/binario_o_script.py")
  # Generar reporte completo estructurado en Markdown
  reporte_md = assistant.generate_report()
  # O inspeccionar individualmente:
  # assistant.calculate_entropy()
  # assistant.extract_strings(min_len=4)
  # assistant.identify_format()
  ```
* **Uso vía CLI:**
  ```bash
  python ./tools/reverse_engineering/decompiler_helper.py archivo.exe --output reporte.md
  ```

---

## 4. ACE (Agent Computer Environment / Sandbox Runner) (`./tools/agent_sandbox/`)
* **Propósito:** Entorno controlado de ejecución para comandos de consola y scripts de Python generados por el agente. Aplica timeouts estrictos, aislamiento de rutas, captura obligatoria de `stdout`/`stderr`/`exit_code` y bloqueo preventivo de comandos destructivos del sistema operativo.
* **Archivo principal:** [`./tools/agent_sandbox/sandbox_runner.py`](file:///c:/Users/juand/OneDrive/Desktop/IA_Automejorable/tools/agent_sandbox/sandbox_runner.py)
* **Prueba unitaria:** [`./tools/agent_sandbox/test.py`](file:///c:/Users/juand/OneDrive/Desktop/IA_Automejorable/tools/agent_sandbox/test.py) (4 tests OK)
* **Firma de llamada en Python:**
  ```python
  from tools.agent_sandbox.sandbox_runner import AgentSandboxRunner

  runner = AgentSandboxRunner(workspace_dir="./")
  # Ejecutar comando de consola con timeout
  res = runner.run_command("dir", timeout=15)
  # res -> {"success": bool, "exit_code": int, "stdout": str, "stderr": str, "duration": float, "blocked": bool}

  # Ejecutar código Python aislado
  res_py = runner.run_python_code("import sys; print(sys.version)", timeout=10)
  ```
* **Uso vía CLI:**
  ```bash
  python ./tools/agent_sandbox/sandbox_runner.py --cmd "Get-Process" --timeout 15
  python ./tools/agent_sandbox/sandbox_runner.py --code "print(2**64)"
  ```

---

## 5. Network DNS Sinkhole & Ad-Filter (`./tools/dns_sinkhole/`)
* **Propósito:** Micro-servidor e interceptor DNS local (estilo Pi-hole / ESP32 DNS sinkhole). Intercepta consultas DNS UDP, analiza dominios contra listas de bloqueo (publicidad, rastreadores y telemetría) y responde con `0.0.0.0` a dominios no deseados mientras reenvía consultas legítimas al DNS upstream (1.1.1.1).
* **Archivo principal:** [`./tools/dns_sinkhole/dns_filter.py`](file:///c:/Users/juand/OneDrive/Desktop/IA_Automejorable/tools/dns_sinkhole/dns_filter.py)
* **Prueba unitaria:** [`./tools/dns_sinkhole/test.py`](file:///c:/Users/juand/OneDrive/Desktop/IA_Automejorable/tools/dns_sinkhole/test.py) (4 tests OK)
* **Firma de llamada en Python:**
  ```python
  from tools.dns_sinkhole.dns_filter import DnsSinkhole

  sinkhole = DnsSinkhole(upstream_dns="1.1.1.1")
  # Cargar lista negra desde archivo estándar de hosts
  sinkhole.load_blocklist_from_file("blocklist.txt")
  # O agregar en memoria:
  sinkhole.add_domains(["adservice.google.com", "telemetry.tracker.io"])

  # Verificar si un dominio está bloqueado
  bloqueado = sinkhole.is_blocked("sub.adservice.google.com") # True

  # Iniciar servidor DNS en puerto local
  sinkhole.start_server(host="127.0.0.1", port=5353)
  ```
* **Uso vía CLI:**
  ```bash
  python ./tools/dns_sinkhole/dns_filter.py --test-domain "doubleclick.net"
  python ./tools/dns_sinkhole/dns_filter.py --port 5353 --blocklist blocklist.txt
  ```

---

## Resumen de Verificación de Calidad

| Módulo | Directorio | Archivo Principal | Tests | Estado |
| :--- | :--- | :--- | :---: | :---: |
| **WiFi Sensing** | `./tools/wifi_sensing/` | `analyzer.py` | 4/4 | ✅ PASADO |
| **Offline Vault** | `./tools/offline_vault/` | `vault_engine.py` | 3/3 | ✅ PASADO |
| **REA Assistant** | `./tools/reverse_engineering/` | `decompiler_helper.py` | 3/3 | ✅ PASADO |
| **ACE Sandbox** | `./tools/agent_sandbox/` | `sandbox_runner.py` | 4/4 | ✅ PASADO |
| **DNS Sinkhole** | `./tools/dns_sinkhole/` | `dns_filter.py` | 4/4 | ✅ PASADO |
| **Agente JEV Core** | `./tests/` | Suite general | 38/38 | ✅ PASADO |
