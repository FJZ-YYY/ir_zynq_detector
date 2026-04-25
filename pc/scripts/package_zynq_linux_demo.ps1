param(
  [string]$RepoRoot = "G:\FPGA\ir_zynq_detector",
  [string]$RemoteDir = "/home/root/irdet_demo"
)

$ErrorActionPreference = "Stop"

$bundleDir = Join-Path $RepoRoot "build\zynq_linux_demo_bundle"
$assetsDir = Join-Path $RepoRoot "build\linux_ncnn_demo"
$appPath = Join-Path $RepoRoot "build\zynq_linux_arm_ncnn\irdet_linux_ncnn_app"
$plToolPath = Join-Path $RepoRoot "build\zynq_linux_arm_ncnn\irdet_linux_pl_dw3x3_tool"
$toolchainRoot = "F:\Xilinx\Vitis\2020.2\gnu\aarch32\nt\gcc-arm-linux-gnueabi\cortexa9t2hf-neon-xilinx-linux-gnueabi"
$toolchainLibDir = Join-Path $toolchainRoot "lib"
$toolchainUsrLibDir = Join-Path $toolchainRoot "usr\lib"
$paramPath = Join-Path $RepoRoot "build\ncnn_runtime_fixed_v2_tracer_op13_ncnn\irdet_ssdlite_ir_runtime_fixed_v2.param"
$binPath = Join-Path $RepoRoot "build\ncnn_runtime_fixed_v2_tracer_op13_ncnn\irdet_ssdlite_ir_runtime_fixed_v2.bin"
$anchorsPath = Join-Path $assetsDir "anchors_xyxy_f32.bin"
$gray8Path = Join-Path $assetsDir "sample_gray8_640x512.bin"
$tensorPath = Join-Path $assetsDir "sample_runtime_input_f32.bin"
$assetsJson = Join-Path $assetsDir "linux_ncnn_demo_assets.json"
$metadataJson = Join-Path $RepoRoot "build\model\irdet_ssdlite_ir_runtime_fixed_v2_tracer_op13_ncnn.json"
$layerCaseDir = Join-Path $RepoRoot "build\pl_layer_case_depthwise_fixed_v2"
$fullChannelDir = Join-Path $RepoRoot "build\pl_depthwise_full_channel_fixed_v2"
$buildArmNcnn = Join-Path $RepoRoot "pc\scripts\build_ncnn_arm_linux_min.ps1"
$buildArmApp = Join-Path $RepoRoot "pc\scripts\build_zynq_linux_arm_ncnn.ps1"
$exportAssets = Join-Path $RepoRoot "pc\scripts\export_linux_ncnn_demo_assets.py"
$exportLayerCase = Join-Path $RepoRoot "pc\scripts\export_depthwise_layer_case.py"
$exportFullChannel = Join-Path $RepoRoot "pc\scripts\export_depthwise_full_channel.py"
$checkContract = Join-Path $RepoRoot "pc\scripts\check_deploy_contract.py"
$patchElf = Join-Path $RepoRoot "pc\scripts\patch_linux_elf_interpreter.py"
$python = Join-Path $RepoRoot ".venv-train\Scripts\python.exe"
$hostPython = "python"

function Write-LfAsciiFile {
  param(
    [Parameter(Mandatory = $true)][string]$Path,
    [Parameter(Mandatory = $true)][string]$Content
  )

  $normalized = $Content.Replace("`r`n", "`n").Replace("`r", "`n")
  $encoding = New-Object System.Text.ASCIIEncoding
  [System.IO.File]::WriteAllText($Path, $normalized, $encoding)
}

if (!(Test-Path $python)) { throw "Python not found: $python" }
if (!(Test-Path $buildArmNcnn)) { throw "Script not found: $buildArmNcnn" }
if (!(Test-Path $buildArmApp)) { throw "Script not found: $buildArmApp" }
if (!(Test-Path $exportAssets)) { throw "Script not found: $exportAssets" }
if (!(Test-Path $exportLayerCase)) { throw "Script not found: $exportLayerCase" }
if (!(Test-Path $exportFullChannel)) { throw "Script not found: $exportFullChannel" }
if (!(Test-Path $checkContract)) { throw "Script not found: $checkContract" }
if (!(Test-Path $patchElf)) { throw "Script not found: $patchElf" }

