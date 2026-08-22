@echo off
setlocal
cd /d "%~dp0"

echo ================================================
echo   Thrash Lightening Control - EXE Builder
echo ================================================
echo.

where py >nul 2>nul
if %errorlevel%==0 (
    set "PY=py"
) else (
    set "PY=python"
)

%PY% -m pip install -r requirements-build.txt
if errorlevel 1 (
    echo.
    echo [ERROR] Failed to install build dependencies.
    pause
    exit /b 1
)

echo.
echo [1/2] Cleaning previous build...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

 echo [2/2] Building standalone EXE...
%PY% -m PyInstaller --clean --noconfirm keyboard-effects.spec
if errorlevel 1 (
    echo.
    echo [ERROR] PyInstaller build failed.
    pause
    exit /b 1
)

echo.
echo ================================================
echo   BUILD COMPLETE
echo ================================================
echo.
echo EXE:
echo   dist\ThrashLighteningControl.exe
echo.
echo Double-click ThrashLighteningControl.exe and accept the Administrator prompt.
echo The native desktop window will open automatically.
echo.
pause
endlocal
