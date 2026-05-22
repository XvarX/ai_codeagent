@echo off
cd /d "%~dp0"
echo ========================================
echo   AI Code Agent - Build with Flet Build
echo ========================================
echo.
echo Flet Build wraps Python app in a native Flutter desktop shell.
echo First run will auto-install Flutter SDK (one-time).
echo.

flet build windows ^
    --no-cdn ^
    --product "AI Code Agent" ^
    --description "AI Code Agent" ^
    -y

echo.
echo ========================================
echo   Done: build\windows\
echo ========================================
echo.
pause
