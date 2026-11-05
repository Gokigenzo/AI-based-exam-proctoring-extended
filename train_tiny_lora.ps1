param([int]$Steps = 300)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$env:PYTHONIOENCODING = 'utf-8'
$env:OMP_NUM_THREADS = '2'
$env:HF_HUB_OFFLINE = '0'
$tinyPython = Join-Path $PSScriptRoot '.venv-training/Scripts/python.exe'
$tinyRevision = 'cc51d32be916efebde04ff549854fa1741cb5c02'
& $tinyPython scripts/prepare_tiny_dataset.py
if ($LASTEXITCODE -ne 0) { throw 'Small dataset preparation failed.' }
& $tinyPython scripts/train_stt.py --dataset Audio-dataset/vivos-small --model vinai/PhoWhisper-tiny --revision $tinyRevision --lora --lora-rank 8 --augment --epochs 2 --max-steps $Steps --eval-steps 50 --max-eval-samples 64 --batch-size 2 --gradient-accumulation 4 --learning-rate 5e-5 --early-stopping 2 --output training-runs/phowhisper-tiny-lora
if ($LASTEXITCODE -ne 0) { throw 'Tiny LoRA training failed.' }
& $tinyPython scripts/export_stt.py --checkpoint training-runs/phowhisper-tiny-lora/final --output models/whisper-phowhisper-tiny-lora
if ($LASTEXITCODE -ne 0) { throw 'Tiny LoRA export failed.' }
$tinySource = Join-Path $PSScriptRoot ".tmp/huggingface-training/models--vinai--PhoWhisper-tiny/snapshots/$tinyRevision"
if (-not (Test-Path -LiteralPath 'models/whisper-phowhisper-tiny/model.bin')) {
    & $tinyPython scripts/export_stt.py --checkpoint $tinySource --output models/whisper-phowhisper-tiny
    if ($LASTEXITCODE -ne 0) { throw 'Tiny baseline export failed.' }
}
& $tinyPython scripts/evaluate_stt.py --dataset Audio-dataset/vivos-small --models phowhisper-tiny phowhisper-tiny-lora phowhisper-base --samples 100 --chunk-seconds 8 --output training-runs/tiny-lora-int8-test.json
if ($LASTEXITCODE -ne 0) { throw 'INT8 evaluation failed.' }
& $tinyPython scripts/evaluate_stt.py --dataset Audio-dataset/vivos-small --models phowhisper-tiny phowhisper-tiny-lora phowhisper-base --samples 100 --chunk-seconds 8 --noise-snr 15 --output training-runs/tiny-lora-int8-noise-test.json
if ($LASTEXITCODE -ne 0) { throw 'Noisy INT8 evaluation failed.' }
Write-Host 'Training, export and evaluation finished. Review training-runs/tiny-lora-int8-test.json before selecting a model.'
