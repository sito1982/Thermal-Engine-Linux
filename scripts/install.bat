@echo off
setlocal EnableDelayedExpansion

echo ============================================
echo   Thermal Engine Studio - Installation Script
echo ============================================
echo.

:: Situate siempre en la raiz del proyecto: este script vive en scripts\.
cd /d "%~dp0.."

if not exist "requirements.txt" (
    echo [ERROR] No se encuentra requirements.txt en "%CD%".
    echo Ejecuta este script desde el proyecto ^(scripts\install.bat^).
    pause
    exit /b 1
)

:: Check for Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python is not installed or not in PATH.
    echo Please install Python 3.10 or later from https://www.python.org/
    pause
    exit /b 1
)

echo [OK] Python found
python --version
echo.

:: Check for pip
python -m pip --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] pip is not available. Please reinstall Python with pip included.
    pause
    exit /b 1
)

echo [OK] pip found
echo.

:: Ask about virtual environment
set /p VENV_CHOICE="Create a virtual environment? (recommended) [Y/n]: "
if /i "%VENV_CHOICE%"=="n" goto :skip_venv

if exist "venv\Scripts\python.exe" (
    echo [OK] Existing virtual environment found in venv\
) else (
    echo Creating virtual environment...
    python -m venv venv
    if errorlevel 1 (
        echo [WARNING] Failed to create virtual environment. Continuing with system Python...
        goto :skip_venv
    )
    echo [OK] Virtual environment created in venv\
)

echo Activating virtual environment...
call "venv\Scripts\activate.bat"
if errorlevel 1 (
    echo [WARNING] Could not activate the virtual environment. Continuing with system Python...
    goto :skip_venv
)
echo [OK] Virtual environment activated
echo.

:skip_venv

:: Install Python dependencies
echo Installing Python dependencies...
echo This may take a few minutes...
echo.
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo [WARNING] Some packages may have failed to install.
    echo The editor may still work with reduced functionality.
    set "INSTALL_FAILED=1"
)
echo.

:: Create presets folder if it doesn't exist
if not exist "presets" mkdir presets

echo.
echo ============================================
if defined INSTALL_FAILED (
    echo   Installation finished with warnings
) else (
    echo   Installation Complete
)
echo ============================================
echo.
if defined INSTALL_FAILED (
    echo Revisa los errores de pip mostrados arriba antes de ejecutar la app.
    echo.
)
echo To run the editor:
echo   Double-click 'scripts\run.bat'
if exist "venv\Scripts\python.exe" (
    echo   or run: venv\Scripts\python.exe main.py
) else (
    echo   or run: python main.py
)
echo.
echo NOTE: Sensors work natively on Windows (NVML + psutil/WMI), no admin needed.
echo       HWiNFO is OPTIONAL: install it from https://www.hwinfo.com/ and enable
echo       "Shared Memory Support" for extra metrics (fans, CPU power, NVMe).
echo.
pause
