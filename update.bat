@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul 2>&1

title Utils Toolkit 更新器
color 0B

echo ======================================
echo   Utils Toolkit - 在线更新
echo   无需 Git，双击即可更新
echo ======================================
echo.

:: ── 检查运行目录 ──────────────────────────
if not exist "%~dp0start.bat" (
    echo [×] 请把 update.bat 放到项目根目录运行
    echo     当前目录: %~dp0
    echo     缺少 start.bat
    pause
    exit /b 1
)
cd /d "%~dp0"
echo [√] 项目目录: %cd%
echo.

:: ── 检查是否被反病毒软件拦截 ──────────────
echo [1/4] 正在下载最新版本...
if exist "update_tmp.zip" del /f /q "update_tmp.zip" >nul 2>&1

:: 用 PowerShell 下载（Windows 7 起内置，比 curl 更通用）
powershell -Command "& {
    $wc = New-Object System.Net.WebClient;
    try {
        $wc.DownloadFile('https://github.com/sur584/utils-toolkit/archive/refs/heads/master.zip', 'update_tmp.zip');
        Write-Host 'download_ok'
    } catch {
        Write-Host 'download_fail:' $_.Exception.Message
    }
}" > "%temp%\update_result.tmp" 2>&1

set /p DOWNLOAD_RESULT=<"%temp%\update_result.tmp"
if not "%DOWNLOAD_RESULT%"=="download_ok" (
    echo [×] 下载失败
    type "%temp%\update_result.tmp"
    del /f /q "%temp%\update_result.tmp" >nul 2>&1
    if exist "update_tmp.zip" del /f /q "update_tmp.zip" >nul 2>&1
    echo.
    echo 可能的原因：
    echo   1. 网络无法访问 GitHub
    echo   2. 安全软件拦截了下载
    echo   3. 梯子未开启（需要翻墙时）
    pause
    exit /b 1
)
del /f /q "%temp%\update_result.tmp" >nul 2>&1
echo [√] 下载完成

:: ── 解压 ──────────────────────────────────
echo [2/4] 正在解压...
if exist "update_tmp" rmdir /s /q "update_tmp" >nul 2>&1

powershell -Command "& {
    try {
        Expand-Archive -Path 'update_tmp.zip' -DestinationPath 'update_tmp' -Force;
        Write-Host 'extract_ok'
    } catch {
        Write-Host 'extract_fail:' $_.Exception.Message
    }
}" > "%temp%\update_result.tmp" 2>&1

set /p EXTRACT_RESULT=<"%temp%\update_result.tmp"
if not "%EXTRACT_RESULT%"=="extract_ok" (
    echo [×] 解压失败
    type "%temp%\update_result.tmp"
    del /f /q "%temp%\update_result.tmp" >nul 2>&1
    if exist "update_tmp" rmdir /s /q "update_tmp" >nul 2>&1
    if exist "update_tmp.zip" del /f /q "update_tmp.zip" >nul 2>&1
    pause
    exit /b 1
)
del /f /q "%temp%\update_result.tmp" >nul 2>&1
echo [√] 解压完成

:: ── 查找解压后的目录 ──────────────────────
set SRC_DIR=
for /d %%i in ("update_tmp\*") do set "SRC_DIR=%%i"
if "%SRC_DIR%"=="" (
    echo [×] 未找到更新文件
    rmdir /s /q "update_tmp" >nul 2>&1
    del /f /q "update_tmp.zip" >nul 2>&1
    pause
    exit /b 1
)
echo [√] 找到更新包: %SRC_DIR%

:: ── 复制文件（排除 .git 和缓存）───────────
echo [3/4] 正在更新文件...
echo.
echo 排除项:
echo   - .git              (版本控制)
echo   - cache             (本地缓存)
echo   - models            (模型文件)
echo   - backend/downloads (下载文件)
echo   - node_modules      (如果存在)
echo.

robocopy "%SRC_DIR%" "." /e /purge /njh /njs /ndl /np /ns ^
    /xd ".git" "cache" "models" "node_modules" "backend\downloads" ^
    /xf "update.bat"

if %errorlevel% geq 8 (
    echo [×] 文件复制失败（错误码: %errorlevel%）
    rmdir /s /q "update_tmp" >nul 2>&1
    del /f /q "update_tmp.zip" >nul 2>&1
    pause
    exit /b 1
)
echo.
echo [√] 文件更新完成

:: ── 清理临时文件 ──────────────────────────
echo [4/4] 正在清理...
rmdir /s /q "update_tmp" >nul 2>&1
del /f /q "update_tmp.zip" >nul 2>&1
echo [√] 清理完成

echo.
echo ======================================
echo   更新完成！
echo ======================================
echo.
echo 本次更新内容:
echo   - 修复 TikTok 解析失败问题
echo   - 自动检测代理（无需手动配置）
echo   - 下载优先使用无水印直链
echo.
echo 如果服务正在运行，请重启以生效。
echo.
echo 按任意键退出...
pause >nul 2>&1
exit /b 0
