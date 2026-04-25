# SSDLite IR Model Evaluation And Export

## Goal

This stage verifies the PC-trained SSDLite-MobileNetV2 infrared detector before
it is connected to the board-side deployment path.

This is separate from the PL depthwise demo:

- model evaluation checks detection quality on `FLIR_ADAS_v2`
- ONNX export provides the raw-head tensors needed by a deployment runtime
- PL depthwise acceleration remains the operator-level hardware acceleration proof

## Current Model Artifacts

Checkpoint:

- `G:\FPGA\ir_zynq_detector\build\train_ssdlite_ir_formal\best.pt`

ONNX raw-head export:

- `G:\FPGA\ir_zynq_detector\build\model\irdet_ssdlite_ir_formal.onnx`
- `G:\FPGA\ir_zynq_detector\build\model\irdet_ssdlite_ir_formal.json`

Transform-free runtime legacy export:

- `G:\FPGA\ir_zynq_detector\build\model\irdet_ssdlite_ir_runtime_legacy.onnx`
- `G:\FPGA\ir_zynq_detector\build\model\irdet_ssdlite_ir_runtime_legacy.json`

Evaluation output:

- `G:\FPGA\ir_zynq_detector\build\eval_ssdlite_ir_formal\metrics.json`
- `G:\FPGA\ir_zynq_detector\build\eval_ssdlite_ir_formal\summary.txt`
- `G:\FPGA\ir_zynq_detector\build\eval_ssdlite_ir_formal\detections.json`
- `G:\FPGA\ir_zynq_detector\build\eval_ssdlite_ir_formal\vis\`

## Quick Smoke Evaluation

Use this when checking that the environment, checkpoint, dataset manifest, and
visualization path still work.

```powershell
powershell -ExecutionPolicy Bypass -File G:\FPGA\ir_zynq_detector\pc\scripts\run_eval_ssdlite_ir.ps1 `
  -MaxImages 16 `
  -BatchSize 4 `
  -NumWorkers 0 `
  -VisCount 4 `
  -Amp
```

Verified smoke result:

```text
Evaluation finished for 16 images on cuda.
mAP50=0.0486 mAP50_95=0.0203
person: ap50=0.0402 ap50_95=0.0094 gt=32 pred=101
bicycle: ap50=nan ap50_95=nan gt=0 pred=15
car: ap50=0.0571 ap50_95=0.0311 gt=39 pred=108
```

The smoke score is not a formal quality result because it only uses the first
16 validation images.

## Formal Validation Evaluation

```powershell
powershell -ExecutionPolicy Bypass -File G:\FPGA\ir_zynq_detector\pc\scripts\run_eval_ssdlite_ir.ps1 `
  -BatchSize 8 `
  -NumWorkers 0 `
  -VisCount 16 `
  -Amp
```

Verified full validation result:

```text
Evaluation finished for 1096 images on cuda.
mAP50=0.0689 mAP50_95=0.0243
person: ap50=0.0295 ap50_95=0.0061 gt=4470 pred=9579
bicycle: ap50=0.0452 ap50_95=0.0107 gt=170 pred=2088
car: ap50=0.1322 ap50_95=0.0560 gt=7133 pred=12408
```

Interpretation:

- the training/evaluation/export chain is functional
- the current model is good enough to continue integration testing
- the current model is not yet accurate enough to present as a final detector
- `car` is the strongest class so far
- `person` and `bicycle` need another training/architecture pass later

## ONNX Raw-Head Export

```powershell
G:\FPGA\ir_zynq_detector\.venv-train\Scripts\python.exe `
  G:\FPGA\ir_zynq_detector\pc\scripts\export_ssdlite_ir_onnx.py `
  --checkpoint G:\FPGA\ir_zynq_detector\build\train_ssdlite_ir_formal\best.pt `
  --output G:\FPGA\ir_zynq_detector\build\model\irdet_ssdlite_ir_formal.onnx `
  --metadata-output G:\FPGA\ir_zynq_detector\build\model\irdet_ssdlite_ir_formal.json
```

Verified export summary:

```text
Classes: person, bicycle, car
Input tensor: 1x1x128x160
Internal transform tensor: (1, 1, 160, 128) image_size=(160, 128)
Outputs: bbox_regression=(1, 660, 4) cls_logits=(1, 660, 4) anchors_xyxy=(660, 4)
```

The exported ONNX intentionally stops before SSD decode and NMS. This makes the
deployment contract explicit:

- runtime input: normalized grayscale tensor `1x1x128x160`
- current exported graph keeps the torchvision SSD transform inside the graph
- current internal detection tensor is `1x1x160x128`
- runtime outputs:
  - `bbox_regression`: SSD box deltas
  - `cls_logits`: class logits including background
  - `anchors_xyxy`: anchor boxes in resized model coordinates
