[CmdletBinding()]
param(
    [string]$DatasetRoot = "G:\chormxiazai\FLIR_ADAS_v2",
    [string]$Manifest = "",
    [string]$Checkpoint = "",
    [string]$OutputDir = "",
    [ValidateSet("train", "val")]
    [string]$Split = "val",
    [int]$BatchSize = 8,
    [int]$NumWorkers = 0,
    [int]$MaxImages = 0,
    [int]$VisCount = 12,
    [double]$ScoreThresh = 0.05,
    [double]$VisScoreThresh = 0.35,
    [string]$Device = "auto",
    [switch]$Amp,
    [switch]$PinMemory
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent (Split-Path -Parent $ScriptDir)
$PythonExe = Join-Path $RepoRoot ".venv-train\Scripts\python.exe"
$ConfigPath = Join-Path $RepoRoot "configs\project_config.yaml"
$PrepareScript = Join-Path $RepoRoot "pc\scripts\prepare_flir_subset.py"
$EvalScript = Join-Path $RepoRoot "pc\scripts\eval_ssdlite_ir.py"
$DefaultSubsetDir = Join-Path $RepoRoot "build\flir_thermal_3cls"

if ([string]::IsNullOrWhiteSpace($Manifest)) {
    $Manifest = Join-Path $DefaultSubsetDir "dataset_manifest.json"
}
if ([string]::IsNullOrWhiteSpace($Checkpoint)) {
    $Checkpoint = Join-Path $RepoRoot "build\train_ssdlite_ir_formal\best.pt"
}
if ([string]::IsNullOrWhiteSpace($OutputDir)) {
    if ($MaxImages -gt 0) {
        $OutputDir = Join-Path $RepoRoot "build\eval_ssdlite_ir_smoke"
    } else {
        $OutputDir = Join-Path $RepoRoot "build\eval_ssdlite_ir_formal"
    }
}

if (-not (Test-Path $PythonExe)) {
    throw "Training Python environment not found: $PythonExe"
}
if (-not (Test-Path $Checkpoint)) {
    throw "Checkpoint not found: $Checkpoint"
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

$Args = @(
    $EvalScript,
    "--checkpoint", $Checkpoint,
    "--manifest", $Manifest,
    "--split", $Split,
    "--output-dir", $OutputDir,
    "--batch-size", "$BatchSize",
    "--num-workers", "$NumWorkers",
    "--score-thresh", "$ScoreThresh",
    "--vis-score-thresh", "$VisScoreThresh",
    "--vis-count", "$VisCount",
    "--device", $Device
)

if ($MaxImages -gt 0) {
    $Args += @("--max-images", "$MaxImages")
}
if ($Amp.IsPresent) {
    $Args += "--amp"
}
if ($PinMemory.IsPresent) {
    $Args += "--pin-memory"
}

Write-Host "Starting SSDLite evaluation..."
Write-Host "$PythonExe $($Args -join ' ')"
& $PythonExe @Args
