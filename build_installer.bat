@echo off
setlocal
cd /d "%~dp0"

set "ISCC=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"

if not exist "%ISCC%" (
    echo [ERROR] Inno Setup 6 was not found.
    echo Install it from https://jrsoftware.org/isdl.php
    exit /b 1
)

if not exist "installer\Thrash-Code-Signing.cer" (
    echo [ERROR] installer\Thrash-Code-Signing.cer is missing.
    exit /b 1
)

if not exist "installer\SHA256SUMS.txt" (
    echo [ERROR] installer\SHA256SUMS.txt is missing.
    exit /b 1
)

set "PYTHON=python"
where py >nul 2>nul && set "PYTHON=py"
%PYTHON% -m PyInstaller --clean --noconfirm --distpath installer-app --workpath build\installer-app keyboard-effects-installer.spec
if errorlevel 1 exit /b 1

"%ISCC%" installer.iss
if errorlevel 1 exit /b 1

echo.
echo Installer created in installer-dist\
endlocal
