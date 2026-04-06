@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
set "PYTHON_BIN=%SCRIPT_DIR%\.venv\Scripts\python.exe"

if not exist "%PYTHON_BIN%" (
    echo Missing %PYTHON_BIN%. Please create .venv in the project root and install dependencies first.
    exit /b 1
)

"%PYTHON_BIN%" "%SCRIPT_DIR%scripts\launch_app.py" %*
