@echo off
cd /d "%~dp0"
echo Starting backend...
python agentcore/main.py --ws --port 18765
pause
