' ============================================================================
' Lanzador silencioso de JEV - equivalente al Exec de una entrada .desktop
' Abre app.py con pythonw (sin consola) desde la carpeta correcta, aunque el
' acceso directo se ejecute desde el escritorio.
' ============================================================================
Option Explicit

Dim fso, shell, baseDir, pythonw, python, launcher, command
Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")

baseDir = fso.GetParentFolderName(WScript.ScriptFullName)
shell.CurrentDirectory = baseDir

pythonw = baseDir & "\.venv\Scripts\pythonw.exe"
python = baseDir & "\.venv\Scripts\python.exe"
launcher = baseDir & "\jev_launcher.py"

If Not fso.FileExists(launcher) Then
    MsgBox "No se encontró jev_launcher.py en:" & vbCrLf & baseDir, 16, "JEV"
    WScript.Quit 1
End If

If fso.FileExists(pythonw) Then
    command = """" & pythonw & """ """ & launcher & """"
ElseIf fso.FileExists(python) Then
    ' Sin pythonw: se usa python.exe con la ventana oculta por el propio shell.
    command = """" & python & """ """ & launcher & """"
Else
    MsgBox "No se encontró el entorno virtual .venv en:" & vbCrLf & baseDir & vbCrLf & vbCrLf & "Ejecuta primero la instalación del proyecto.", 16, "JEV"
    WScript.Quit 1
End If

' 0 = ventana oculta, False = no esperar a que termine
shell.Run command, 0, False