- PS-side postprocess:
  - decode box deltas against anchors
  - apply softmax
  - score threshold
  - class-wise NMS
  - map boxes back to source image size

Important note:

The current checkpoint was trained and exported with the same torchvision SSD
transform behavior, so it is internally consistent. For a later bare-metal C
runtime that bypasses torchvision/ONNX transforms, we should explicitly choose
and retrain one fixed tensor contract, preferably `1x1x128x160` for
`height=128, width=160`.

## Transform-Free Runtime Legacy Export

This export removes the torchvision SSD transform from the ONNX graph. The input
is therefore not the original image tensor. It is the already-resized and
already-normalized internal tensor used by the current checkpoint.

Command:

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

Verified export result:

```text
Runtime input tensor: 1x1x160x128
Checkpoint training hint: 1x1x128x160 (pre-transform)
Outputs: bbox_regression=(1, 660, 4) cls_logits=(1, 660, 4) anchors_xyxy=(660, 4)
Verification records=3 tolerance=1.0e-05 PASS
```

Contract check:

```powershell
G:\FPGA\ir_zynq_detector\.venv-train\Scripts\python.exe `
  G:\FPGA\ir_zynq_detector\pc\scripts\check_deploy_contract.py `
  --contract G:\FPGA\ir_zynq_detector\configs\deploy_contract_ssdlite_ir_v1.json `
  --runtime-metadata G:\FPGA\ir_zynq_detector\build\model\irdet_ssdlite_ir_runtime_legacy.json `
  --allow-legacy-current
```

Verified contract result:

```text
CONTRACT_LEGACY_OK: runtime metadata is compatible with the current checkpoint
CONTRACT_WARNING: runtime input shape differs from the live PS preprocess shape; do not use this as the next retraining contract
CONTRACT_WARNING: metadata explicitly marks this export as not future-fixed
```

PC ONNX Runtime smoke command:

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

Verified ONNX Runtime result:

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

ONNX operator inventory:

```powershell
G:\FPGA\ir_zynq_detector\.venv-train\Scripts\python.exe `
  G:\FPGA\ir_zynq_detector\pc\scripts\inspect_onnx_model.py `
  --onnx G:\FPGA\ir_zynq_detector\build\model\irdet_ssdlite_ir_runtime_legacy.onnx `
  --output G:\FPGA\ir_zynq_detector\build\model\irdet_ssdlite_ir_runtime_legacy_inspect.json
```

Verified operator counts:

```text
nodes=195
Add: 10
Clip: 59
Concat: 2
Conv: 88
Reshape: 24
Transpose: 12
```

Packed single-file ONNX for converter compatibility:

```powershell
G:\FPGA\ir_zynq_detector\.venv-train\Scripts\python.exe `
  G:\FPGA\ir_zynq_detector\pc\scripts\pack_onnx_external_data.py `
  --input G:\FPGA\ir_zynq_detector\build\model\irdet_ssdlite_ir_runtime_legacy.onnx `
  --output G:\FPGA\ir_zynq_detector\build\model\irdet_ssdlite_ir_runtime_legacy_packed.onnx
```

Verified packed output:

```text
G:\FPGA\ir_zynq_detector\build\model\irdet_ssdlite_ir_runtime_legacy_packed.onnx
output_bytes=12671513
```

ncnn conversion helper:

```powershell
powershell -ExecutionPolicy Bypass `
  -File G:\FPGA\ir_zynq_detector\pc\scripts\convert_runtime_onnx_to_ncnn.ps1
```

Verified local tool:

```text
G:\FPGA\ir_zynq_detector\tools\ncnn\ncnn-20240820-windows-vs2019\x64\bin\onnx2ncnn.exe
```

Verified output:

```text
G:\FPGA\ir_zynq_detector\build\ncnn_runtime_legacy_tracer_op13_ncnn\irdet_ssdlite_ir_runtime_legacy.param
G:\FPGA\ir_zynq_detector\build\ncnn_runtime_legacy_tracer_op13_ncnn\irdet_ssdlite_ir_runtime_legacy.bin
```

## Raw-Head Postprocess Verification

The raw-head verification script checks that an independent decode + softmax +
class-wise NMS path reproduces the PyTorch detector output.

Smoke command:

```powershell
G:\FPGA\ir_zynq_detector\.venv-train\Scripts\python.exe `
  G:\FPGA\ir_zynq_detector\pc\scripts\verify_ssd_raw_postprocess.py `
  --checkpoint G:\FPGA\ir_zynq_detector\build\train_ssdlite_ir_formal\best.pt `
  --manifest G:\FPGA\ir_zynq_detector\build\flir_thermal_3cls\dataset_manifest.json `
  --output-dir G:\FPGA\ir_zynq_detector\build\verify_ssd_raw_postprocess_smoke `
  --max-images 8 `
  --device auto
