@echo off
cd /d "%~dp0"
echo Downloading all dependencies to .\offline_deps ...

mkdir offline_deps 2>nul

pip download -r requirements.txt -d offline_deps

echo.
echo Done! Dependencies saved to offline_deps\
echo Copy this entire project folder to the target machine, then run:
echo   pip install --no-index --find-links=offline_deps -r requirements.txt
echo   cp config.example.yaml config.yaml   (edit API key)
echo   python main.py
pause
