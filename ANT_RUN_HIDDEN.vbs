Option Explicit
Dim sh, fso, dir, cmd, rc
Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
dir = fso.GetParentFolderName(WScript.ScriptFullName)

' Use the same verified Python launcher path as ANT_RUN.bat.
' The CMD window itself is hidden by WScript, while launcher.py hides server.py.
cmd = "cmd /d /s /c ""cd /d """ & dir & """ && py launcher.py >> ANT_launcher.log 2>&1"""
rc = sh.Run(cmd, 0, False)

If rc <> 0 Then
    On Error Resume Next
    Dim logFile
    Set logFile = fso.OpenTextFile(fso.BuildPath(dir, "ANT_launcher.log"), 8, True)
    logFile.WriteLine Now & " VBS launch failed, Run return code=" & rc
    logFile.Close
End If
