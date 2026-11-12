Dim fso, folder, script, sh, python
Set fso = CreateObject("Scripting.FileSystemObject")
folder = fso.GetParentFolderName(WScript.ScriptFullName)
script = """" & folder & "\widget_window.py"""
Set sh = CreateObject("Wscript.Shell")
' The Python dependencies.bat installs PySide6 into: the newest Python 3 the py launcher knows if
' it can run one, or else the python on the PATH
python = "python"
On Error Resume Next
If sh.Run("py -3 -c ""pass""", 0, True) = 0 Then
    If Err.Number = 0 Then python = "py -3"
End If
Err.Clear
On Error GoTo 0
sh.Run python & " " & script, 0, False
