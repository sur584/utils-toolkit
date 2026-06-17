@echo off
chcp 65001 >nul
title Utils Toolkit 更新

echo ======================================
echo   Utils Toolkit - 在线更新
echo ======================================
echo.

:: 检查是否在项目根目录
if not exist "start.bat" (
    echo [错误] 请把 update.bat 放到项目根目录运行
    pause
    exit /b 1
)

echo [1/3] 正在下载最新版本...
:: 先用 curl（Windows 10/11 自带），失败则用 PowerShell
curl -sL -o update_tmp.zip "https://github.com/sur584/utils-toolkit/archive/refs/heads/master.zip"
if %errorlevel% neq 0 (
    powershell -Command "Invoke-WebRequest -Uri 'https://github.com/sur584/utils-toolkit/archive/refs/heads/master.zip' -OutFile 'update_tmp.zip'"
)
if not exist "update_tmp.zip" (
    echo [错误] 下载失败，请检查网络连接
    pause
    exit /b 1
)
echo [OK] 下载完成

echo [2/3] 正在解压更新...
:: 删除旧的解压目录（如果有）
if exist "update_tmp" rmdir /s /q "update_tmp"

:: 解压
powershell -Command "Expand-Archive -Path 'update_tmp.zip' -DestinationPath 'update_tmp' -Force"
if %errorlevel% neq 0 (
    echo [错误] 解压失败
    del update_tmp.zip
    pause
    exit /b 1
)

:: 获取解压后的目录名（通常是 utils-toolkit-master）
for /d %%i in (update_tmp\*) do (
    echo 正在更新文件...
    xcopy /e /y "%%i\*" "." >nul
)

:: 清理临时文件
rmdir /s /q "update_tmp"
del update_tmp.zip

echo [3/3] 更新完成！
echo.
echo 如果服务正在运行，请重启以生效。
echo 按任意键退出...
pause >nul
