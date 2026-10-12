@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 (
  python scripts\start-webui-local.py
) else (
  py -3 scripts\start-webui-local.py
)
if errorlevel 1 (
  echo.
  echo Startup failed. Check the message above and install Python / Node.js if needed.
  pause
)
endlocal
