@echo off
cd /d "%~dp0"
title Rebuild Frontend

echo.
echo ==========================================
echo   Rebuild Frontend
echo ==========================================
echo.

where node >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Node.js not found!
    echo Please install from: https://nodejs.org/
    pause
    exit /b
)

echo [1/2] Building frontend...
npx vite build
if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Build failed!
    pause
    exit /b
)

echo.
echo [2/2] Done!
echo.
echo Frontend rebuilt successfully. You can now run app.bat to start the server.
echo.
pause
