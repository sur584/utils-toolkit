@echo off
cd /d "%~dp0"
title Utils Toolkit

:: Find Python
set PY_CMD=python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    py --version >nul 2>&1
    if %errorlevel%==0 (
        set PY_CMD=py
    ) else (
        if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" (
            set PY_CMD=%LOCALAPPDATA%\Programs\Python\Python312\python.exe
        ) else (
            echo [ERROR] Python not found!
            echo.
            echo Please install Python 3.10+ from:
            echo   https://www.python.org/downloads/
            echo.
            echo Or open index.html directly for image tool.
            echo.
            pause
            exit /b 1
        )
    )
)

echo Starting Utils Toolkit...
"%PY_CMD%" launcher.py
if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Failed to start. Error code: %errorlevel%
)
pause
