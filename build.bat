@echo off
chcp 65001 >nul 2>&1
cd /d "%~dp0"

echo ============================================
echo   AI Code Agent - One-Click Build
echo ============================================
echo.

echo [1/3] Building Python backend (PyInstaller)...
pyinstaller agentcore.spec --distpath build --workpath build\pyinstaller-tmp --noconfirm
if %ERRORLEVEL% neq 0 (
    echo [FAIL] Python build failed
    pause
    exit /b 1
)
echo   -^> build\agentcore\ OK
echo.

echo [2/3] Building Tauri app...
cd ui
call npx tauri build --no-bundle
if %ERRORLEVEL% neq 0 (
    cd ..
    echo [FAIL] Tauri build failed
    pause
    exit /b 1
)
cd ..

echo [3/3] Copying exe to build\...
copy /Y ui\src-tauri\target\release\ai-code-agent.exe build\ >nul
echo   -^> Done
echo.

echo ============================================
echo   Build complete!
echo   build\ai-code-agent.exe
echo   build\agentcore\
echo   Copy the entire build\ folder to distribute
echo ============================================
echo.
echo Cleaning intermediate files...
del /Q build\agentcore.exe 2>nul
rmdir /S /Q build\pyinstaller-tmp 2>nul
rmdir /S /Q ui\src-tauri\build 2>nul
rmdir /S /Q ui\dist 2>nul
echo Done.
pause
