# Personal Growth System — one-time setup
# Run this once from the repo directory: .\install.ps1

$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "Installing Python dependencies..."
pip install fastmcp starlette pydantic
if ($LASTEXITCODE -ne 0) {
    Write-Host "pip failed. Make sure Python is installed and on your PATH."
    exit 1
}

Write-Host ""
Write-Host "Creating data directory..."
$dataDir = "$env:USERPROFILE\personal-growth-data"
New-Item -ItemType Directory -Force -Path $dataDir | Out-Null
Write-Host "  Data will be stored at: $dataDir"

Write-Host ""
Write-Host "Checking for ngrok..."
if (-not (Get-Command ngrok -ErrorAction SilentlyContinue)) {
    Write-Host "  ngrok not found. Download it from https://ngrok.com/download"
    Write-Host "  Unzip ngrok.exe and add it to a folder on your PATH (e.g. C:\tools)"
    Write-Host "  Then run: ngrok config add-authtoken YOUR_AUTHTOKEN"
    Write-Host "  And claim your free static domain at: https://dashboard.ngrok.com/domains"
} else {
    Write-Host "  ngrok found."
}

Write-Host ""
Write-Host "Next steps:"
Write-Host "  1. Edit start.ps1 — set MCP_AUTH_TOKEN and NGROK_DOMAIN"
Write-Host "  2. Run .\start.ps1 to test".
Write-Host ""
