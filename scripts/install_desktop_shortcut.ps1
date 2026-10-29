<#
.SYNOPSIS
    Crea (o elimina) el acceso directo de JEV en el escritorio de Windows.

.DESCRIPTION
    Equivalente Windows de la entrada .desktop de Coucou (Type/Name/Exec/Icon/
    Terminal=false):
      * Exec       -> wscript.exe launch_jev.vbs  (arranque sin consola)
      * Icon       -> assets\jev.ico
      * Terminal   -> false (pythonw + ventana oculta)
      * Instalador -> crea el acceso directo en Escritorio y Menu Inicio

.PARAMETER Uninstall
    Elimina los accesos directos creados (Escritorio, Menu Inicio y Arranque).

.PARAMETER Startup
    Anade ademas un acceso directo en la carpeta de Arranque de Windows
    (JEV se abrira al iniciar sesion).

.PARAMETER NoStartMenu
    No crea el acceso directo del Menu Inicio.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\install_desktop_shortcut.ps1

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\install_desktop_shortcut.ps1 -Uninstall
#>
[CmdletBinding()]
param(
    [switch]$Uninstall,
    [switch]$Startup,
    [switch]$NoStartMenu,
    [string]$Name = "JEV - Jarvis AI"
)

$ErrorActionPreference = "Stop"

$Root        = Split-Path -Parent $PSScriptRoot
$VbsLauncher = Join-Path $Root "launch_jev.vbs"
$LauncherPy  = Join-Path $Root "jev_launcher.py"
$IconFile    = Join-Path $Root "assets\jev.ico"
$AppFile     = Join-Path $Root "app.py"
$Pythonw     = Join-Path $Root ".venv\Scripts\pythonw.exe"
$PythonExe   = Join-Path $Root ".venv\Scripts\python.exe"

$DesktopDir  = [Environment]::GetFolderPath("Desktop")
$ProgramsDir = [Environment]::GetFolderPath("Programs")
$StartupDir  = [Environment]::GetFolderPath("Startup")

$Targets = [System.Collections.Generic.List[string]]::new()
$Targets.Add((Join-Path $DesktopDir ($Name + ".lnk")))
if (-not $NoStartMenu) { $Targets.Add((Join-Path $ProgramsDir ($Name + ".lnk"))) }
if ($Startup)          { $Targets.Add((Join-Path $StartupDir ($Name + ".lnk"))) }

function Remove-Shortcuts {
    $removed = 0
    foreach ($path in $Targets) {
        if (Test-Path -LiteralPath $path) {
            Remove-Item -LiteralPath $path -Force
            Write-Host ("  [eliminado] " + $path) -ForegroundColor DarkYellow
            $removed++
        }
    }
    if ($removed -eq 0) {
        Write-Host "  No habia accesos directos que eliminar." -ForegroundColor DarkGray
    } else {
        Write-Host ("Listo: " + $removed + " acceso(s) directo(s) eliminado(s).") -ForegroundColor Green
    }
}

function New-JevShortcut([string]$Path) {
    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($Path)
    $shortcut.TargetPath       = $Pythonw
    $shortcut.Arguments        = '"' + $LauncherPy + '"'
    $shortcut.WorkingDirectory = $Root
    $shortcut.IconLocation     = $IconFile + ",0"
    $shortcut.Description      = "JEV - Isla de escritorio y agente autonomo local (JARVIS)"
    $shortcut.WindowStyle      = 7
    $shortcut.Save()

    $check = (New-Object -ComObject WScript.Shell).CreateShortcut($Path)
    if ((Test-Path -LiteralPath $Path) -and ($check.TargetPath -eq $Pythonw)) {
        Write-Host ("  [creado]     " + $Path) -ForegroundColor Green
        Write-Host ("               -> " + $check.TargetPath + " " + $check.Arguments) -ForegroundColor DarkGray
    } else {
        throw "No se pudo verificar el acceso directo: $Path"
    }
}

Write-Host ""
Write-Host "  JEV - Integracion con el escritorio" -ForegroundColor Cyan
Write-Host "  =================================" -ForegroundColor Cyan
Write-Host ("  Proyecto  : " + $Root)
Write-Host ("  Escritorio: " + $DesktopDir)
Write-Host ""

if ($Uninstall) {
    Remove-Shortcuts
    Write-Host ""
    return
}

# --- Validaciones previas -------------------------------------------------
$missing = @()
foreach ($file in @($LauncherPy, $AppFile)) {
    if (-not (Test-Path -LiteralPath $file)) { $missing += $file }
}
if (-not (Test-Path -LiteralPath $Pythonw)) {
    throw ("No se encontro pythonw.exe en: " + $Pythonw)
}
if ($missing.Count -gt 0) {
    throw ("Faltan archivos necesarios: " + ($missing -join " | "))
}
if (-not (Test-Path -LiteralPath $IconFile)) {
    Write-Host "  [aviso] No hay icono en assets\jev.ico; se generara." -ForegroundColor Yellow
    & (Join-Path $Root ".venv\Scripts\python.exe") (Join-Path $Root "scripts\generate_jev_icon.py") | Out-Null
}

# --- Creacion -------------------------------------------------------------
foreach ($target in $Targets) {
    New-JevShortcut -Path $target
}

# Refrescar la caché de iconos de Explorer para que se vea el icono nuevo
try { & ie4uinit.exe -show | Out-Null } catch { }

Write-Host ""
Write-Host "  Acceso directo listo. Abre JEV con doble clic en el escritorio." -ForegroundColor Green
Write-Host "  Para anclarlo a la barra de tareas: clic derecho > Mas opciones > Anclar." -ForegroundColor DarkGray
Write-Host "  Desinstalar:  scripts\install_desktop_shortcut.ps1 -Uninstall" -ForegroundColor DarkGray
Write-Host "  Autoarranque: scripts\install_desktop_shortcut.ps1 -Startup" -ForegroundColor DarkGray
Write-Host ""
