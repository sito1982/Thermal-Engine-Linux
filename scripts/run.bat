@echo off
:: Situate en la raiz del proyecto (este script vive en scripts\).
cd /d "%~dp0.."

:: Usa la venv del proyecto si existe; si no, el Python del sistema.
set "PYTHON=python"
if exist "venv\Scripts\python.exe" set "PYTHON=venv\Scripts\python.exe"

:: Run the application
"%PYTHON%" main.py

:: Keep window open if there was an error
if errorlevel 1 pause
