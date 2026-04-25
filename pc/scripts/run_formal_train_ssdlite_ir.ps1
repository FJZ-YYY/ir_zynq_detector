[CmdletBinding()]
param(
    [string]$DatasetRoot = "G:\chormxiazai\FLIR_ADAS_v2",
    [string]$Manifest = "",
    [string]$OutputDir = "",
    [int]$Epochs = 40,
    [int]$BatchSize = 8,
    [int]$ValBatchSize = 8,
    [int]$NumWorkers = 4,
    [string]$Device = "auto",
    [double]$WidthMult = 1.0,
    [double]$LearningRate = 0.001,
    [int]$SaveEvery = 5,
    [int]$LogInterval = 50,
    [switch]$NoAmp
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent (Split-Path -Parent $ScriptDir)
$PythonExe = Join-Path $RepoRoot ".venv-train\Scripts\python.exe"
$ConfigPath = Join-Path $RepoRoot "configs\project_config.yaml"
$PrepareScript = Join-Path $RepoRoot "pc\scripts\prepare_flir_subset.py"
$TrainScript = Join-Path $RepoRoot "pc\scripts\train_ssdlite_ir.py"
$DefaultSubsetDir = Join-Path $RepoRoot "build\flir_thermal_3cls"

if ([string]::IsNullOrWhiteSpace($Manifest)) {
    $Manifest = Join-Path $DefaultSubsetDir "dataset_manifest.json"
}
if ([string]::IsNullOrWhiteSpace($OutputDir)) {
    $OutputDir = Join-Path $RepoRoot "build\train_ssdlite_ir_formal"
}

if (-not (Test-Path $PythonExe)) {
    throw "Training Python environment not found: $PythonExe"
}

if (-not (Test-Path $Manifest)) {
    if (-not (Test-Path $DatasetRoot)) {
        throw "Dataset root not found and manifest is missing: $DatasetRoot"
    }
    Write-Host "Preparing FLIR 3-class subset..."
    & $PythonExe $PrepareScript `
        --dataset-root $DatasetRoot `
        --config $ConfigPath `
        --output-dir $DefaultSubsetDir `
        --overwrite
}

$ResumePath = Join-Path $OutputDir "last.pt"
$Args = @(
    $TrainScript,
    "--manifest", $Manifest,
    "--output-dir", $OutputDir,
    "--epochs", "$Epochs",
    "--batch-size", "$BatchSize",
    "--val-batch-size", "$ValBatchSize",
    "--lr", "$LearningRate",
    "--num-workers", "$NumWorkers",
    "--device", $Device,
    "--width-mult", "$WidthMult",
    "--save-every", "$SaveEvery",
    "--log-interval", "$LogInterval",
    "--lr-scheduler", "cosine",
    "--pin-memory",
    "--persistent-workers"
)

if (-not $NoAmp.IsPresent) {
    $Args += "--amp"
}

if (Test-Path $ResumePath) {
    Write-Host "Resuming from $ResumePath"
    $Args += @("--resume", $ResumePath)
}

Write-Host "Starting formal training..."
Write-Host "$PythonExe $($Args -join ' ')"
& $PythonExe @Args
