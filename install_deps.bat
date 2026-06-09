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
cd ..

echo.
echo ================================
echo Downloading ripgrep (rg.exe)...
echo ================================
set RG_VERSION=15.1.0
set RG_URL=https://github.com/BurntSushi/ripgrep/releases/download/%RG_VERSION%/ripgrep-%RG_VERSION%-x86_64-pc-windows-msvc.zip
set RG_ZIP=%TEMP%\ripgrep.zip
set RG_EXTRACT=%TEMP%\ripgrep_extract

curl -L -o "%RG_ZIP%" "%RG_URL%"
if %ERRORLEVEL% NEQ 0 (
    echo Download failed! Please download ripgrep manually from:
    echo   https://github.com/BurntSushi/ripgrep/releases
    pause
    exit /b %ERRORLEVEL%
)

echo Extracting...
if exist "%RG_EXTRACT%" rmdir /S /Q "%RG_EXTRACT%"
mkdir "%RG_EXTRACT%"
powershell -Command "Expand-Archive -Path '%RG_ZIP%' -DestinationPath '%RG_EXTRACT%' -Force"

echo Installing rg.exe...
rem Find rg.exe in the extracted tree
for /r "%RG_EXTRACT%" %%f in (rg.exe) do (
    copy /Y "%%f" "%~dp0agentcore\rg.exe" >nul
    echo   -^> agentcore\rg.exe
)

if not exist "%~dp0build\agentcore" mkdir "%~dp0build\agentcore"
copy /Y "%~dp0agentcore\rg.exe" "%~dp0build\agentcore\rg.exe" >nul
echo   -^> build\agentcore\rg.exe

rem Cleanup
del /Q "%RG_ZIP%" 2>nul
rmdir /S /Q "%RG_EXTRACT%" 2>nul

echo.
echo ================================
echo All dependencies installed successfully!
echo ================================
pause
