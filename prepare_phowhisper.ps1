# One-time conversion only. The normal application never imports PyTorch.
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$env:TEMP = Join-Path $PSScriptRoot '.tmp'
$env:TMP = $env:TEMP
$env:OMP_NUM_THREADS = '2'
New-Item -ItemType Directory -Path $env:TEMP -Force | Out-Null
if (-not (Test-Path -LiteralPath '.venv/Scripts/python.exe')) { throw 'Install the runtime dependencies with prepare.ps1 first, then run this conversion script.' }
& .venv/Scripts/python.exe -m venv .tmp/model-converter
if ($LASTEXITCODE -ne 0) { throw 'Could not create isolated conversion environment.' }
& .tmp/model-converter/Scripts/python.exe -m pip install --only-binary=:all: torch==2.7.1 --index-url https://download.pytorch.org/whl/cpu
if ($LASTEXITCODE -ne 0) { throw 'Could not install CPU conversion dependency.' }
& .tmp/model-converter/Scripts/python.exe -m pip install --only-binary=:all: transformers==4.51.3 huggingface-hub==0.30.2 numpy==1.26.4
if ($LASTEXITCODE -ne 0) { throw 'Could not install conversion dependency.' }
& .tmp/model-converter/Scripts/python.exe scripts/convert_phowhisper.py
if ($LASTEXITCODE -ne 0) { throw 'Model conversion failed.' }
Write-Host 'Local PhoWhisper INT8 is ready. The temporary converter is not needed by start.ps1.'
