@echo off
chcp 65001 >nul 2>&1
title 红米Note5 批量刷机工具 (GUI)
cd /d "%~dp0"

REM 优先用系统 Python（带 tkinter），找不到再试其他
set PYTHON=
if exist "C:\Users\谌祺\AppData\Local\Programs\Python\Python310\python.exe" (
    set "PYTHON=C:\Users\谌祺\AppData\Local\Programs\Python\Python310\python.exe"
)
if not defined PYTHON (
    where python >nul 2>nul && set "PYTHON=python"
)
if not defined PYTHON (
    echo [错误] 未找到 Python。请安装 Python 3 并勾选 Add to PATH。
    pause
    exit /b 1
)

"%PYTHON%" flash_gui.py
if errorlevel 1 (
    echo.
    echo 程序异常退出。请检查上面的报错信息。
    pause
)
