$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$venvPython = Join-Path $projectRoot "backend\.venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $venvPython)) {
    py -3.12 -m venv (Join-Path $projectRoot "backend\.venv")
}

& $venvPython -m pip install --disable-pip-version-check -r (Join-Path $projectRoot "backend\requirements-dev.txt")
& npm.cmd install --prefix $projectRoot

Write-Host "H3 Local Studio development dependencies are ready." -ForegroundColor Green
Write-Host "Run: npm.cmd run dev"

