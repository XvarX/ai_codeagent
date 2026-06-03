@echo off
cd /d "%~dp0"

echo ================================
echo Installing backend dependencies...
echo ================================
pip install -r requirements.txt
if %ERRORLEVEL% NEQ 0 (
    echo Backend install failed!
    pause
    exit /b %ERRORLEVEL%
)

echo.
echo ================================
echo Installing frontend dependencies...
echo ================================
cd ui
npm install
if %ERRORLEVEL% NEQ 0 (
    echo Frontend install failed!
    pause
    exit /b %ERRORLEVEL%
)

echo.
echo All dependencies installed successfully!
pause
