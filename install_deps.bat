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
pushd "%~dp0ui"
npm install
if %ERRORLEVEL% NEQ 0 (
    popd
    echo Frontend install failed!
    pause
    exit /b %ERRORLEVEL%
)
popd

echo.
echo ================================
echo Downloading ripgrep (rg.exe)...
echo ================================
python "%~dp0install_deps.py"
if %ERRORLEVEL% NEQ 0 (
    pause
    exit /b %ERRORLEVEL%
)

echo.
echo ================================
echo All dependencies installed successfully!
echo ================================
pause
