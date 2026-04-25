# True Inference Runtime Plan

## Current Status

The board has verified these pieces in one UART demo path:

- PC sends decoded FLIR thermal `gray8` image data
- PS receives the frame and validates checksum
- PS resizes and normalizes to the model tensor size
- PL MobileNetV2 depthwise `3x3` accelerator probe returns success
- PS SSD raw-head postprocess decodes a real exported model sample

This proves the deployment interface, but it is not yet full board-side neural
network inference. The remaining missing block is the runtime that computes
`bbox_regression` and `cls_logits` from the preprocessed tensor.

## Selected Route

Use two coordinated runtime tracks:

- bare-metal track: keep UART, preprocessing, PL operator acceleration, and SSD
  postprocess demos stable
- Linux track: add full SSDLite-MobileNetV2 inference with a lightweight C/C++
  runtime

This is more realistic than hand-writing the whole SSDLite network in bare-metal
C or pure HDL.

## Why Not Full Bare-Metal First

Full SSDLite-MobileNetV2 requires many layers:

- regular convolution
- depthwise convolution
- pointwise convolution
- batchnorm/fused scale
- ReLU6
- SSD heads
- tensor memory scheduling
- quantization or float kernels

Writing all of that directly for bare metal is possible, but it is a large
project by itself. It would slow down the main goal: proving an end-to-end
deployable detector on Zynq-7020.

## Recommended Linux Runtime

First choice: `ncnn`.

Reasons:

- C/C++ only
- supports ARMv7 Linux
- practical for small embedded CPU inference
- has ONNX conversion tooling
- easier to cross-compile than a large desktop runtime
- custom SSD postprocess can reuse the existing PS C implementation

Fallback choices:

- TensorFlow Lite if model conversion to TFLite becomes cleaner than ncnn
- ONNX Runtime only if ARMv7 build friction is acceptable

## Windows Host Impact

Linux here means Linux running on the Zynq board, not replacing the PC operating
system.

The PC can remain Windows. The installed Vitis 2020.2 toolchain already contains
an ARM Linux cross compiler:

```text
F:\Xilinx\Vitis\2020.2\gnu\aarch32\nt\gcc-arm-linux-gnueabi\bin\arm-linux-gnueabihf-g++.exe
```

If a complete board Linux image must be built from scratch, PetaLinux normally
requires a Linux host or VM/WSL. To avoid that as long as possible, first try to
use an existing/prebuilt Zynq Linux image for the board, then cross-compile only
the detector application from Windows.

## Runtime-Friendly Legacy Export

The current checkpoint has a verified transform-free raw-head export:

```text
G:\FPGA\ir_zynq_detector\build\model\irdet_ssdlite_ir_runtime_legacy.onnx
G:\FPGA\ir_zynq_detector\build\model\irdet_ssdlite_ir_runtime_legacy.json
```

Export command:

```powershell
G:\FPGA\ir_zynq_detector\.venv-train\Scripts\python.exe `
  G:\FPGA\ir_zynq_detector\pc\scripts\export_ssdlite_ir_runtime_onnx.py `
  --checkpoint G:\FPGA\ir_zynq_detector\build\train_ssdlite_ir_formal\best.pt `
  --output G:\FPGA\ir_zynq_detector\build\model\irdet_ssdlite_ir_runtime_legacy.onnx `
  --metadata-output G:\FPGA\ir_zynq_detector\build\model\irdet_ssdlite_ir_runtime_legacy.json `
  --manifest G:\FPGA\ir_zynq_detector\build\flir_thermal_3cls\dataset_manifest.json `
  --split val `
  --verify-images 2
```

Verified result:

```text
Runtime input tensor: 1x1x160x128
Checkpoint training hint: 1x1x128x160 (pre-transform)
Outputs: bbox_regression=(1, 660, 4) cls_logits=(1, 660, 4) anchors_xyxy=(660, 4)
Verification records=3 tolerance=1.0e-05 PASS
```

This export is useful for the current checkpoint because it removes torchvision's
SSD transform from the ONNX graph while preserving the exact transformed tensor
space used by the trained model.

It is not the final fixed input contract. The contract checker intentionally
reports this difference:

```powershell
G:\FPGA\ir_zynq_detector\.venv-train\Scripts\python.exe `
  G:\FPGA\ir_zynq_detector\pc\scripts\check_deploy_contract.py `
  --contract G:\FPGA\ir_zynq_detector\configs\deploy_contract_ssdlite_ir_v1.json `
  --runtime-metadata G:\FPGA\ir_zynq_detector\build\model\irdet_ssdlite_ir_runtime_legacy.json `
  --allow-legacy-current
