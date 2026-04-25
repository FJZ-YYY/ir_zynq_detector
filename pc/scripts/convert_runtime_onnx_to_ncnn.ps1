param(
  [string]$OnnxPath = "G:\FPGA\ir_zynq_detector\build\model\irdet_ssdlite_ir_runtime_legacy_tracer_op13_ncnn.onnx",
  [string]$OutputDir = "G:\FPGA\ir_zynq_detector\build\ncnn_runtime_legacy_tracer_op13_ncnn",
  [string]$Onnx2Ncnn = "G:\FPGA\ir_zynq_detector\tools\ncnn\ncnn-20240820-windows-vs2019\x64\bin\onnx2ncnn.exe",
  [string]$BaseName = "irdet_ssdlite_ir_runtime_legacy"
)

$ErrorActionPreference = "Stop"

if (!(Test-Path $OnnxPath)) {
  throw "ONNX file not found: $OnnxPath"
}

$tool = Get-Command $Onnx2Ncnn -ErrorAction SilentlyContinue
if ($null -eq $tool) {
  throw "onnx2ncnn tool not found. Install ncnn tools or pass -Onnx2Ncnn <full-path-to-onnx2ncnn.exe>."
}

New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

$paramPath = Join-Path $OutputDir "$BaseName.param"
$binPath = Join-Path $OutputDir "$BaseName.bin"

Write-Host "Converting ONNX to ncnn..."
Write-Host "ONNX:  $OnnxPath"
Write-Host "PARAM: $paramPath"
Write-Host "BIN:   $binPath"

& $tool.Source $OnnxPath $paramPath $binPath
if ($LASTEXITCODE -ne 0) {
  throw "onnx2ncnn failed with exit code $LASTEXITCODE"
}

Write-Host "ncnn conversion finished."
Get-Item $paramPath, $binPath | Select-Object FullName, Length, LastWriteTime