Write-Host "Refreshing Linux demo assets..."
& $python $exportAssets `
  --onnx (Join-Path $RepoRoot "build\model\irdet_ssdlite_ir_runtime_fixed_v2_tracer_op13_ncnn.onnx") `
  --metadata $metadataJson `
  --checkpoint (Join-Path $RepoRoot "build\train_ssdlite_ir_fixed_v2\best.pt") `
  --manifest (Join-Path $RepoRoot "build\flir_thermal_3cls_fixed_v2_keepempty\dataset_manifest.json") `
  --split val `
  --index 0 `
  --provider cpu `
  --output-dir $assetsDir
if ($LASTEXITCODE -ne 0) {
  throw "export_linux_ncnn_demo_assets.py failed with exit code $LASTEXITCODE"
}

Write-Host "Exporting fixed_v2 real depthwise layer case..."
& $python $exportLayerCase `
  --checkpoint (Join-Path $RepoRoot "build\train_ssdlite_ir_fixed_v2\best.pt") `
  --manifest (Join-Path $RepoRoot "build\flir_thermal_3cls_fixed_v2_keepempty\dataset_manifest.json") `
  --split val `
  --index 0 `
  --output-dir $layerCaseDir `
  --device cpu
if ($LASTEXITCODE -ne 0) {
  throw "export_depthwise_layer_case.py failed with exit code $LASTEXITCODE"
}

