$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
$runtime = Join-Path $projectRoot '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $runtime)) { throw 'Run scripts/setup-windows.ps1 first, or use the portable distribution.' }
& $runtime (Join-Path $PSScriptRoot 'launcher.py')
