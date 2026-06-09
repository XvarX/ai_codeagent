@echo off
chcp 65001 >nul 2>&1
cd /d "%~dp0"
echo Starting dev server...
cd ui && npm run tauri dev
pause
