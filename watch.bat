@echo off
chcp 936 >nul
setlocal enabledelayedexpansion
set "ADB=C:\Program Files (x86)\Minimal ADB and Fastboot"
title Fastboot/ADB 实时监测 - 插上手机看这里
:loop
cls
echo ==================================================
echo            设备实时监测（每 2 秒刷新）
echo ==================================================
echo.
echo [FASTBOOT 设备]
"%ADB%\fastboot.exe" devices
echo.
echo [ADB 设备]
"%ADB%\adb.exe" devices
echo.
echo --------------------------------------------------
echo 出现序列号 = 连接成功
echo 两栏都空   = 手机没连上（线/口/未进fastboot）
echo --------------------------------------------------
timeout /t 2 >nul
goto loop
