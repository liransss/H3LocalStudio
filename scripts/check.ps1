$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
Push-Location $projectRoot
try {
    & npm.cmd run build
    & "backend\.venv\Scripts\python.exe" -m pytest
}
finally {
    Pop-Location
}

