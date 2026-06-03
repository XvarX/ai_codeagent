@echo off
cd /d "%~dp0"
echo Starting backend...
python -m agentcore.main --ws --port 18765 --reload
pause
