# 🖥️ Acceso directo de JEV en el escritorio

Cómo convertir el proyecto en una aplicación de un solo clic, sin tener que
entrar a la carpeta cada vez. El patrón está tomado de
[Louis-CFM/coucou](https://github.com/Louis-CFM/coucou), que resuelve lo mismo
para su app de bandeja con una entrada de escritorio y un instalador.

---

## 1. Qué se tomó de Coucou

Coucou declara su lanzador con una entrada `.desktop` (Linux) y deja que el
instalador (Tauri/NSIS en Windows) cree los accesos directos:

| Campo de Coucou | Significado | Equivalente en JEV (Windows) |
|-----------------|-------------|------------------------------|
| `Type=Application` | Es una aplicación | Acceso directo `.lnk` |
| `Name=Coucou` | Nombre visible | `JEV - Jarvis AI.lnk` |
| `Exec=coucou` | Comando de arranque | `pythonw.exe jev_launcher.py` |
| `Icon=coucou` | Icono | `assets\jev.ico` (multi-resolución) |
| `Terminal=false` | Sin consola | `pythonw.exe` + `jev_launcher.py` |
| Instalador NSIS | Crea los accesos directos | `scripts\install_desktop_shortcut.ps1` |

La idea es la misma: **un único punto de entrada declarativo, sin consola y con
icono propio**, más un instalador que crea los accesos directos y sabe
desinstalarlos.

## 2. Archivos implicados

| Archivo | Función |
|---------|---------|
| `crear_acceso_directo.bat` | Doble clic para crear el acceso directo (una sola vez). |
| `scripts\install_desktop_shortcut.ps1` | Instalador real: crea/elimina Escritorio, Menú Inicio y Arranque. |
| `jev_launcher.py` | Arranque sin consola: log, instancia única y foco de la instancia existente. |
| `launch_jev.vbs` | Lanzador alternativo (el acceso directo ya no lo necesita). |
| `jev_launcher.py` | Arranque: log, instancia única, cuadro de error legible. |
| `assets\jev.ico` | Icono del reactor (16–256 px, fondo transparente). |
| `scripts\generate_jev_icon.py` | Regenera el icono si quieres otro diseño. |

![Icono de JEV](../assets/jev_icon_256.png)

## 3. Instalación (una vez)

La forma más simple:

1. Doble clic en **`crear_acceso_directo.bat`**.
2. Aparece **JEV - Jarvis AI** en el escritorio y en el menú Inicio.
3. Doble clic en el icono y JEV arranca sin ventana de consola.

Por PowerShell:

~~~powershell
# Escritorio + Menú Inicio
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\install_desktop_shortcut.ps1

# Solo escritorio
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\install_desktop_shortcut.ps1 -NoStartMenu

# Además, arrancar JEV al iniciar sesión
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\install_desktop_shortcut.ps1 -Startup
~~~

## 4. Desinstalación

~~~powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\install_desktop_shortcut.ps1 -Uninstall
~~~

También puedes pasar `-Uninstall` al `.bat`:
`crear_acceso_directo.bat -Uninstall`.

## 5. Cómo funciona el arranque

~~~text
[doble clic en el .lnk]
        │
        ▼
pythonw.exe "C:\...\jev_launcher.py"      (sin consola)
        │  redirige stdout/stderr a data\logs\jev_launcher.log
        │  mutex Local\\JEV_AutonomousAI_SingleInstance (una sola instancia)
        ▼
jev_desktop.main()
        ├── isla flotante (centrada arriba, siempre encima)
        └── ventana JARVIS completa (oculta hasta "Abrir JEV")
~~~

- **Una sola instancia**: si ya está abierto, **trae su isla o su ventana al frente**
  en lugar de bloquear el arranque.
- **Errores visibles**: si el arranque falla, aparece un cuadro de diálogo con la
  ruta del log; no se queda "en silencio".
- **Sin ventana negra**: se usa `pythonw.exe`; si no existiera, el VBS cae a
  `python.exe` con la ventana oculta.

## 6. Anclar a la barra de tareas

Windows no permite anclar por script, pero es inmediato:

1. Abre JEV desde el escritorio.
2. Clic derecho en su icono de la barra de tareas.
3. **Anclar a la barra de tareas**.

## 7. Diagnóstico

| Síntoma | Qué revisar |
|---------|-------------|
| Doble clic y no pasa nada | `data\logs\jev_launcher.log` (últimas líneas). |
| "No se encontró el entorno virtual" | Falta `.venv`; ejecuta la instalación del proyecto. |
| "JEV ya está abierto" | Hay otra instancia; búscala en la barra de tareas. |
| Icono genérico | Vuelve a ejecutar el instalador: regenera `assets\jev.ico` si falta. |
| Moví la carpeta del proyecto | Vuelve a ejecutar `crear_acceso_directo.bat`. |

## 8. Nota sobre Coucou

Coucou es una app nativa (Swift/Tauri) con instalador propio; JEV es Python +
PyWebView. No se copia su código: se replica su **contrato de integración**
(entrada declarativa, icono, sin terminal, instalador/desinstalador), que es la
parte reutilizable.

---

## 9. Isla flotante (nuevo)

El acceso directo del escritorio ya no abre la ventana completa, sino la
**Isla de JEV**. Toda la información de la isla (mascota, panel, aprobaciones,
modo clásico) está en [DESKTOP_ISLAND.md](DESKTOP_ISLAND.md).
