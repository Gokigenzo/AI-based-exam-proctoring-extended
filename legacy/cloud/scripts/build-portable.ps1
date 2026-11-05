param([string]$ModelRoot = (Join-Path (Split-Path $PSScriptRoot -Parent) 'models'), [switch]$Resume)
$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Split-Path $PSScriptRoot -Parent)).Path
$outputRoot = Join-Path $projectRoot 'dist/ExamWatch'
if ((Test-Path -LiteralPath $outputRoot) -and -not $Resume) { throw 'dist/ExamWatch already exists. Use -Resume for an interrupted build, or move the old distribution.' }
$env:UV_CACHE_DIR = Join-Path $projectRoot '.cache/uv'
$env:UV_PYTHON_INSTALL_DIR = Join-Path $projectRoot '.cache/portable-python'
Push-Location $projectRoot
try {
    uv python install 3.12.10 --no-bin
    if ($LASTEXITCODE -ne 0) { throw 'Portable Python download failed' }
    $pythonPath = (uv python find --managed-python 3.12.10).Trim()
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $pythonPath)) { throw 'Cannot locate managed Python' }
    New-Item -ItemType Directory -Path $outputRoot -Force | Out-Null
    if (-not (Test-Path -LiteralPath (Join-Path $outputRoot 'runtime/python.exe'))) {
        Copy-Item -LiteralPath (Split-Path $pythonPath -Parent) -Destination (Join-Path $outputRoot 'runtime') -Recurse
    }
    New-Item -ItemType Directory -Path (Join-Path $projectRoot 'build') -Force | Out-Null
    uv export --frozen --extra local --no-dev --no-emit-project --format requirements-txt --output-file build/portable-requirements.txt | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Locked dependency export failed' }
    $runtimePython = Join-Path $outputRoot 'runtime/python.exe'
    # This is our copied runtime under dist/, never the managed source installation.
    uv pip install --python $runtimePython --break-system-packages --requirements build/portable-requirements.txt
    if ($LASTEXITCODE -ne 0) { throw 'Portable dependency install failed' }
    $packageDestination = Join-Path $outputRoot 'runtime/Lib/site-packages/examwatch'
    New-Item -ItemType Directory -Path $packageDestination -Force | Out-Null
    Get-ChildItem -LiteralPath (Join-Path $projectRoot 'packages/examwatch') | Copy-Item -Destination $packageDestination -Recurse -Force
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'launcher.py') -Destination (Join-Path $outputRoot 'launcher.py')
    $modelDestination = Join-Path $outputRoot 'models'
    New-Item -ItemType Directory -Path $modelDestination -Force | Out-Null
    Get-ChildItem -LiteralPath $ModelRoot | Copy-Item -Destination $modelDestination -Recurse -Force
    '@echo off' + "`r`n" + 'cd /d "%~dp0"' + "`r`n" + 'set EXAMWATCH_BUNDLED_MODELS=%~dp0models' + "`r`n" + 'runtime\python.exe launcher.py' | Set-Content -LiteralPath (Join-Path $outputRoot 'Start ExamWatch.cmd') -Encoding ascii
    Copy-Item -LiteralPath (Join-Path $projectRoot 'docs/WINDOWS.md') -Destination (Join-Path $outputRoot 'HUONG_DAN.md')
    Copy-Item -LiteralPath (Join-Path $projectRoot 'THIRD_PARTY_NOTICES.md') -Destination $outputRoot
    & $runtimePython -c "import imageio_ffmpeg,subprocess; from pathlib import Path; p=Path(r'dist/ExamWatch'); f=imageio_ffmpeg.get_ffmpeg_exe(); (p/'FFMPEG-LICENSE.txt').write_bytes(subprocess.check_output([f,'-L'],stderr=subprocess.STDOUT)); (p/'FFMPEG-BUILD.txt').write_bytes(subprocess.check_output([f,'-buildconf'],stderr=subprocess.STDOUT))"
    & $runtimePython -c "import cv2,mediapipe,torch,onnxruntime,sounddevice; from examwatch.local.adapters import checked_model; from pathlib import Path; r=Path(r'dist/ExamWatch/models'); [checked_model(r,n) for n in ('pose','yunet','phowhisper-base','fer')]; print('Portable imports and model checks passed')"
    if ($LASTEXITCODE -ne 0) { throw 'Portable validation failed; do not distribute this directory' }
    Write-Host "Portable directory ready: $outputRoot"
    Write-Host 'Copy the whole directory to another Windows x64 machine; launch Start ExamWatch.cmd.'
} finally { Pop-Location }
