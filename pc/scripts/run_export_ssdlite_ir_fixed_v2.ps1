[CmdletBinding()]
param(
    [string]$Checkpoint = "",
    [string]$Manifest = "",
    [string]$RepoRoot = "",
    [int]$VerifyImages = 2
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
if ([string]::IsNullOrWhiteSpace($RepoRoot)) {
    $RepoRoot = Split-Path -Parent (Split-Path -Parent $ScriptDir)
}

$PythonExe = Join-Path $RepoRoot ".venv-train\Scripts\python.exe"
$ExportRawScript = Join-Path $RepoRoot "pc\scripts\export_ssdlite_ir_onnx.py"
$ExportRuntimeScript = Join-Path $RepoRoot "pc\scripts\export_ssdlite_ir_runtime_onnx.py"
$CheckContractScript = Join-Path $RepoRoot "pc\scripts\check_deploy_contract.py"
$ConvertNcnnScript = Join-Path $RepoRoot "pc\scripts\convert_runtime_onnx_to_ncnn.ps1"

if ([string]::IsNullOrWhiteSpace($Checkpoint)) {
    $Checkpoint = Join-Path $RepoRoot "build\train_ssdlite_ir_fixed_v2\best.pt"
}
if ([string]::IsNullOrWhiteSpace($Manifest)) {
    $Manifest = Join-Path $RepoRoot "build\flir_thermal_3cls_fixed_v2_keepempty\dataset_manifest.json"
}

$RawOnnx = Join-Path $RepoRoot "build\model\irdet_ssdlite_ir_fixed_v2.onnx"
$RawMeta = Join-Path $RepoRoot "build\model\irdet_ssdlite_ir_fixed_v2.json"
$RuntimeOnnx = Join-Path $RepoRoot "build\model\irdet_ssdlite_ir_runtime_fixed_v2.onnx"
$RuntimeMeta = Join-Path $RepoRoot "build\model\irdet_ssdlite_ir_runtime_fixed_v2.json"
$RuntimeNcnnOnnx = Join-Path $RepoRoot "build\model\irdet_ssdlite_ir_runtime_fixed_v2_tracer_op13_ncnn.onnx"
$RuntimeNcnnMeta = Join-Path $RepoRoot "build\model\irdet_ssdlite_ir_runtime_fixed_v2_tracer_op13_ncnn.json"
$NcnnOutputDir = Join-Path $RepoRoot "build\ncnn_runtime_fixed_v2_tracer_op13_ncnn"

foreach ($required in @($PythonExe, $ExportRawScript, $ExportRuntimeScript, $CheckContractScript, $ConvertNcnnScript, $Checkpoint, $Manifest)) {
    if (-not (Test-Path $required)) {
        throw "Required path not found: $required"
    }
}

Write-Host "Exporting raw-head ONNX..."
& $PythonExe $ExportRawScript `
    --checkpoint $Checkpoint `
    --output $RawOnnx `
    --metadata-output $RawMeta
if ($LASTEXITCODE -ne 0) {
    throw "export_ssdlite_ir_onnx.py failed with exit code $LASTEXITCODE"
}

Write-Host "Exporting strict fixed-contract runtime ONNX..."
& $PythonExe $ExportRuntimeScript `
    --checkpoint $Checkpoint `
    --output $RuntimeOnnx `
    --metadata-output $RuntimeMeta `
    --manifest $Manifest `
    --split val `
    --verify-images $VerifyImages
if ($LASTEXITCODE -ne 0) {
    throw "export_ssdlite_ir_runtime_onnx.py failed with exit code $LASTEXITCODE"
}

Write-Host "Checking strict deployment contract..."
& $PythonExe $CheckContractScript `
    --contract (Join-Path $RepoRoot "configs\deploy_contract_ssdlite_ir_v1.json") `
    --runtime-metadata $RuntimeMeta
if ($LASTEXITCODE -ne 0) {
    throw "check_deploy_contract.py failed with exit code $LASTEXITCODE"
}

Write-Host "Exporting ncnn-friendly runtime ONNX..."
& $PythonExe $ExportRuntimeScript `
    --checkpoint $Checkpoint `
    --output $RuntimeNcnnOnnx `
    --metadata-output $RuntimeNcnnMeta `
    --manifest $Manifest `
    --split val `
    --verify-images $VerifyImages `
    --exclude-anchor-output `
    --legacy-exporter `
    --single-file `
    --opset 13
if ($LASTEXITCODE -ne 0) {
    throw "export_ssdlite_ir_runtime_onnx.py (ncnn path) failed with exit code $LASTEXITCODE"
}

Write-Host "Checking strict deployment contract for ncnn-friendly export..."
& $PythonExe $CheckContractScript `
    --contract (Join-Path $RepoRoot "configs\deploy_contract_ssdlite_ir_v1.json") `
    --runtime-metadata $RuntimeNcnnMeta
if ($LASTEXITCODE -ne 0) {
    throw "check_deploy_contract.py failed for ncnn-friendly export with exit code $LASTEXITCODE"
}

Write-Host "Converting fixed-contract runtime ONNX to ncnn..."
& powershell -ExecutionPolicy Bypass -File $ConvertNcnnScript `
    -OnnxPath $RuntimeNcnnOnnx `
    -OutputDir $NcnnOutputDir `
    -BaseName "irdet_ssdlite_ir_runtime_fixed_v2"
if ($LASTEXITCODE -ne 0) {
    throw "convert_runtime_onnx_to_ncnn.ps1 failed with exit code $LASTEXITCODE"
}

Write-Host "Fixed-contract export finished."
Write-Host "Artifacts:"
Write-Host "  $RawOnnx"
Write-Host "  $RawMeta"
Write-Host "  $RuntimeOnnx"
Write-Host "  $RuntimeMeta"
Write-Host "  $RuntimeNcnnOnnx"
Write-Host "  $RuntimeNcnnMeta"
Write-Host "  $NcnnOutputDir"
