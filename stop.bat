@echo off
cd /d "%~dp0"
title Utils Toolkit - Stop

echo.
echo ==========================================
echo   Stopping Utils Toolkit...
echo ==========================================
echo.

powershell -Command "$found=$false; 5001..5010 | ForEach-Object { $procs=(Get-NetTCPConnection -LocalPort $_ -State Listen -ErrorAction SilentlyContinue).OwningProcess | Select-Object -Unique; foreach($procId in $procs){ if($procId){ try{ Stop-Process -Id $procId -Force -ErrorAction Stop; Write-Host ('Stopped port '+$_+' PID:'+$procId); $found=$true }catch{} } } }; if(-not $found){ Write-Host 'No Utils Toolkit service found on ports 5001-5010' }"

echo.
echo ==========================================
echo   Done
echo ==========================================
echo.
pause
