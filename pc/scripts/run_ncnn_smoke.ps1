param(
  [string]$RepoRoot = "G:\FPGA\ir_zynq_detector",
  [float]$Tolerance = 0.002
)

$ErrorActionPreference = "Stop"

$python = Join-Path $RepoRoot ".venv-train\Scripts\python.exe"
$gxx = "G:\minggw_bin\mingw64\bin\g++.exe"
$ncnnLib = Join-Path $RepoRoot "build\ncnn_mingw_20240820\src\libncnn.a"
$exe = Join-Path $RepoRoot "build\ncnn_smoke\irdet_ncnn_smoke.exe"

if (!(Test-Path $python)) {
  throw "Python environment not found: $python"
}
if (!(Test-Path $gxx)) {
  throw "MinGW g++ not found: $gxx"
}
if (!(Test-Path $ncnnLib)) {
  throw "ncnn static library not found: $ncnnLib"
}

New-Item -ItemType Directory -Force -Path (Join-Path $RepoRoot "build\ncnn_smoke") | Out-Null

Write-Host "Exporting ncnn smoke vectors..."
& $python (Join-Path $RepoRoot "pc\scripts\export_ncnn_smoke_vectors.py") `
  --onnx (Join-Path $RepoRoot "build\model\irdet_ssdlite_ir_runtime_fixed_v2_tracer_op13_ncnn.onnx") `
  --metadata (Join-Path $RepoRoot "build\model\irdet_ssdlite_ir_runtime_fixed_v2_tracer_op13_ncnn.json") `
  --checkpoint (Join-Path $RepoRoot "build\train_ssdlite_ir_fixed_v2\best.pt") `
  --manifest (Join-Path $RepoRoot "build\flir_thermal_3cls_fixed_v2_keepempty\dataset_manifest.json") `
  --split val `
  --index 0 `
  --provider cpu `
  --output-dir (Join-Path $RepoRoot "build\ncnn_smoke")
if ($LASTEXITCODE -ne 0) {
  throw "export_ncnn_smoke_vectors.py failed with exit code $LASTEXITCODE"
}

Write-Host "Compiling C++ ncnn smoke executable..."
& $gxx `
  -std=c++11 `
  -O2 `
  -D_WIN32_WINNT=0x0601 `
  -I (Join-Path $RepoRoot "tools\ncnn\src") `
  -I (Join-Path $RepoRoot "build\ncnn_mingw_20240820\src") `
  -I (Join-Path $RepoRoot "tools\ncnn\src\layer") `
  -I (Join-Path $RepoRoot "tools\ncnn\src\layer\x86") `
  (Join-Path $RepoRoot "pc\ncnn_smoke\irdet_ncnn_smoke.cpp") `
  $ncnnLib `
  -o $exe `
  -lws2_32 `
  -lwinmm `
  -static-libgcc `
  -static-libstdc++
if ($LASTEXITCODE -ne 0) {
  throw "C++ ncnn smoke compilation failed with exit code $LASTEXITCODE"
}

Write-Host "Running C++ ncnn smoke test..."
& $exe $RepoRoot $Tolerance
if ($LASTEXITCODE -ne 0) {
  throw "C++ ncnn smoke test failed with exit code $LASTEXITCODE"
}
