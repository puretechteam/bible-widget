@echo off
set /p pid=<"%~dp0widget.pid"
taskkill /F /PID %pid% >nul 2>&1
del "%~dp0widget.pid" >nul 2>&1