Write-Host "Exporting fixed_v2 real depthwise full-channel case..."
& $python $exportFullChannel `
  --input-dir $layerCaseDir `
  --output-dir $fullChannelDir `
  --c-header-out (Join-Path $fullChannelDir "ir_pl_dw3x3_full_channel_data.h") `
  --channel 11 `
  --frac-bits 8
if ($LASTEXITCODE -ne 0) {
  throw "export_depthwise_full_channel.py failed with exit code $LASTEXITCODE"
}

Write-Host "Rebuilding ARM Linux ncnn..."
& powershell -ExecutionPolicy Bypass -File $buildArmNcnn -RepoRoot $RepoRoot
if ($LASTEXITCODE -ne 0) {
  throw "build_ncnn_arm_linux_min.ps1 failed with exit code $LASTEXITCODE"
}

Write-Host "Rebuilding ARM Linux detector app..."
& powershell -ExecutionPolicy Bypass -File $buildArmApp -RepoRoot $RepoRoot
if ($LASTEXITCODE -ne 0) {
  throw "build_zynq_linux_arm_ncnn.ps1 failed with exit code $LASTEXITCODE"
}

Write-Host "Checking deployment contract compatibility..."
& $python $checkContract `
  --contract (Join-Path $RepoRoot "configs\deploy_contract_ssdlite_ir_v1.json") `
  --runtime-metadata $metadataJson
if ($LASTEXITCODE -ne 0) {
  throw "check_deploy_contract.py failed with exit code $LASTEXITCODE"
}

if (Test-Path $bundleDir) {
  Remove-Item -Recurse -Force $bundleDir
}
New-Item -ItemType Directory -Force -Path $bundleDir | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $bundleDir "app") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $bundleDir "model") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $bundleDir "data") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $bundleDir "lib") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $bundleDir "data\pl_real_layer_case") | Out-Null

Copy-Item $appPath (Join-Path $bundleDir "app\irdet_linux_ncnn_app")
Copy-Item $plToolPath (Join-Path $bundleDir "app\irdet_linux_pl_dw3x3_tool")
Copy-Item $paramPath (Join-Path $bundleDir "model\irdet_ssdlite_ir_runtime_fixed_v2.param")
Copy-Item $binPath (Join-Path $bundleDir "model\irdet_ssdlite_ir_runtime_fixed_v2.bin")
Copy-Item $anchorsPath (Join-Path $bundleDir "model\anchors_xyxy_f32.bin")
Copy-Item $gray8Path (Join-Path $bundleDir "data\sample_gray8_640x512.bin")
Copy-Item $tensorPath (Join-Path $bundleDir "data\sample_runtime_input_f32.bin")
Copy-Item $assetsJson (Join-Path $bundleDir "data\linux_ncnn_demo_assets.json")
Copy-Item $metadataJson (Join-Path $bundleDir "model\irdet_ssdlite_ir_runtime_fixed_v2_tracer_op13_ncnn.json")
Copy-Item (Join-Path $layerCaseDir "layer_input.bin") (Join-Path $bundleDir "data\pl_real_layer_case\layer_input.bin")
Copy-Item (Join-Path $layerCaseDir "weight_fused.bin") (Join-Path $bundleDir "data\pl_real_layer_case\weight_fused.bin")
Copy-Item (Join-Path $layerCaseDir "bias_fused.bin") (Join-Path $bundleDir "data\pl_real_layer_case\bias_fused.bin")
Copy-Item (Join-Path $layerCaseDir "golden_bn_out.bin") (Join-Path $bundleDir "data\pl_real_layer_case\golden_bn_out.bin")
Copy-Item (Join-Path $layerCaseDir "layer_summary.txt") (Join-Path $bundleDir "data\pl_real_layer_case\layer_summary.txt")
Copy-Item (Join-Path $layerCaseDir "layer_manifest.json") (Join-Path $bundleDir "data\pl_real_layer_case\layer_manifest.json")
Copy-Item (Join-Path $fullChannelDir "depthwise_full_channel.txt") (Join-Path $bundleDir "data\pl_real_layer_case\depthwise_full_channel.txt")

$runtimeLibs = @(
  @{ Source = (Join-Path $toolchainLibDir "ld-linux-armhf.so.3"); Target = "lib\ld-linux-armhf.so.3" },
  @{ Source = (Join-Path $toolchainLibDir "libc.so.6"); Target = "lib\libc.so.6" },
  @{ Source = (Join-Path $toolchainLibDir "libdl.so.2"); Target = "lib\libdl.so.2" },
  @{ Source = (Join-Path $toolchainLibDir "libgcc_s.so.1"); Target = "lib\libgcc_s.so.1" },
  @{ Source = (Join-Path $toolchainLibDir "libm.so.6"); Target = "lib\libm.so.6" },
  @{ Source = (Join-Path $toolchainLibDir "libpthread.so.0"); Target = "lib\libpthread.so.0" },
  @{ Source = (Join-Path $toolchainLibDir "librt.so.1"); Target = "lib\librt.so.1" },
  @{ Source = (Join-Path $toolchainLibDir "libutil.so.1"); Target = "lib\libutil.so.1" },
  @{ Source = (Join-Path $toolchainUsrLibDir "libatomic.so.1"); Target = "lib\libatomic.so.1" },
  @{ Source = (Join-Path $toolchainUsrLibDir "libstdc++.so.6"); Target = "lib\libstdc++.so.6" }
)

foreach ($runtimeLib in $runtimeLibs) {
  if (!(Test-Path $runtimeLib.Source)) {
    throw "Runtime library not found: $($runtimeLib.Source)"
  }
  Copy-Item $runtimeLib.Source (Join-Path $bundleDir $runtimeLib.Target)
}

Write-Host "Patching ARM ELF interpreter/RUNPATH for remote bundle root $RemoteDir ..."
foreach ($elfPath in @(
  (Join-Path $bundleDir "app\irdet_linux_ncnn_app"),
  (Join-Path $bundleDir "app\irdet_linux_pl_dw3x3_tool")
)) {
  & $hostPython $patchElf --input $elfPath --runtime-root $RemoteDir --in-place
  if ($LASTEXITCODE -ne 0) {
    throw "patch_linux_elf_interpreter.py failed for $elfPath with exit code $LASTEXITCODE"
  }
}

$runGray8 = @'
#!/bin/sh
set -eu
DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
cd "$DIR"
chmod +x app/irdet_linux_ncnn_app app/irdet_linux_pl_dw3x3_tool lib/ld-linux-armhf.so.3 || true
./app/irdet_linux_ncnn_app \
  --param ./model/irdet_ssdlite_ir_runtime_fixed_v2.param \
  --bin ./model/irdet_ssdlite_ir_runtime_fixed_v2.bin \
  --anchors ./model/anchors_xyxy_f32.bin \
  --gray8 ./data/sample_gray8_640x512.bin \
  --src-width 640 \
  --src-height 512 \
  --runtime-width 160 \
  --runtime-height 128 \
  --score-thresh-x1000 200 \
  --iou-thresh-x1000 450 \
  --mean 0.5 \
  --std 0.5 \
  --input-scale 0.00392156862745
'@
Write-LfAsciiFile -Path (Join-Path $bundleDir "run_demo_gray8.sh") -Content $runGray8

$runGray8WithPlProbe = @'
#!/bin/sh
set -eu
DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
cd "$DIR"
chmod +x app/irdet_linux_ncnn_app app/irdet_linux_pl_dw3x3_tool lib/ld-linux-armhf.so.3 || true
./app/irdet_linux_ncnn_app \
  --param ./model/irdet_ssdlite_ir_runtime_fixed_v2.param \
  --bin ./model/irdet_ssdlite_ir_runtime_fixed_v2.bin \
  --anchors ./model/anchors_xyxy_f32.bin \
  --gray8 ./data/sample_gray8_640x512.bin \
  --src-width 640 \
  --src-height 512 \
  --runtime-width 160 \
  --runtime-height 128 \
  --score-thresh-x1000 200 \
  --iou-thresh-x1000 450 \
  --mean 0.5 \
  --std 0.5 \
  --input-scale 0.00392156862745 \
  --pl-probe-full
'@
Write-LfAsciiFile -Path (Join-Path $bundleDir "run_demo_gray8_with_pl_probe.sh") -Content $runGray8WithPlProbe

$runGray8WithPlRealLayer = @'
#!/bin/sh
set -eu
DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
cd "$DIR"
chmod +x app/irdet_linux_ncnn_app app/irdet_linux_pl_dw3x3_tool lib/ld-linux-armhf.so.3 || true
./app/irdet_linux_ncnn_app \
  --param ./model/irdet_ssdlite_ir_runtime_fixed_v2.param \
  --bin ./model/irdet_ssdlite_ir_runtime_fixed_v2.bin \
  --anchors ./model/anchors_xyxy_f32.bin \
  --gray8 ./data/sample_gray8_640x512.bin \
  --src-width 640 \
  --src-height 512 \
  --runtime-width 160 \
  --runtime-height 128 \
  --score-thresh-x1000 200 \
  --iou-thresh-x1000 450 \
  --mean 0.5 \
  --std 0.5 \
  --input-scale 0.00392156862745 \
  --pl-real-layer-dir ./data/pl_real_layer_case
'@
Write-LfAsciiFile -Path (Join-Path $bundleDir "run_demo_gray8_with_pl_real_layer.sh") -Content $runGray8WithPlRealLayer

$runDumpRuntimeDwInput = @'
#!/bin/sh
set -eu
DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
cd "$DIR"
chmod +x app/irdet_linux_ncnn_app app/irdet_linux_pl_dw3x3_tool lib/ld-linux-armhf.so.3 || true
./app/irdet_linux_ncnn_app \
  --param ./model/irdet_ssdlite_ir_runtime_fixed_v2.param \
  --bin ./model/irdet_ssdlite_ir_runtime_fixed_v2.bin \
  --anchors ./model/anchors_xyxy_f32.bin \
  --gray8 ./data/sample_gray8_640x512.bin \
  --src-width 640 \
  --src-height 512 \
  --runtime-width 160 \
  --runtime-height 128 \
  --score-thresh-x1000 200 \
  --iou-thresh-x1000 450 \
  --mean 0.5 \
  --std 0.5 \
  --input-scale 0.00392156862745 \
  --dump-blob /inner/backbone/features.0/features.0.3/conv/conv.0/conv.0.2/Clip_output_0 \
  --dump-blob-out ./data/runtime_dw_input \
  --blob-only
'@
Write-LfAsciiFile -Path (Join-Path $bundleDir "run_dump_runtime_dw_input.sh") -Content $runDumpRuntimeDwInput

$runTensor = @'
#!/bin/sh
set -eu
DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
cd "$DIR"
chmod +x app/irdet_linux_ncnn_app app/irdet_linux_pl_dw3x3_tool lib/ld-linux-armhf.so.3 || true
./app/irdet_linux_ncnn_app \
  --param ./model/irdet_ssdlite_ir_runtime_fixed_v2.param \
  --bin ./model/irdet_ssdlite_ir_runtime_fixed_v2.bin \
  --anchors ./model/anchors_xyxy_f32.bin \
  --tensor-f32 ./data/sample_runtime_input_f32.bin \
  --src-width 640 \
  --src-height 512 \
  --runtime-width 160 \
  --runtime-height 128 \
  --score-thresh-x1000 200 \
  --iou-thresh-x1000 450 \
  --mean 0.5 \
  --std 0.5 \
  --input-scale 0.00392156862745
'@
Write-LfAsciiFile -Path (Join-Path $bundleDir "run_demo_tensor.sh") -Content $runTensor

$runPlSelftest = @'
#!/bin/sh
set -eu
DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
cd "$DIR"
chmod +x app/irdet_linux_pl_dw3x3_tool lib/ld-linux-armhf.so.3 || true
./app/irdet_linux_pl_dw3x3_tool --all --skip-gpio
'@
Write-LfAsciiFile -Path (Join-Path $bundleDir "run_pl_selftest.sh") -Content $runPlSelftest

$readme = @'
IR Zynq Linux ncnn demo bundle

Contents:
- app/irdet_linux_ncnn_app
- app/irdet_linux_pl_dw3x3_tool
- lib/ld-linux-armhf.so.3
- lib/libc.so.6
- lib/libstdc++.so.6
- model/irdet_ssdlite_ir_runtime_fixed_v2.param
- model/irdet_ssdlite_ir_runtime_fixed_v2.bin
- model/anchors_xyxy_f32.bin
- data/sample_gray8_640x512.bin
- data/sample_runtime_input_f32.bin
- data/pl_real_layer_case/*
- run_demo_gray8.sh
- run_demo_gray8_with_pl_probe.sh
- run_demo_gray8_with_pl_real_layer.sh
- run_demo_tensor.sh
- run_pl_selftest.sh

Recommended first board-side run:
1. Boot the board into Linux shell.
2. Copy this whole directory onto the board, for example to /home/root/irdet_demo.
3. Run:
   chmod +x app/irdet_linux_ncnn_app app/irdet_linux_pl_dw3x3_tool lib/ld-linux-armhf.so.3 run_demo_gray8.sh run_demo_gray8_with_pl_probe.sh run_demo_gray8_with_pl_real_layer.sh run_demo_tensor.sh run_pl_selftest.sh
   ./run_demo_gray8.sh

Expected output pattern:
- Model backend=ncnn runtime_in=160x128 ...
- det_count=2
- det0 class=car score=0.718 bbox=[140,220,193,254]

Notes:
- run_demo_gray8.sh exercises preprocess + ncnn + postprocess
- run_demo_gray8_with_pl_probe.sh runs the same detector path, but first executes the embedded
  Linux-side PL full-scheduler replay inside the detector app
- run_demo_gray8_with_pl_real_layer.sh runs the detector and also validates one exported
  fixed_v2 MobileNetV2 depthwise 3x3 real layer case through the PL full scheduler
- run_demo_tensor.sh bypasses preprocess and is useful for debugging runtime parity
- run_pl_selftest.sh replays the validated PL dw3x3 MMIO/full-scheduler checks from Linux user space
- the Linux selftest intentionally skips the optional AXI GPIO probe, because touching an
  un-decoded GPIO slave through /dev/mem would terminate the process with Bus error
- the ARM executables are patched to use the bundled loader and runtime in this directory,
  so board-side scripts can launch them directly without manually invoking ld-linux
'@
Set-Content -Path (Join-Path $bundleDir "README.txt") -Value $readme -Encoding ascii

$manifest = [ordered]@{
  bundle = "zynq_linux_demo_bundle_fixed_v2"
  runtime_root = $RemoteDir
  app = "app/irdet_linux_ncnn_app"
  pl_tool = "app/irdet_linux_pl_dw3x3_tool"
  loader = "lib/ld-linux-armhf.so.3"
  model_param = "model/irdet_ssdlite_ir_runtime_fixed_v2.param"
  model_bin = "model/irdet_ssdlite_ir_runtime_fixed_v2.bin"
  anchors = "model/anchors_xyxy_f32.bin"
  gray8_sample = "data/sample_gray8_640x512.bin"
  tensor_sample = "data/sample_runtime_input_f32.bin"
  pl_real_layer_case = "data/pl_real_layer_case"
  run_gray8 = "run_demo_gray8.sh"
  run_gray8_with_pl_probe = "run_demo_gray8_with_pl_probe.sh"
  run_gray8_with_pl_real_layer = "run_demo_gray8_with_pl_real_layer.sh"
  run_tensor = "run_demo_tensor.sh"
  run_pl_selftest = "run_pl_selftest.sh"
}
$manifest | ConvertTo-Json -Depth 4 | Set-Content -Path (Join-Path $bundleDir "bundle_manifest.json") -Encoding ascii

Get-ChildItem -Recurse $bundleDir | Select-Object FullName,Length,LastWriteTime
