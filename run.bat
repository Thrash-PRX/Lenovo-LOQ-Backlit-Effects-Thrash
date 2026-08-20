@echo off
title Lenovo LOQ Keyboard Effects Lab
echo ===================================================
echo     Lenovo LOQ Keyboard Effects Lab Launcher
echo ===================================================
echo.

:: Check for Python
where py >nul 2>nul
if %errorlevel% neq 0 (
    where python >nul 2>nul
    if %errorlevel% neq 0 (
        echo [ERROR] Python is not installed!
        echo Please install Python from https://www.python.org/downloads/
        echo (Make sure to check "Add Python to PATH" during installation)
        echo.
        pause
        exit /b
    )
)

echo [1/2] Installing/verifying dependencies...
py -m pip install -r requirements.txt --quiet
if %errorlevel% neq 0 (
    echo [WARNING] Failed to install dependencies via 'py'. Trying 'python'...
    python -m pip install -r requirements.txt --quiet
)

echo [2/2] Launching desktop application (UAC prompt will appear)...
py app.py
if %errorlevel% neq 0 (
    python app.py
)

pause
