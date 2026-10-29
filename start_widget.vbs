Dim fso, folder
Set fso = CreateObject("Scripting.FileSystemObject")
folder = fso.GetParentFolderName(WScript.ScriptFullName)
CreateObject("Wscript.Shell").Run "py -3 """ & folder & "\widget_window.py""", 0, False