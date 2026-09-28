$ErrorActionPreference = 'Stop'

$projectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'
$credentialFile = Join-Path $projectRoot '.env'
$logDirectory = Join-Path $projectRoot '.local'
$logFile = Join-Path $logDirectory 'relay.log'

if (-not (Test-Path -LiteralPath $python)) {
    throw "Python virtual environment not found: $python"
}
if (-not (Test-Path -LiteralPath $credentialFile)) {
    throw "Telegram credentials not found: $credentialFile"
}

New-Item -ItemType Directory -Path $logDirectory -Force | Out-Null
Set-Location -LiteralPath $projectRoot

while ($true) {
    "$(Get-Date -Format o) Starting relay" | Out-File -LiteralPath $logFile -Append -Encoding utf8
    # Windows PowerShell surfaces a native process's stderr as an error record.
    # Keep writing those records to the log instead of stopping the supervisor.
    $ErrorActionPreference = 'Continue'
    & $python -u -m src.telegram.listener 2>&1 | Out-File -LiteralPath $logFile -Append -Encoding utf8
    $ErrorActionPreference = 'Stop'
    "$(Get-Date -Format o) Relay stopped; restarting in 15 seconds" | Out-File -LiteralPath $logFile -Append -Encoding utf8
    Start-Sleep -Seconds 15
}
