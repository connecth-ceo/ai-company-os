@echo off
chcp 65001 >nul
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\smoke_tool_gateway.ps1"
echo.
pause
