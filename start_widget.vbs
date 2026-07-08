Dim fso, folder
Set fso = CreateObject("Scripting.FileSystemObject")
folder = fso.GetParentFolderName(WScript.ScriptFullName)
CreateObject("Wscript.Shell").Run "pythonw """ & folder & "\widget_window.py""", 0, False