@echo off
setlocal enabledelayedexpansion

title Utils Toolkit Updater
color 07

echo ======================================
echo   Utils Toolkit - Online Updater
echo   No Git required
echo ======================================
echo.

:: Check current directory
if not exist "%~dp0start.bat" (
    echo [ERROR] Please put update.bat in the project root folder
    echo         Current: %~dp0
    echo         Missing: start.bat
    pause
    exit /b 1
)
cd /d "%~dp0"
echo [OK] Project root: %cd%
echo.

:: Step 1: Download latest code
echo [1/4] Downloading latest version...
if exist "update_tmp.zip" del /f /q "update_tmp.zip" >nul 2>&1

powershell -Command "$wc=New-Object System.Net.WebClient; try{$wc.DownloadFile('https://github.com/sur584/utils-toolkit/archive/refs/heads/master.zip','update_tmp.zip');write-host OK}catch{write-host FAIL;echo $_.Exception.Message;exit 1}"
if %errorlevel% neq 0 (
    echo [ERROR] Download failed. Check your network / VPN connection.
    if exist "update_tmp.zip" del /f /q "update_tmp.zip" >nul 2>&1
    pause
    exit /b 1
)
if not exist "update_tmp.zip" (
    echo [ERROR] Download failed - no file received
    pause
    exit /b 1
)
echo [OK] Download complete

:: Step 2: Extract
echo [2/4] Extracting...
if exist "update_tmp" rmdir /s /q "update_tmp" >nul 2>&1

powershell -Command "try{Expand-Archive -Path 'update_tmp.zip' -DestinationPath 'update_tmp' -Force;write-host OK}catch{write-host FAIL;echo $_.Exception.Message;exit 1}"
if %errorlevel% neq 0 (
    echo [ERROR] Extract failed
    rmdir /s /q "update_tmp" >nul 2>&1
    del /f /q "update_tmp.zip" >nul 2>&1
    pause
    exit /b 1
)

:: Find extracted folder
set SRC_DIR=
for /d %%i in ("update_tmp\*") do set "SRC_DIR=%%i"
if "%SRC_DIR%"=="" (
    echo [ERROR] No extracted folder found
    rmdir /s /q "update_tmp" >nul 2>&1
    del /f /q "update_tmp.zip" >nul 2>&1
    pause
    exit /b 1
)
echo [OK] Extract complete

:: Step 3: Copy files (exclude local data)
echo [3/4] Updating files...

robocopy "%SRC_DIR%" "." /e /purge /njh /njs /ndl /np /ns ^
    /xd ".git" "cache" "models" "node_modules" "backend\downloads" ^
    /xf "update.bat"

if %errorlevel% geq 8 (
    echo [ERROR] File copy failed (code: %errorlevel%)
    rmdir /s /q "update_tmp" >nul 2>&1
    del /f /q "update_tmp.zip" >nul 2>&1
    pause
    exit /b 1
)
echo [OK] Files updated

:: Step 4: Cleanup
echo [4/4] Cleaning up...
rmdir /s /q "update_tmp" >nul 2>&1
del /f /q "update_tmp.zip" >nul 2>&1
echo [OK] Done

echo.
echo ======================================
echo   Update complete!
echo ======================================
echo.
echo Changes in this update:
echo   - Fixed TikTok parsing
echo   - Auto proxy detection
echo   - Faster downloads
echo.
echo Please restart the service if running.
echo.
pause
exit /b 0
