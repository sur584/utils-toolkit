@echo off
cd /d "%~dp0"
title Utils Toolkit - Stop

echo.
echo ==========================================
echo   Stopping Utils Toolkit...
echo ==========================================
echo.

powershell -Command "$p=(Get-NetTCPConnection -LocalPort 5002 -ErrorAction SilentlyContinue).OwningProcess; if ($p){Stop-Process -Id $p -Force;echo ('Stopped PID:'+$p)}else{echo 'Port 5002 not in use'}"

echo.
echo ==========================================
echo   Done
echo ==========================================
echo.
pause
