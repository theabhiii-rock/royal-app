$project = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) {
  Write-Host "Python was not found. Install Python 3.11+ and run this file again."
  Read-Host "Press Enter to close"
  exit 1
}

Set-Location $project
Write-Host "Starting Royal BetKing educational demo..."
Write-Host "Open http://127.0.0.1:8080 in your browser."
Write-Host "Use the private admin key configured in backend/.env."
$env:RBK_PORT = "8080"
& $python.Source backend\standalone_server.py
