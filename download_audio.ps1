param([int]$Workers = 16)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$env:PYTHONIOENCODING = 'utf-8'
$env:HF_HUB_OFFLINE = '0'
& .venv-training/Scripts/python.exe scripts/download_audio_dataset.py --workers $Workers
if ($LASTEXITCODE -ne 0) { throw 'Download incomplete. Rerun this command to resume.' }
& .venv-training/Scripts/python.exe scripts/index_audio_dataset.py
if ($LASTEXITCODE -ne 0) { throw 'Dataset indexing failed.' }
