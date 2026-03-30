@echo off

rem =========================================================
rem  Edit these two lines before running
set MCP_AUTH_TOKEN=3BcEnO2hl8OtS9RGF04AUqlrkwl_7EQ1vfJnxnWCFUBqoGzWR
set NGROK_DOMAIN=https://sharmaine-unprovoked-rayna.ngrok-free.dev/mcp
rem =========================================================

set DATA_DIR=%USERPROFILE%\personal-growth-data
set PORT=3000

if not exist "%DATA_DIR%" mkdir "%DATA_DIR%"
if not exist "%DATA_DIR%\logs" mkdir "%DATA_DIR%\logs"

echo Stopping any previous instances...
taskkill /f /im ngrok.exe >nul 2>&1

echo Starting MCP server...
start /min "" python "%~dp0main.py" >> "%DATA_DIR%\logs\server.log" 2>&1

timeout /t 2 /nobreak >nul

echo Starting ngrok tunnel...
start /min "" ngrok http --domain=%NGROK_DOMAIN% %PORT% --log stdout >> "%DATA_DIR%\logs\ngrok.log" 2>&1

echo.
echo Running.
echo.
echo   MCP endpoint : https://%NGROK_DOMAIN%/mcp
echo   Auth token   : %MCP_AUTH_TOKEN%
echo   Logs         : %DATA_DIR%\logs
echo.
echo Add to Claude as MCP server:
echo   URL    : https://%NGROK_DOMAIN%/mcp
echo   Header : Authorization: Bearer %MCP_AUTH_TOKEN%
echo.
