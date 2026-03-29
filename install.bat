@echo off
echo.
echo Installing Python dependencies...
pip install fastmcp starlette pydantic
if %errorlevel% neq 0 (
    echo pip failed. Make sure Python is installed and on your PATH.
    pause
    exit /b 1
)
 
echo.
echo Creating data directory...
if not exist "%USERPROFILE%\personal-growth-data" mkdir "%USERPROFILE%\personal-growth-data"
echo Data will be stored at: %USERPROFILE%\personal-growth-data
 
echo.
echo Done. Next steps:
echo   1. Edit start.bat -- set your token and ngrok domain
echo   2. Double-click start.bat to test
echo   3. Add start.bat to Task Scheduler to run on login
echo.
pause
 
