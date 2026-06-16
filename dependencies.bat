@echo off
title Bible Widget - Dependencies

echo Checking for Python...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed or not in PATH.
    echo Please install Python from https://www.python.org/downloads/
    echo Make sure to check "Add Python to PATH" during installation.
    pause
    exit /b 1
)

python --version

echo.
echo Checking for PySide6...
pip show PySide6 >nul 2>&1
if %errorlevel% neq 0 (
    echo PySide6 not found. Installing...
    pip install PySide6
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to install PySide6.
        pause
        exit /b 1
    )
) else (
    echo PySide6 is already installed.
)

echo.
echo All dependencies are ready! You can now run start_widget.bat or start_widget_no_terminal.vbs
pause