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

rem ====== Install dependencies ======
echo Checking dependencies...

"%PY_CMD%" -c "import fastapi,uvicorn,httpx" >nul 2>&1
if %errorlevel%==0 goto deps_ok

echo Installing (this may take a minute)...

rem Try normal install first
"%PY_CMD%" -m pip install fastapi uvicorn httpx pydantic -q
if %errorlevel%==0 goto deps_ok

rem Try without proxy
echo Retrying without proxy...
set HTTP_PROXY=
set HTTPS_PROXY=
set http_proxy=
set https_proxy=
set ALL_PROXY=
"%PY_CMD%" -m pip install fastapi uvicorn httpx pydantic -q
if %errorlevel%==0 goto deps_ok

rem Try Tsinghua mirror
echo Retrying with Tsinghua mirror...
"%PY_CMD%" -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple fastapi uvicorn httpx pydantic -q
if %errorlevel%==0 goto deps_ok

rem All failed
echo.
echo [ERROR] Dependencies install failed!
echo.
echo Please run manually in CMD:
echo   %PY_CMD% -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple fastapi uvicorn httpx pydantic
echo.
pause
exit /b

:deps_ok
echo [OK] Core dependencies ready.

rem Optional deps (video download, AI bg-removal)
"%PY_CMD%" -c "import yt_dlp" >nul 2>&1
if %errorlevel% neq 0 (
    echo Installing yt-dlp...
    "%PY_CMD%" -m pip install yt-dlp -q >nul 2>&1
)
"%PY_CMD%" -c "import rembg" >nul 2>&1
if %errorlevel% neq 0 (
    echo Installing rembg...
    "%PY_CMD%" -m pip install rembg onnxruntime -q >nul 2>&1
)

echo.
echo ==========================================
echo   Starting server...
echo ==========================================
echo.

"%PY_CMD%" launcher.py

echo.
pause
