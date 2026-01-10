# SysMon - System Monitor Launcher
# Activates the virtual environment and starts the server

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$venvActivate = Join-Path $scriptDir ".venv\Scripts\Activate.ps1"
$mainPy = Join-Path $scriptDir "backend\main.py"

# Activate virtual environment
if (Test-Path $venvActivate) {
    & $venvActivate
} else {
    Write-Host "Virtual environment not found at: $venvActivate" -ForegroundColor Red
    Write-Host "Run: python -m venv .venv && .\.venv\Scripts\Activate.ps1 && pip install -r backend\requirements.txt" -ForegroundColor Yellow
    exit 1
}

# Run the server
if (Test-Path $mainPy) {
    python $mainPy
} else {
    Write-Host "main.py not found at: $mainPy" -ForegroundColor Red
    exit 1
}
