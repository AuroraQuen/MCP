# Personal Growth System — startup script
# Edit the two values below, then run: .\start.ps1
#
# To run on boot (Task Scheduler):
#   1. Open Task Scheduler
#   2. Create Task (not Basic Task)
#   3. General tab: check "Run whether user is logged on or not" is NOT checked
#                   check "Run only when user is logged on"
#   4. Triggers tab: New > "At log on" > your user
#   5. Actions tab: New >
#        Program:   powershell.exe
#        Arguments: -WindowStyle Hidden -ExecutionPolicy Bypass -File "C:\path\to\start.ps1"
#   6. Conditions tab: uncheck "Start only if AC power"
#   7. OK — enter your Windows password when prompted

# ── Edit these two lines ──────────────────────────────────────────────────────
$AUTH_TOKEN  = "replace-with-your-secret-token"   # anything strong, keep it private
$NGROK_DOMAIN = "replace-with-your-ngrok-domain"  # e.g. sturdy-fox-quietly.ngrok-free.app
# ─────────────────────────────────────────────────────────────────────────────

$env:MCP_AUTH_TOKEN = $AUTH_TOKEN
$env:DATA_DIR       = "$env:USERPROFILE\personal-growth-data"
$env:PORT           = "3000"

$repoDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$logDir  = "$env:USERPROFILE\personal-growth-data\logs"

New-Item -ItemType Directory -Force -Path $env:DATA_DIR | Out-Null
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

$serverLog = "$logDir\server.log"
$ngrokLog  = "$logDir\ngrok.log"

# Kill any previous instances
Get-Process -Name python  -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -like "*main.py*" } | Stop-Process -Force -ErrorAction SilentlyContinue
Get-Process -Name ngrok   -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue

Start-Sleep -Seconds 1

# Start MCP server
$serverProc = Start-Process -FilePath "python" `
    -ArgumentList "`"$repoDir\main.py`"" `
    -WorkingDirectory $repoDir `
    -RedirectStandardOutput $serverLog `
    -RedirectStandardError  "$logDir\server-err.log" `
    -WindowStyle Hidden `
    -PassThru

Start-Sleep -Seconds 2

# Start ngrok tunnel
$ngrokProc = Start-Process -FilePath "ngrok" `
    -ArgumentList "http", "--domain=$NGROK_DOMAIN", "3000", "--log=stdout" `
    -RedirectStandardOutput $ngrokLog `
    -WindowStyle Hidden `
    -PassThru

Write-Host ""
Write-Host "Personal Growth System running."
Write-Host ""
Write-Host "  MCP endpoint : https://$NGROK_DOMAIN/mcp"
Write-Host "  Auth token   : $AUTH_TOKEN"
Write-Host "  Data dir     : $($env:DATA_DIR)"
Write-Host "  Logs         : $logDir"
Write-Host ""
Write-Host "Add to Claude as MCP server:"
Write-Host "  URL    : https://$NGROK_DOMAIN/mcp"
Write-Host "  Header : Authorization: Bearer $AUTH_TOKEN"
Write-Host ""
