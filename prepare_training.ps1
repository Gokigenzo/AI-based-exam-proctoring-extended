param([switch]$Cpu)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$env:TEMP = Join-Path $PSScriptRoot '.tmp'
$env:TMP = $env:TEMP
New-Item -ItemType Directory -Path $env:TEMP -Force | Out-Null
& .venv/Scripts/python.exe -m venv .venv-training
if ($LASTEXITCODE -ne 0) { throw 'Cannot create training environment.' }
$torchIndex = if ($Cpu) { 'https://download.pytorch.org/whl/cpu' } else { 'https://download.pytorch.org/whl/cu128' }
& .venv-training/Scripts/python.exe -m pip install torch==2.7.1 --index-url $torchIndex
if ($LASTEXITCODE -ne 0) { throw 'Cannot install PyTorch.' }
& .venv-training/Scripts/python.exe -m pip install -r requirements-training.txt
if ($LASTEXITCODE -ne 0) { throw 'Cannot install training dependencies.' }
& .venv-training/Scripts/python.exe -c 'import torch; print("CUDA:", torch.cuda.is_available()); print(torch.cuda.get_device_name(0) if torch.cuda.is_available() else "CPU")'
if ($LASTEXITCODE -ne 0) { throw 'PyTorch import failed.' }
if (-not $Cpu) {
    & .venv-training/Scripts/python.exe -c 'import torch; assert torch.cuda.is_available(), "CUDA unavailable: check NVIDIA driver or use -Cpu"; x=torch.ones((32,32),device="cuda"); print("GPU compute:", (x@x).mean().item())'
    if ($LASTEXITCODE -ne 0) { throw 'CUDA compute failed. Check the NVIDIA driver or use -Cpu.' }
}
