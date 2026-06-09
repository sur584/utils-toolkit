@echo off
setlocal
echo ==============================
echo   Building utils-toolkit...
echo ==============================

where node >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Node.js not found! Please install Node.js first.
    pause
    exit /b 1
)

call npm install
if %errorlevel% neq 0 (
    echo [ERROR] npm install failed!
    pause
    exit /b 1
)

call npx vite build
if %errorlevel% neq 0 (
    echo [ERROR] Vite build failed!
    pause
    exit /b 1
)

echo.
echo Build complete! Output in tools/ directory.
pause
