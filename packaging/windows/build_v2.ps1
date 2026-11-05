$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath (Resolve-Path (Join-Path $PSScriptRoot '../..'))
$destination = Join-Path $PWD 'release/v2'
if (Test-Path -LiteralPath $destination) { throw 'release/v2 exists; preserve it and build from a clean checkout.' }
$buildPython = Join-Path $PWD '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $buildPython)) { throw 'Run prepare.ps1 first.' }
$env:TEMP = Join-Path $PWD '.tmp'
$env:TMP = $env:TEMP
New-Item -ItemType Directory -Path $env:TEMP -Force | Out-Null
New-Item -ItemType Directory -Path $destination -Force | Out-Null
$embedZip = Join-Path $PWD '.tmp/python-3.12.10-embed-amd64.zip'
if (-not (Test-Path -LiteralPath $embedZip)) {
    Invoke-WebRequest 'https://www.python.org/ftp/python/3.12.10/python-3.12.10-embed-amd64.zip' -OutFile $embedZip
}
Expand-Archive -LiteralPath $embedZip -DestinationPath (Join-Path $destination 'runtime')
[IO.File]::WriteAllText((Join-Path $destination 'runtime/python312._pth'), "python312.zip`n.`nLib/site-packages`n../app`nimport site`n")
& $buildPython -m pip install --target (Join-Path $destination 'runtime/Lib/site-packages') -r packaging/windows/requirements-portable.txt -c packaging/windows/constraints-portable.txt --only-binary=:all: --no-compile
if ($LASTEXITCODE -ne 0) { throw 'Runtime installation failed' }
& $buildPython packaging/windows/assemble_v1.py --version v2
if ($LASTEXITCODE -ne 0) { throw 'Assembly failed' }
$source = [IO.File]::ReadAllText((Join-Path $PSScriptRoot 'Launcher.cs')).Replace('ExamWatch v1','ExamWatch v2')
$generated = Join-Path $PWD '.tmp/Launcher_v2.cs'
[IO.File]::WriteAllText($generated,$source,[Text.UTF8Encoding]::new($false))
$compiler = Join-Path $env:WINDIR 'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
& $compiler /nologo /target:winexe /platform:x64 "/out:$destination\ExamWatch.exe" /reference:System.Windows.Forms.dll /reference:System.Drawing.dll $generated
if ($LASTEXITCODE -ne 0) { throw 'Launcher compilation failed' }
$guide = [IO.File]::ReadAllText((Join-Path $PSScriptRoot 'HUONG_DAN.txt')).Replace('v1','v2')
[IO.File]::WriteAllText((Join-Path $destination 'HUONG_DAN.txt'),$guide,[Text.UTF8Encoding]::new($false))
foreach ($doc in @('POSE_ANGLE_ALERTS.md','REALTIME_OPTIMIZATION.md','TRACKING_VIDEO_UPDATE.md')) {
    Copy-Item -LiteralPath $doc -Destination (Join-Path $destination $doc)
}
New-Item -ItemType Directory -Path (Join-Path $destination 'prerequisites') -Force | Out-Null
$vc = Join-Path $destination 'prerequisites/vc_redist.x64.exe'
Invoke-WebRequest 'https://aka.ms/vs/17/release/vc_redist.x64.exe' -OutFile $vc -UserAgent 'Mozilla/5.0'
if ((Get-AuthenticodeSignature $vc).Status -ne 'Valid') { throw 'VC runtime signature invalid' }
Invoke-WebRequest 'https://creativecommons.org/licenses/by-nc-nd/4.0/legalcode.txt' -OutFile (Join-Path $destination 'licenses/Zipformer-CC-BY-NC-ND-4.0.txt')
Write-Host 'v2 assembled. Run tests and portable self-test, then archive --version v2.'
