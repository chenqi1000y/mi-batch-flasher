@echo off
chcp 65001 >nul 2>&1
title 红米Note5 批量刷机工具
cd /d "%~dp0"

echo ============================================
echo     红米 Note 5 (whyred) 批量刷机工具
echo ============================================
echo.
echo   [1] 单台全自动刷机
echo   [2] 多设备并行刷机（插几台刷几台）
echo   [3] 多设备持续监测（插一台刷一台，Ctrl+C 停）
echo   [4] 查看环境自检
echo   [0] 退出
echo.
set /p ch=请选择(1/2/3/4/0):

if "%ch%"=="1" goto single
if "%ch%"=="2" goto multi
if "%ch%"=="3" goto watch
if "%ch%"=="4" goto check
if "%ch%"=="0" goto end
goto end

:single
echo.
echo 手机请先进入 OrangeFox 并连接，按任意键开始...
pause >nul
python oneflash.py
goto end

:multi
echo.
echo 多设备并行。手机请全部进入 OrangeFox 并连接。
echo 默认并发 6 台（受 USB 供电限制）。
set /p max=并发数(默认6):
if "%max%"=="" set max=6
python multiflash.py --max %max%
goto end

:watch
echo.
echo 持续监测模式：插一台刷一台，Ctrl+C 停止。
python multiflash.py --watch
goto end

:check
echo.
echo ============ 环境自检 ============
tools\adb.exe version 2>nul | findstr /i "version"
echo.
echo ROM 包：
dir /b roms\*.zip 2>nul
echo.
echo 当前设备：
tools\adb.exe devices
echo ================================
pause
goto end

:end