```

Expected result:

```text
CONTRACT_LEGACY_OK: runtime metadata is compatible with the current checkpoint
CONTRACT_WARNING: runtime input shape differs from the live PS preprocess shape; do not use this as the next retraining contract
CONTRACT_WARNING: metadata explicitly marks this export as not future-fixed
```

## PC ONNX Runtime Smoke Test

The legacy runtime ONNX has also been executed with ONNX Runtime on the Windows
PC. This verifies that a non-PyTorch runtime can load the exported model, produce
raw-head tensors, and feed the existing SSD postprocess logic.

Dependency:

```powershell
G:\FPGA\ir_zynq_detector\.venv-train\Scripts\python.exe -m pip install onnxruntime
```

Smoke command:

```powershell
G:\FPGA\ir_zynq_detector\.venv-train\Scripts\python.exe `
  G:\FPGA\ir_zynq_detector\pc\scripts\smoke_runtime_onnx.py `
  --onnx G:\FPGA\ir_zynq_detector\build\model\irdet_ssdlite_ir_runtime_legacy.onnx `
  --metadata G:\FPGA\ir_zynq_detector\build\model\irdet_ssdlite_ir_runtime_legacy.json `
  --checkpoint G:\FPGA\ir_zynq_detector\build\train_ssdlite_ir_formal\best.pt `
  --manifest G:\FPGA\ir_zynq_detector\build\flir_thermal_3cls\dataset_manifest.json `
  --split val `
  --index 0 `
  --provider cpu `
  --output-dir G:\FPGA\ir_zynq_detector\build\runtime_onnx_smoke
```

Verified result:

```text
ONNX Runtime providers=['CPUExecutionProvider']
Input input_0 shape=(1, 1, 160, 128)
Output bbox_regression shape=(1, 660, 4)
Output cls_logits shape=(1, 660, 4)
Output anchors_xyxy shape=(660, 4)
Compare bbox_regression max_abs_diff=6.4373016e-06
Compare cls_logits max_abs_diff=9.5367432e-06
Compare anchors_xyxy max_abs_diff=0
Detections count=2 elapsed_ms=5.000
det0 class=car score=0.718 bbox=[140, 220, 193, 254]
det1 class=car score=0.551 bbox=[235, 195, 337, 297]
```

Report:

```text
G:\FPGA\ir_zynq_detector\build\runtime_onnx_smoke\runtime_onnx_smoke.json
```

## ONNX Operator Inventory

The runtime ONNX graph is intentionally simple because decode and NMS are kept
outside the model graph.

Command:

```powershell
G:\FPGA\ir_zynq_detector\.venv-train\Scripts\python.exe `
  G:\FPGA\ir_zynq_detector\pc\scripts\inspect_onnx_model.py `
  --onnx G:\FPGA\ir_zynq_detector\build\model\irdet_ssdlite_ir_runtime_legacy.onnx `
  --output G:\FPGA\ir_zynq_detector\build\model\irdet_ssdlite_ir_runtime_legacy_inspect.json
```

Verified inventory:

```text
nodes=195
input_0 shape=[1, 1, 160, 128]
bbox_regression shape=[1, 660, 4]
cls_logits shape=[1, 660, 4]
anchors_xyxy shape=[660, 4]
Add: 10
Clip: 59
Concat: 2
Conv: 88
Reshape: 24
Transpose: 12
```

This operator set is friendly to lightweight C++ runtimes such as ncnn. There
are no graph-level NMS or custom SSD postprocess operators.

## ncnn Conversion Preparation

The runtime ONNX export originally uses ONNX external tensor data:

```text
G:\FPGA\ir_zynq_detector\build\model\irdet_ssdlite_ir_runtime_legacy.onnx
G:\FPGA\ir_zynq_detector\build\model\irdet_ssdlite_ir_runtime_legacy.onnx.data
```

For conversion tools, a single-file ONNX is often easier to handle. The packed
single-file ONNX is:

```text
G:\FPGA\ir_zynq_detector\build\model\irdet_ssdlite_ir_runtime_legacy_packed.onnx
```

Pack command:

```powershell
G:\FPGA\ir_zynq_detector\.venv-train\Scripts\python.exe `
  G:\FPGA\ir_zynq_detector\pc\scripts\pack_onnx_external_data.py `
  --input G:\FPGA\ir_zynq_detector\build\model\irdet_ssdlite_ir_runtime_legacy.onnx `
  --output G:\FPGA\ir_zynq_detector\build\model\irdet_ssdlite_ir_runtime_legacy_packed.onnx
```

Verified packed ONNX:

```text
output_bytes=12671513
input_0 shape=[1, 1, 160, 128]
bbox_regression shape=[1, 660, 4]
cls_logits shape=[1, 660, 4]
anchors_xyxy shape=[660, 4]
```

ncnn conversion script:

```text
G:\FPGA\ir_zynq_detector\pc\scripts\convert_runtime_onnx_to_ncnn.ps1
```

