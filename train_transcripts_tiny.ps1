param([string]$Output = 'training-runs/phowhisper-tiny-transcripts', [switch]$UseUnreviewedLabels)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$env:PYTHONIOENCODING = 'utf-8'
$env:OMP_NUM_THREADS = '2'
$env:HF_HUB_OFFLINE = '1'
$trainPython = Join-Path $PSScriptRoot '.venv-training/Scripts/python.exe'
if ($UseUnreviewedLabels) {
    Write-Host 'Using existing unreviewed labels as explicitly requested; label status remains unchanged.'
} else {
    & $trainPython scripts/apply_transcript_review.py
    if ($LASTEXITCODE -ne 0) { throw 'Review dataset labels or explicitly pass -UseUnreviewedLabels.' }
}
& $trainPython scripts/train_stt.py --dataset Audio-dataset/transcripts-tiny --model vinai/PhoWhisper-tiny --revision cc51d32be916efebde04ff549854fa1741cb5c02 --lora --lora-rank 8 --augment --epochs 3 --eval-steps 25 --batch-size 2 --gradient-accumulation 4 --learning-rate 2e-5 --early-stopping 2 --max-eval-samples 0 --output $Output
if ($LASTEXITCODE -ne 0) { throw 'Training failed.' }
Write-Host "Saved to $Output. Evaluate before exporting or selecting it in the web."
