@echo off
chcp 65001 >nul 2>&1
echo ============================================
echo   AI Code Agent - One-Click Build
echo ============================================
echo.

echo [1/2] Building Python backend (PyInstaller)...
pyinstaller agentcore.spec --distpath build --workpath build\pyinstaller-tmp --noconfirm
if %ERRORLEVEL% neq 0 (
    echo [FAIL] Python build failed
    exit /b 1
)
echo   -^> build\agentcore.exe OK
echo.

echo [2/2] Building Tauri app...
cd ui
call npm run tauri build
if %ERRORLEVEL% neq 0 (
    echo [FAIL] Tauri build failed
    exit /b 1
)
cd ..
echo   -^> src-tauri\target\release\ OK
echo.

echo ============================================
echo   Build complete!
echo   Backend : build\agentcore.exe
echo   Installer : ui\src-tauri\target\release\bundle\
echo ============================================