```

Verified smoke result:

```text
Raw postprocess verify images=8 mismatches=0 max_box_abs_diff=0.00003052 max_score_abs_diff=0.00000000
```

Larger interface check:

```powershell
G:\FPGA\ir_zynq_detector\.venv-train\Scripts\python.exe `
  G:\FPGA\ir_zynq_detector\pc\scripts\verify_ssd_raw_postprocess.py `
  --checkpoint G:\FPGA\ir_zynq_detector\build\train_ssdlite_ir_formal\best.pt `
  --manifest G:\FPGA\ir_zynq_detector\build\flir_thermal_3cls\dataset_manifest.json `
  --output-dir G:\FPGA\ir_zynq_detector\build\verify_ssd_raw_postprocess_formal `
  --max-images 64 `
  --device auto
```

Verified larger check:

```text
Raw postprocess verify images=64 mismatches=0 max_box_abs_diff=0.00006104 max_score_abs_diff=0.00000000
```

This gives the PS-side C postprocess a concrete reference:

- bbox decode formula matches torchvision SSD
- softmax scores match exactly
- NMS ordering and class labels match
- remaining box difference is only floating-point roundoff

## PS C Raw-Head Sample Test

The next bridge step exports one real model raw-head output to a C header, then
uses the PS-side C postprocess implementation to decode it.

Export command:

```powershell
G:\FPGA\ir_zynq_detector\.venv-train\Scripts\python.exe `
  G:\FPGA\ir_zynq_detector\pc\scripts\export_ssd_raw_sample.py `
  --checkpoint G:\FPGA\ir_zynq_detector\build\train_ssdlite_ir_formal\best.pt `
  --manifest G:\FPGA\ir_zynq_detector\build\flir_thermal_3cls\dataset_manifest.json `
  --output-dir G:\FPGA\ir_zynq_detector\build\ssd_raw_sample `
  --c-header-out G:\FPGA\ir_zynq_detector\zynq_ps\include\ir_ssd_raw_sample_data.h `
  --index 0 `
  --device auto
```

Verified export result:

```text
Exported raw sample image_id=0 index=0
source=640x512 model=128x160 anchors=660 classes=4
expected_detections=2
class=car score=0.719 bbox=[140, 220, 193, 254]
class=car score=0.551 bbox=[235, 195, 337, 297]
```

Host-side C test command:

```powershell
gcc -std=c99 -Wall -Wextra `
  -IG:\FPGA\ir_zynq_detector\zynq_ps\include `
  G:\FPGA\ir_zynq_detector\zynq_ps\tests\ir_ssd_postprocess_raw_sample_test.c `
  G:\FPGA\ir_zynq_detector\zynq_ps\src\ir_ssd_postprocess.c `
  -lm `
  -o G:\FPGA\ir_zynq_detector\build\ir_ssd_postprocess_raw_sample_test.exe

G:\FPGA\ir_zynq_detector\build\ir_ssd_postprocess_raw_sample_test.exe
```

Verified C output:

```text
Raw sample OK: image_id=0 count=2
det0 class=car score=0.719 bbox=[140,220,193,254]
det1 class=car score=0.551 bbox=[235,195,337,297]
```

This means the PS-side C postprocess can already consume real SSDLite raw-head
tensors. The remaining missing piece for true board inference is the runtime
that produces those tensors on the board.

The raw sample is also wired into `ir_model_runner` as an optional backend. The
default backend remains `stub`, so the existing UART demo behavior is unchanged.

Host-side runner test:

```powershell
gcc -std=c99 -Wall -Wextra `
  -IG:\FPGA\ir_zynq_detector\zynq_ps\include `
  G:\FPGA\ir_zynq_detector\zynq_ps\tests\ir_model_runner_raw_sample_test.c `
  G:\FPGA\ir_zynq_detector\zynq_ps\src\ir_model_runner.c `
  G:\FPGA\ir_zynq_detector\zynq_ps\src\ir_detector_stub.c `
  G:\FPGA\ir_zynq_detector\zynq_ps\src\ir_ssd_postprocess.c `
  -lm `
  -o G:\FPGA\ir_zynq_detector\build\ir_model_runner_raw_sample_test.exe

G:\FPGA\ir_zynq_detector\build\ir_model_runner_raw_sample_test.exe
```

Verified runner output:

```text
Runner raw sample OK: backend=ssd_raw_head count=2 first=car score=0.719 bbox=[140,220,193,254]
```

## Board Raw-Sample UART Demo

The raw sample backend is also available as a separate Vitis bare-metal UART
application. It keeps the UART receive, checksum, resize, normalize, and PL
depthwise probe flow active, then uses the exported real SSDLite raw-head sample
to exercise the PS-side SSD decode/NMS code on the board.

Build command:

