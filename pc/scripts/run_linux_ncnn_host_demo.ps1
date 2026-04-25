param(
  [string]$RepoRoot = "G:\FPGA\ir_zynq_detector"
)

$ErrorActionPreference = "Stop"

$python = Join-Path $RepoRoot ".venv-train\Scripts\python.exe"
$cmake = Join-Path $RepoRoot ".venv-train\Scripts\cmake.exe"
$ninja = Join-Path $RepoRoot ".venv-train\Scripts\ninja.exe"
$gcc = "G:\minggw_bin\mingw64\bin\gcc.exe"
$gxx = "G:\minggw_bin\mingw64\bin\g++.exe"
$buildDir = Join-Path $RepoRoot "build\zynq_linux_host_ncnn"
$assetsDir = Join-Path $RepoRoot "build\linux_ncnn_demo"
$exe = Join-Path $buildDir "irdet_linux_ncnn_app.exe"
$ncnnLib = Join-Path $RepoRoot "build\ncnn_mingw_20240820\src\libncnn.a"
$ncnnIncludes = @(
  (Join-Path $RepoRoot "tools\ncnn\src"),
  (Join-Path $RepoRoot "build\ncnn_mingw_20240820\src")
) -join ';'

if (!(Test-Path $python)) { throw "Python not found: $python" }
if (!(Test-Path $cmake)) { throw "cmake not found: $cmake" }
if (!(Test-Path $ninja)) { throw "ninja not found: $ninja" }
if (!(Test-Path $gcc)) { throw "gcc not found: $gcc" }
if (!(Test-Path $gxx)) { throw "g++ not found: $gxx" }
if (!(Test-Path $ncnnLib)) { throw "ncnn library not found: $ncnnLib" }

$env:PATH = "$(Split-Path $ninja);$env:PATH"

if (Test-Path $buildDir) {
  Remove-Item -Recurse -Force $buildDir
}

Write-Host "Exporting Linux ncnn demo assets..."
& $python (Join-Path $RepoRoot "pc\scripts\export_linux_ncnn_demo_assets.py") `
  --onnx (Join-Path $RepoRoot "build\model\irdet_ssdlite_ir_runtime_fixed_v2_tracer_op13_ncnn.onnx") `
  --metadata (Join-Path $RepoRoot "build\model\irdet_ssdlite_ir_runtime_fixed_v2_tracer_op13_ncnn.json") `
  --checkpoint (Join-Path $RepoRoot "build\train_ssdlite_ir_fixed_v2\best.pt") `
  --manifest (Join-Path $RepoRoot "build\flir_thermal_3cls_fixed_v2_keepempty\dataset_manifest.json") `
  --split val `
  --index 0 `
  --provider cpu `
  --output-dir $assetsDir
if ($LASTEXITCODE -ne 0) {
  throw "export_linux_ncnn_demo_assets.py failed with exit code $LASTEXITCODE"
}

Write-Host "Configuring host demo build..."
$cmakeArgs = @(
  "-S", (Join-Path $RepoRoot "zynq_linux"),
  "-B", $buildDir,
  "-G", "Ninja",
  "-DCMAKE_C_COMPILER=$gcc",
  "-DCMAKE_CXX_COMPILER=$gxx",
  "-DIRDET_REPO_ROOT=$RepoRoot",
  "-DIRDET_NCNN_INCLUDE_DIRS=$ncnnIncludes",
  "-DIRDET_NCNN_LIBRARY=$ncnnLib"
)
& $cmake @cmakeArgs
if ($LASTEXITCODE -ne 0) {
  throw "CMake configure failed with exit code $LASTEXITCODE"
}

Write-Host "Building host demo..."
& $cmake --build $buildDir -j 4
if ($LASTEXITCODE -ne 0) {
  throw "CMake build failed with exit code $LASTEXITCODE"
}

$assets = Get-Content (Join-Path $assetsDir "linux_ncnn_demo_assets.json") | ConvertFrom-Json

Write-Host "Running Linux ncnn host demo..."
& $exe `
  --param $assets.model_param `
  --bin $assets.model_bin `
  --anchors $assets.anchors_file `
  --gray8 $assets.gray8_file `
  --src-width $assets.gray8_width `
  --src-height $assets.gray8_height `
  --runtime-width $assets.runtime_width `
  --runtime-height $assets.runtime_height `
  --score-thresh-x1000 200 `
  --iou-thresh-x1000 450 `
  --mean 0.5 `
  --std 0.5 `
  --input-scale 0.00392156862745
if ($LASTEXITCODE -ne 0) {
  throw "Linux ncnn host demo failed with exit code $LASTEXITCODE"
}
