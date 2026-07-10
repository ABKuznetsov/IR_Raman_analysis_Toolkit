Option Explicit
Dim fso, shell, appRoot, previewScript, command
Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")
appRoot = fso.GetParentFolderName(WScript.ScriptFullName)
previewScript = appRoot & "\toolkit\launch_ir_raman_phase_finder_preview.ps1"

If Not fso.FileExists(previewScript) Then
    MsgBox "IR/Raman Phase Finder startup preview script was not found." & vbCrLf & previewScript, vbExclamation, "IR/Raman Phase Finder"
    WScript.Quit 1
End If

command = "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File " & Quote(previewScript) & " -AppId ir_raman_phase_finder"
shell.Run command, 0, False

Function Quote(value)
    Quote = Chr(34) & Replace(CStr(value), Chr(34), Chr(34) & Chr(34)) & Chr(34)
End Function
