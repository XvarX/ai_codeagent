@echo off
cd /d "%~dp0"
echo ========================================
echo   AI Code Agent - Build Standalone EXE
echo ========================================
echo.

echo [1/2] Installing PyInstaller...
pip install pyinstaller -q

echo [2/2] Building...
pyinstaller --onedir --windowed ^
    --name AI_CodeAgent ^
    --hidden-import flet ^
    --hidden-import flet_core ^
    --hidden-import flet_desktop ^
    --hidden-import flet_runtime ^
    --hidden-import yaml ^
    --hidden-import anthropic ^
    --hidden-import openai ^
    --hidden-import pydantic ^
    --collect-all flet ^
    main.py

echo.
echo ========================================
echo   Done: dist\AI_CodeAgent\
echo ========================================
echo.
echo To distribute: copy the folder and add config.yaml inside:
echo   dist\AI_CodeAgent\
echo     AI_CodeAgent.exe
echo     config.yaml  ^<-- copy from config.example.yaml, add API keys
echo.
pause
