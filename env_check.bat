@echo off
chcp 65001 >nul 2>&1
setlocal enabledelayedexpansion
title 刷机环境自检
set "ADB=C:\Program Files (x86)\Minimal ADB and Fastboot"
set "ROM=E:\rom\whyred\whyred_global_images_V12.0.2.0.PEIMIXM_20201224.0000.00_9.0_global"

echo ============================================================
echo                      刷机环境自检
echo ============================================================
echo.

echo [1/5] Android 驱动是否已预装到系统
pnputil /enum-drivers 2>nul | findstr /i "android_winusb" >nul
if !errorlevel! equ 0 (echo        OK  - 驱动已预装，任意小米手机插上会自动识别) else (echo        FAIL- 驱动未预装，请重新运行安装)

echo.
echo [2/5] fastboot 工具
if exist "%ADB%\fastboot.exe" (echo        OK  - %ADB%\fastboot.exe) else (echo        FAIL- 找不到 fastboot.exe)

echo.
echo [3/5] 固件目录
if exist "%ROM%\flash_all.bat" (echo        OK  - 固件已解压就绪) else (echo        FAIL- 固件目录不完整)

echo.
echo [4/5] MiFlash 工具
if exist "E:\rom\tools\MiFlash2018\MiFlash2018-5-28-0\XiaoMiFlash.exe" (echo        OK  - MiFlash 就绪) else (echo        FAIL- MiFlash 缺失)

echo.
echo [5/5] 当前连接的设备
"%ADB%\fastboot.exe" devices
"%ADB%\adb.exe" devices

echo.
echo ============================================================
echo   全部 OK 即可开始刷机。设备栏空 = 手机没连上。
echo ============================================================
echo.
pause
