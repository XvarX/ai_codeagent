@echo off
cd /d "%~dp0"
echo ========================================
echo   AI Code Agent - Build Standalone EXE
echo ========================================
echo.

echo [1/2] Installing PyInstaller...
pip install pyinstaller -q

echo [2/2] Building...
pyinstaller --onefile --windowed ^
    --name AI_CodeAgent ^
    --hidden-import PySide6 ^
    --hidden-import yaml ^
    --hidden-import anthropic ^
    --hidden-import openai ^
    --hidden-import pydantic ^
    --collect-all PySide6 ^
    main.py

echo.
echo ========================================
echo   Done: dist\AI_CodeAgent.exe
echo ========================================
echo.
echo To distribute: put these two files together:
echo   1. dist\AI_CodeAgent.exe
echo   2. config.yaml (copy from config.example.yaml and add API keys)
echo.
pause
