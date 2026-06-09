@echo off
cd /d "%~dp0"
title Utils Toolkit

echo.
echo ==========================================
echo   Utils Toolkit
echo ==========================================
echo.

rem ====== Find Python ======
set PY_CMD=

where python >nul 2>&1
if %errorlevel%==0 (
    set PY_CMD=python
    goto python_found
)

where py >nul 2>&1
if %errorlevel%==0 (
    set PY_CMD=py
    goto python_found
)

if exist "%LOCALAPPDATA%\Programs\Python\Python313\python.exe" (
    set PY_CMD=%LOCALAPPDATA%\Programs\Python\Python313\python.exe
    goto python_found
)
if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" (
    set PY_CMD=%LOCALAPPDATA%\Programs\Python\Python312\python.exe
    goto python_found
)
if exist "%LOCALAPPDATA%\Programs\Python\Python311\python.exe" (
    set PY_CMD=%LOCALAPPDATA%\Programs\Python\Python311\python.exe
    goto python_found
)
if exist "%LOCALAPPDATA%\Programs\Python\Python310\python.exe" (
    set PY_CMD=%LOCALAPPDATA%\Programs\Python\Python310\python.exe
    goto python_found
)

rem Python not found
echo [ERROR] Python not found!
echo.
echo Please install Python 3.10+ from:
echo   https://www.python.org/downloads/
echo.
echo Make sure to check "Add Python to PATH" during install.
echo.
pause
exit /b

:python_found
echo Found Python: %PY_CMD%
echo.

rem launcher.py handles all dependency installation
"%PY_CMD%" launcher.py

echo.
pause
