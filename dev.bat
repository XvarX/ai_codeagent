@echo off
chcp 65001 >nul 2>&1
echo Starting dev server...
cd ui && npm run tauri dev
