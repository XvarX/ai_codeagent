@echo off
cd /d "%~dp0"
echo ========================================
echo   AI Code Agent - Build EXE
echo ========================================
echo.

flet pack main.py --name AI_CodeAgent --onedir -y

echo.
echo ========================================
echo   Done: dist\AI_CodeAgent\
echo ========================================
echo.
pause
