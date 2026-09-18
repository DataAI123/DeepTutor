' DeepTutor silent launcher for Windows.
'
' Starts the web stack through the launcher's detached path so that no console
' window exists to flash on launch and none can be closed by accident (#1501).
' Because the worker is detached, closing anything this script did open leaves
' the server running; stop it with `deeptutor stop`.
'
' Output is not lost even though there is no console: the launcher redirects the
' detached worker to <home>\data\user\runtime\launcher.log, and `deeptutor
' doctor` summarises readiness afterwards.
'
' Optional desktop shortcut: create a shortcut whose target is
'     wscript.exe "<this file>"
' and whose "Start in" is the project root. Double-clicking it then behaves like
' launching the server, with no window to close.

Option Explicit

Const HIDDEN_WINDOW = 0
Const DONT_WAIT = False

Dim fso, shell, root, pythonw, command
Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")

root = fso.GetParentFolderName(fso.GetParentFolderName(WScript.ScriptFullName))

' Prefer the project virtualenv so the launcher imports the same deeptutor the
' repository is developed against; fall back to whatever pythonw is on PATH.
pythonw = fso.BuildPath(root, ".venv\Scripts\pythonw.exe")
If Not fso.FileExists(pythonw) Then
    pythonw = "pythonw"
End If

command = """" & pythonw & """ -m deeptutor_cli.main start --detach"
shell.CurrentDirectory = root

On Error Resume Next
shell.Run command, HIDDEN_WINDOW, DONT_WAIT
If Err.Number <> 0 Then
    MsgBox "DeepTutor could not be started." & vbCrLf & vbCrLf & _
           "Run this command in a terminal to see the error:" & vbCrLf & _
           "    cd /d """ & root & """" & vbCrLf & _
           "    python -m deeptutor_cli.main start --detach" & vbCrLf & vbCrLf & _
           "Error: " & Err.Description, vbCritical, "DeepTutor"
    WScript.Quit 1
End If
On Error GoTo 0
