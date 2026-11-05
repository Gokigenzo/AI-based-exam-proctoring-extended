$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
Push-Location $projectRoot
try {
    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) { throw 'Developer setup requires uv. End users use the portable ZIP built by build-portable.ps1.' }
    $env:UV_CACHE_DIR = Join-Path $projectRoot '.cache/uv'
    uv sync --extra local --extra dev --frozen
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed' }
    $modelRoot = Join-Path $env:LOCALAPPDATA 'ExamWatch/models'
    & '.venv/Scripts/python.exe' scripts/prepare_models.py --root $modelRoot
    if ($LASTEXITCODE -ne 0) { throw 'Some models unavailable. Read the preparation output.' }
} finally { Pop-Location }
