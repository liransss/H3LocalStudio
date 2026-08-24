param(
    [switch]$Mock
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$backendRoot = Join-Path $projectRoot "backend"
$venvPython = Join-Path $backendRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $venvPython)) {
    throw "Backend virtual environment is missing. Run scripts\setup.ps1 first."
}

if ($Mock) {
    $env:H3_MOCK_MODE = "true"
}

Push-Location $backendRoot
try {
    & $venvPython -m uvicorn app.main:app --host 127.0.0.1 --port 7331 --reload
}
finally {
    Pop-Location
}

