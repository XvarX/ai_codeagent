@echo off
setlocal enabledelayedexpansion
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
set NPM_ERR=%ERRORLEVEL%
popd
if %NPM_ERR% NEQ 0 (
    echo Frontend install failed!
    pause
    exit /b %NPM_ERR%
)

echo.
echo ================================
echo Downloading ripgrep (rg.exe)...
echo ================================
set RG_VERSION=15.1.0
set RG_URL=https://github.com/BurntSushi/ripgrep/releases/download/%RG_VERSION%/ripgrep-%RG_VERSION%-x86_64-pc-windows-msvc.zip
set RG_ZIP=%TEMP%\ripgrep.zip
set RG_EXTRACT=%TEMP%\ripgrep_extract
set RG_DEST=%~dp0agentcore\rg.exe

echo URL: !RG_URL!
echo.

powershell -Command "(New-Object Net.WebClient).DownloadFile('!RG_URL!', '!RG_ZIP!')"
if not exist "!RG_ZIP!" (
    echo Download failed! Please download ripgrep manually from:
    echo   https://github.com/BurntSushi/ripgrep/releases
    pause
    exit /b 1
)
echo Downloaded.

echo Extracting...
if exist "!RG_EXTRACT!" rmdir /S /Q "!RG_EXTRACT!"
powershell -Command "Expand-Archive -Path '!RG_ZIP!' -DestinationPath '!RG_EXTRACT!' -Force"

echo Installing...
for /r "!RG_EXTRACT!" %%f in (rg.exe) do (
    copy /Y "%%f" "!RG_DEST!" >nul
    echo   rg.exe -^> agentcore\
)

if not exist "%~dp0build\agentcore" mkdir "%~dp0build\agentcore"
copy /Y "!RG_DEST!" "%~dp0build\agentcore\rg.exe" >nul
echo   rg.exe -^> build\agentcore\

del /Q "!RG_ZIP!" 2>nul
rmdir /S /Q "!RG_EXTRACT!" 2>nul

echo.
echo ================================
echo All dependencies installed successfully!
echo ================================
pause