The verified ncnn-friendly export is the legacy tracer/opset13 ONNX with the
Identity output removed:

```powershell
G:\FPGA\ir_zynq_detector\.venv-train\Scripts\python.exe `
  G:\FPGA\ir_zynq_detector\pc\scripts\export_ssdlite_ir_runtime_onnx.py `
  --checkpoint G:\FPGA\ir_zynq_detector\build\train_ssdlite_ir_formal\best.pt `
  --output G:\FPGA\ir_zynq_detector\build\model\irdet_ssdlite_ir_runtime_legacy_tracer_op13.onnx `
  --metadata-output G:\FPGA\ir_zynq_detector\build\model\irdet_ssdlite_ir_runtime_legacy_tracer_op13.json `
  --manifest G:\FPGA\ir_zynq_detector\build\flir_thermal_3cls\dataset_manifest.json `
  --split val `
  --verify-images 2 `
  --opset 13 `
  --legacy-exporter `
  --single-file

G:\FPGA\ir_zynq_detector\.venv-train\Scripts\python.exe `
  G:\FPGA\ir_zynq_detector\pc\scripts\simplify_onnx_for_ncnn.py `
  --input G:\FPGA\ir_zynq_detector\build\model\irdet_ssdlite_ir_runtime_legacy_tracer_op13.onnx `
  --output G:\FPGA\ir_zynq_detector\build\model\irdet_ssdlite_ir_runtime_legacy_tracer_op13_ncnn.onnx
```

Verified conversion tool:

```text
G:\FPGA\ir_zynq_detector\tools\ncnn\ncnn-20240820-windows-vs2019\x64\bin\onnx2ncnn.exe
```

Run conversion:

```powershell
powershell -ExecutionPolicy Bypass `
  -File G:\FPGA\ir_zynq_detector\pc\scripts\convert_runtime_onnx_to_ncnn.ps1
```

Verified ncnn artifacts:

```text
G:\FPGA\ir_zynq_detector\build\ncnn_runtime_legacy_tracer_op13_ncnn\irdet_ssdlite_ir_runtime_legacy.param
G:\FPGA\ir_zynq_detector\build\ncnn_runtime_legacy_tracer_op13_ncnn\irdet_ssdlite_ir_runtime_legacy.bin
param bytes=52352
bin bytes=12132704
```

`onnx2ncnn` prints a generic PNNX recommendation after conversion. For this
runtime export, the generated `.param/.bin` has been validated by the C++ smoke
test below.

## PC ncnn C++ Smoke Test

The PC smoke test intentionally uses C++ ncnn, not the Python ncnn binding. This
is closer to the future board Linux app and avoids local Python binding issues
seen with the current Windows Python 3.13 environment.

Helper scripts:

```text
G:\FPGA\ir_zynq_detector\pc\scripts\export_ncnn_smoke_vectors.py
G:\FPGA\ir_zynq_detector\pc\ncnn_smoke\irdet_ncnn_smoke.cpp
G:\FPGA\ir_zynq_detector\pc\scripts\run_ncnn_smoke.ps1
```

The smoke script performs three steps:

- exports a fixed FLIR validation sample tensor and ONNX Runtime reference raw
  outputs
- compiles a small C++ ncnn executable with the locally built `libncnn.a`
- loads `.param/.bin`, runs inference, and compares `bbox_regression` and
  `cls_logits`

Run:

```powershell
powershell -ExecutionPolicy Bypass `
  -File G:\FPGA\ir_zynq_detector\pc\scripts\run_ncnn_smoke.ps1
