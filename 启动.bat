@echo off
rem ---------------------------------------------------------------------
rem  Xiangqi Coach launcher
rem
rem  ASCII ONLY. cmd.exe parses .bat files using the OEM codepage (GBK on
rem  Chinese Windows). Any Chinese character written into this file turns
rem  into garbage and gets executed as a command, which is exactly the
rem  "is not recognized as an internal or external command" error.
rem  All Chinese output comes from server.py, which handles UTF-8 itself.
rem ---------------------------------------------------------------------
chcp 65001 >nul
title Xiangqi Coach
cd /d "%~dp0"

set "PY=%USERPROFILE%\.workbuddy\binaries\python\versions\3.13.12\python.exe"
if not exist "%PY%" set "PY=python"

set "PYTHONIOENCODING=utf-8"
set "PYTHONUTF8=1"

"%PY%" -u server.py
set "CODE=%ERRORLEVEL%"

rem exit code 3 = another instance is already running, browser was opened
if "%CODE%"=="3" exit /b 0

echo.
if not "%CODE%"=="0" echo   [ERROR] server.py exited with code %CODE%
echo   Server stopped. Press any key to close this window.
pause >nul
