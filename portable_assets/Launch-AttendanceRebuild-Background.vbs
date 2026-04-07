Option Explicit

Dim shell
Dim fso
Dim appDir
Dim exePath

Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

appDir = fso.GetParentFolderName(WScript.ScriptFullName)
exePath = fso.BuildPath(appDir, "AttendanceRebuild.exe")

shell.CurrentDirectory = appDir
shell.Run """" & exePath & """", 0, False
