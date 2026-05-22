@echo off
cd /d "%~dp0"
echo ========================================
echo   AI Code Agent - Build Standalone EXE
echo ========================================
echo.

echo Building with Flet Pack...
flet pack main.py ^
    --name AI_CodeAgent ^
    --onedir ^
    --product-name "AI Code Agent" ^
    --file-description "AI Code Agent" ^
    -y

echo.
echo ========================================
echo   Done: dist\AI_CodeAgent\
echo ========================================
echo.
echo Place config.yaml next to AI_CodeAgent.exe before running.
echo.
pause
