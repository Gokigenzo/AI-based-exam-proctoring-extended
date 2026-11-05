$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath (Resolve-Path (Join-Path $PSScriptRoot '../..'))
$releasePath = Join-Path $PWD 'release/v1'
if (Test-Path -LiteralPath $releasePath) { throw 'release/v1 already exists. Preserve it; use a new version for a later build.' }
$buildPython = Join-Path $PWD '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $buildPython)) { throw 'A build-only Python environment is required.' }
$env:TEMP = Join-Path $PWD '.tmp'
$env:TMP = $env:TEMP
New-Item -ItemType Directory -Path $releasePath -Force | Out-Null
$embedZip = Join-Path $PWD '.tmp/python-3.12.10-embed-amd64.zip'
if (-not (Test-Path -LiteralPath $embedZip)) {
    Invoke-WebRequest 'https://www.python.org/ftp/python/3.12.10/python-3.12.10-embed-amd64.zip' -OutFile $embedZip
}
Expand-Archive -LiteralPath $embedZip -DestinationPath (Join-Path $releasePath 'runtime')
[IO.File]::WriteAllText((Join-Path $releasePath 'runtime/python312._pth'), "python312.zip`n.`nLib/site-packages`n../app`nimport site`n")
& $buildPython -m pip install --target (Join-Path $releasePath 'runtime/Lib/site-packages') -r packaging/windows/requirements-portable.txt -c packaging/windows/constraints-portable.txt --only-binary=:all: --no-compile
if ($LASTEXITCODE -ne 0) { throw 'Portable runtime installation failed' }
& $buildPython packaging/windows/assemble_v1.py
if ($LASTEXITCODE -ne 0) { throw 'Assembly failed' }
Copy-Item -LiteralPath packaging/windows/HUONG_DAN.txt -Destination (Join-Path $releasePath 'HUONG_DAN.txt')
$compiler = Join-Path $env:WINDIR 'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
& $compiler /nologo /target:winexe /platform:x64 "/out:$releasePath\ExamWatch.exe" /reference:System.Windows.Forms.dll /reference:System.Drawing.dll (Join-Path $PWD 'packaging/windows/Launcher.cs')
if ($LASTEXITCODE -ne 0) { throw 'Launcher compilation failed' }
New-Item -ItemType Directory -Path (Join-Path $releasePath 'prerequisites') -Force | Out-Null
Invoke-WebRequest 'https://aka.ms/vs/17/release/vc_redist.x64.exe' -OutFile (Join-Path $releasePath 'prerequisites/vc_redist.x64.exe') -UserAgent 'Mozilla/5.0'
if ((Get-AuthenticodeSignature (Join-Path $releasePath 'prerequisites/vc_redist.x64.exe')).Status -ne 'Valid') { throw 'VC runtime signature invalid' }
Invoke-WebRequest 'https://creativecommons.org/licenses/by-nc-nd/4.0/legalcode.txt' -OutFile (Join-Path $releasePath 'licenses/Zipformer-CC-BY-NC-ND-4.0.txt')
Write-Host 'Build assembled. Run portable QA before publishing ZIP; no user data is copied.'
