[CmdletBinding()]
param(
    [ValidateSet("cu126", "cu128")]
    [string]$CudaWheel = "cu128"
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent (Split-Path -Parent $ScriptDir)
$PythonExe = Join-Path $RepoRoot ".venv-train\Scripts\python.exe"
$IndexUrl = "https://download.pytorch.org/whl/$CudaWheel"

if (-not (Test-Path $PythonExe)) {
    throw "Training Python environment not found: $PythonExe"
}

Write-Host "Installing CUDA-enabled torch/torchvision from $IndexUrl"
& $PythonExe -m pip install --upgrade --index-url $IndexUrl torch torchvision

Write-Host "Verifying torch CUDA availability..."
& $PythonExe -c "import torch; print('torch', torch.__version__); print('cuda_available', torch.cuda.is_available()); print('device_count', torch.cuda.device_count()); print('device_name', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'N/A')"
