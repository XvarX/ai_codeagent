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
echo   (Install NSIS for installer: winget install NSIS.NSIS)
cd ui
call npx tauri build --no-bundle
if %ERRORLEVEL% neq 0 (
    cd ..
    echo [FAIL] Tauri build failed
    pause
    exit /b 1
)
cd ..

echo [3/3] Assembling output to build\dist\...
set OUT=build\dist
if exist "%OUT%" rmdir /S /Q "%OUT%"
mkdir "%OUT%"

copy /Y ui\src-tauri\target\release\ai-code-agent.exe "%OUT%\" >nul
xcopy /E /Y /I build\agentcore "%OUT%\agentcore" >nul
echo   -^> Done
echo.

echo ============================================
echo   Build complete!
echo   App     : build\dist\ai-code-agent.exe
echo   Backend : build\dist\agentcore\
echo   Copy the entire build\dist\ folder to distribute
echo ============================================
echo.
echo Cleaning intermediate files...
del /Q build\agentcore.exe 2>nul
rmdir /S /Q build\agentcore 2>nul
rmdir /S /Q build\pyinstaller-tmp 2>nul
rmdir /S /Q ui\src-tauri\build 2>nul
rmdir /S /Q ui\dist 2>nul
rmdir /S /Q ui\dist-electron 2>nul
echo Done.
pause