```powershell
F:\Xilinx\Vitis\2020.2\bin\xsct.bat `
  G:\FPGA\ir_zynq_detector\vitis\create_baremetal_raw_sample_app.tcl
```

Verified build artifact:

```text
G:\FPGA\ir_zynq_detector\build\vitis_raw_sample\irdet_uart_rx_raw_sample\Debug\irdet_uart_rx_raw_sample.elf
```

Run command:

```powershell
F:\Xilinx\Vitis\2020.2\bin\xsct.bat `
  G:\FPGA\ir_zynq_detector\vitis\run_uart_rx_raw_sample_on_board.tcl
```

Expected boot line:

```text
Model backend=ssd_raw_head input=128x160 threshold=0.200
```

Send one FLIR thermal validation image from the PC:

```powershell
python G:\FPGA\ir_zynq_detector\pc\tools\send_uart_image.py `
  --dataset-root "G:\chormxiazai\FLIR_ADAS_v2" `
  --match "images_thermal_val\data" `
  --index 0 `
  --port COM3 `
  --baud 921600 `
  --wait-ack
```

Expected detection fields:

```text
DET_OK class=car score=0.719 bbox=[140,220,193,254]
```

Verified board response on 2026-04-23:

```text
frame_id=1 width=640 height=512 payload=327680 checksum_rx=0x0280F887 checksum_calc=0x0280F887 pre_in=640x512 pre_out=160x128 min=1 max=255 mean_x1000=502 pl_dw3x3_rc=0 cpu=91 pl=91 det_count=2 RX_OK PRE_OK DET_OK class=car score=0.719 bbox=[140,220,193,254]
```

Notes:

- this backend intentionally ignores the live image tensor for detection
- the live image path is still useful because it validates UART receive,
  checksum, resize/normalize, and PL probe integration
- this is an interface validation step, not final board-side neural inference
- the default UART app still uses `stub` unless it is built with the raw sample
  backend macro

## Fixed Input Contract Timing

We should not retrain only to fix the `128x160` versus `160x128` transform
detail right now. The correct timing to lock the fixed input contract is the
next model-quality training pass.

The current deployment contract is recorded in:

- `G:\FPGA\ir_zynq_detector\configs\deploy_contract_ssdlite_ir_v1.json`
- `G:\FPGA\ir_zynq_detector\docs\deployment_contract.md`

Before that retraining pass, freeze these choices together:

- tensor layout: `NCHW`
- channel count: `1`
- intended model input: `height=128, width=160`
- whether the ONNX graph keeps or removes torchvision's internal transform
- PS preprocessing output dimensions
- anchor generation dimensions
- raw-head postprocess dimensions

Then retrain/export/evaluate once under that exact contract. This avoids
spending a long training run only to fix an interface detail while the current
model accuracy is still known to be weak.

## ncnn Runtime Smoke

The runtime ONNX has been converted to ncnn and verified on the Windows PC with a
small C++ ncnn executable.

Conversion command:

```powershell
powershell -ExecutionPolicy Bypass `
  -File G:\FPGA\ir_zynq_detector\pc\scripts\convert_runtime_onnx_to_ncnn.ps1
```

Smoke command:

```powershell
powershell -ExecutionPolicy Bypass `
  -File G:\FPGA\ir_zynq_detector\pc\scripts\run_ncnn_smoke.ps1
```

Verified artifacts:

```text
G:\FPGA\ir_zynq_detector\build\ncnn_runtime_legacy_tracer_op13_ncnn\irdet_ssdlite_ir_runtime_legacy.param
G:\FPGA\ir_zynq_detector\build\ncnn_runtime_legacy_tracer_op13_ncnn\irdet_ssdlite_ir_runtime_legacy.bin
G:\FPGA\ir_zynq_detector\build\ncnn_smoke\irdet_ncnn_smoke.exe
G:\FPGA\ir_zynq_detector\build\ncnn_smoke\ncnn_smoke_vectors.json
```

Verified output:

```text
Compare bbox_regression max_abs_diff=1.23978e-05 mean_abs_diff=8.48821e-07
Compare cls_logits max_abs_diff=2.28882e-05 mean_abs_diff=1.80784e-06
NCNN_SMOKE_PASS tolerance=0.002
```

The next true-inference task is to port this C++ ncnn smoke structure into a
board-side Linux detector app, then reuse the existing C SSD postprocess.

## Next Recommended Step

The PC-verified raw-head contract has now been bridged into the Zynq PS UART
application and verified on the board. The next engineering step is to choose
the first true inference runtime:

- keep the current stub detector output as a fallback
- keep the raw-sample backend as the real-tensor C postprocess reference
- prefer board Linux plus a lightweight C/C++ inference runtime for full
  SSDLite-MobileNetV2 inference
- keep the PL depthwise scheduler as the operator-level hardware acceleration
  proof and integration target
- lock the final fixed input contract before the next model-quality retraining
  pass
