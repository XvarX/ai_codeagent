@echo off
cd /d "%~dp0"
echo ========================================
echo   AI Code Agent - 打包成独立 exe
echo ========================================
echo.

echo [1/2] 安装 PyInstaller...
pip install pyinstaller -q

echo [2/2] 打包中...
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
echo   完成！输出: dist\AI_CodeAgent.exe
echo ========================================
echo.
echo 发给别人用：把以下两个文件放在同一个目录
echo   1. dist\AI_CodeAgent.exe
echo   2. config.yaml (从 config.example.yaml 复制并填 key)
echo.
pause
