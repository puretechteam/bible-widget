@echo off
setlocal
set "BW_PIDFILE=%~dp0widget.pid"
set "BW_DIR=%~dp0"
if not exist "%BW_PIDFILE%" exit /b 0
rem PowerShell reads the process number itself, so nothing in the file can run as a command. It
rem stops the process only if it is this folder's widget: Windows reuses the numbers of ended
rem processes, so after a crash the number may belong to another program, even another Python one,
rem another copy of the widget, or an editor with widget_window.py open.
powershell -NoProfile -NonInteractive -Command "$n = Get-Content -LiteralPath $env:BW_PIDFILE -TotalCount 1; if ($n -match '^\s*(\d{1,10})\s*$') { $id = [long]$Matches[1]; $p = Get-CimInstance Win32_Process -Filter ('ProcessId=' + $id); $dir = $env:BW_DIR.TrimEnd('\'); $mine = @((Join-Path $dir 'widget_window.py'), (Join-Path $dir 'BibleWidget.exe')); if ($p -and $p.Name -match '^(pythonw?|BibleWidget)\.exe$' -and (@($mine | Where-Object { $p.CommandLine -and $p.CommandLine.IndexOf($_, [StringComparison]::OrdinalIgnoreCase) -ge 0 }).Count -gt 0 -or $p.ExecutablePath -eq $mine[1])) { Stop-Process -Id $id -Force } }"
del "%BW_PIDFILE%" >nul 2>&1