```

Verified result:

```text
Input input_0 shape=(1, 1, 160, 128)
Reference bbox_regression shape=(1, 660, 4)
Reference cls_logits shape=(1, 660, 4)
Detections count=2
det0 class=car score=0.718 bbox=[140, 220, 193, 254]
det1 class=car score=0.551 bbox=[235, 195, 337, 297]
bbox_regression dims=2 w=4 h=660 total=2640
cls_logits dims=2 w=4 h=660 total=2640
Compare bbox_regression max_abs_diff=1.23978e-05 mean_abs_diff=8.48821e-07
Compare cls_logits max_abs_diff=2.28882e-05 mean_abs_diff=1.80784e-06
NCNN_SMOKE_PASS tolerance=0.002
```

This closes the PC-side lightweight runtime proof: the same raw-head tensors
previously verified with ONNX Runtime can now be produced by ncnn.

## Linux User-Space App Skeleton

The next step after the PC ncnn smoke is no longer theoretical. A Linux
user-space detector app skeleton now exists in:

```text
G:\FPGA\ir_zynq_detector\zynq_linux
```

Key files:

```text
G:\FPGA\ir_zynq_detector\zynq_linux\include\irdet_linux_ncnn_detector.h
G:\FPGA\ir_zynq_detector\zynq_linux\src\irdet_linux_ncnn_detector.cpp
G:\FPGA\ir_zynq_detector\zynq_linux\src\irdet_linux_main.cpp
G:\FPGA\ir_zynq_detector\zynq_linux\CMakeLists.txt
G:\FPGA\ir_zynq_detector\zynq_linux\cmake\toolchains\vitis_aarch32_linux.cmake
```

This app already reuses the validated PS-side code for:

- grayscale resize/normalize preprocessing
- SSD box decode
- class softmax
- class-wise NMS

So the Linux runtime path is built on the same postprocess logic already used by
the board-side raw-sample reference path.

## Host Demo Of The Linux App

Before moving to the board, the Linux app logic has been verified on the Windows
host with the locally built `ncnn` library.

Helper scripts:

```text
G:\FPGA\ir_zynq_detector\pc\scripts\export_linux_ncnn_demo_assets.py
G:\FPGA\ir_zynq_detector\pc\scripts\run_linux_ncnn_host_demo.ps1
```

Verified host demo result:

```text
Model backend=ncnn runtime_in=128x160 anchors=660 score_thresh=200 mean=0.5 std=0.5
pre_in=640x512 pre_out=128x160 min=17 max=251 mean_x1000=-212
det_count=2
det0 class=car score=0.718 bbox=[140,220,193,254]
det1 class=car score=0.551 bbox=[235,195,337,297]
```

This is the first verified run of the full software-side deployment chain:

- raw gray8 sample
- C preprocess
- ncnn inference
- C SSD postprocess
- final class/score/bbox printing

It is still a host-side verification, not a board Linux demo yet, but it proves
the chosen runtime architecture is implementable.

## ARM Cross-Build Status

The Windows host can now also cross-build both the runtime library and the Linux
detector application with the Vitis 2020.2 ARM Linux toolchain.

Helper scripts:

```text
G:\FPGA\ir_zynq_detector\pc\scripts\build_ncnn_arm_linux_min.ps1
G:\FPGA\ir_zynq_detector\pc\scripts\build_zynq_linux_arm_ncnn.ps1
```

Verified artifacts on 2026-04-23:

```text
G:\FPGA\ir_zynq_detector\build\ncnn_arm_linux_min\src\libncnn.a
G:\FPGA\ir_zynq_detector\build\zynq_linux_arm_ncnn\irdet_linux_ncnn_app
```

Verified ELF header:

```text
Class: ELF32
Machine: ARM
Flags: hard-float ABI
```

This means the remaining work is no longer "how to build the runtime". The main
remaining tasks are now:

- prepare a runnable Linux image on the Zynq board
- copy the app, model, anchors, and sample input onto the board
- execute the first on-board Linux inference run
- reconnect the PL accelerator path from Linux when the software-only baseline
  is stable

## Image Input For Linux V1

For the Linux true-inference demo, prefer file input first:

- copy a decoded or raw test image to the board
- run the detector app from the Linux shell
- print class, score, and bbox

Reason: the same UART is often used as the Linux console. Sending binary image
frames over the console UART can conflict with shell/U-Boot/Linux messages.

After full inference works, add one of these input paths:

- second UART for binary frame protocol
- TCP socket from PC to board
- SD card batch image input

## Implementation Stages

### Stage A: Freeze Runtime Contract

- keep classes as `person`, `bicycle`, `car`
- keep input tensor as `1x1x128x160`, grayscale, NCHW
- keep normalization as `(gray8 / 255.0 - 0.5) / 0.5`
- make export metadata fail loudly if raw-head width/height silently swaps

### Stage B: Export A Runtime-Friendly Model

- create a transform-free export wrapper for backbone + SSD heads
- input should already be resized and normalized
- output should be raw heads: `bbox_regression`, `cls_logits`, `anchors_xyxy`
- compare PyTorch raw-head output against the existing postprocess verifier

### Stage C: Convert And Smoke-Test Runtime

- convert ONNX to the selected runtime format
- run one PC-side inference smoke test
- confirm raw-head tensor shapes and class ordering

### Stage D: Cross-Compile Linux Detector App

- build a minimal C++ app with the ARM Linux compiler from Vitis
- load runtime model files
- read one image/raw tensor file
- run inference
- call existing SSD postprocess logic
- print detections

### Stage E: Board Linux Demo

- boot board Linux
- copy model, app, and one test image to the board
- run app
- record latency and output detections

### Stage F: Reconnect PL Acceleration

- access PL depthwise scheduler from Linux using `/dev/mem` or a small UIO
  driver
- replay the verified MobileNetV2 depthwise channel case
- compare CPU-only depthwise time versus PL scheduler time
- document the accelerator as an operator-level proof

## When To Retrain

Do not retrain immediately just because the current model has low AP.

Retrain after Stage A and Stage B are stable. That way the next long training
run produces a checkpoint that already matches the final deployment contract.
