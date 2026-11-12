@echo off
title Bible Widget - Dependencies
rem Only needed to run from source. The BibleWidget.exe download needs nothing installed.
rem PySide6 goes into the Python that start_widget.vbs starts: the newest Python 3 the py launcher
rem knows, if it can run one, or else the python on the PATH.

echo Checking for Python...
set "PY="
py -3 -c "pass" >nul 2>&1 && set "PY=py -3"
if not defined PY python --version >nul 2>&1 && set "PY=python"
if not defined PY (
    echo [ERROR] Python is not installed or not in PATH.
    echo Please install Python from https://www.python.org/downloads/
    echo Make sure to check "Add Python to PATH" during installation.
    pause
    exit /b 1
)

echo Using: %PY%
%PY% --version

echo.
echo Installing the packages listed in requirements.txt (PySide6)...
%PY% -m pip install -r "%~dp0requirements.txt"
if %errorlevel% neq 0 (
    echo [ERROR] Failed to install the requirements.
    pause
    exit /b 1
)

echo.
echo All dependencies are ready! You can now run start_widget.vbs
pause
