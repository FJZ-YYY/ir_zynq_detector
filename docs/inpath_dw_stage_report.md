# In-Path Depthwise Stage Report

Date: 2026-04-26

## Scope

This report freezes the current board-verified state of the Zynq-7020 / AC880
infrared detector project after the `prefix + depthwise + suffix` milestone was
completed.

The goal of this stage was not peak performance. The goal was to prove that the
existing PL full scheduler output can enter the live detector inference path and
still produce valid SSD detections on the board.

## Fixed Runtime Contract

- Platform: AC880 / Zynq-7020
- PS runtime: Linux + ncnn detector
- PL accelerator: depthwise `3x3` full-channel scheduler
- PL full scheduler base: `0x43C10000`
- Input contract: `NCHW = 1x1x128x160`
- Runtime log convention: `runtime_in=160x128` means `width x height`

Target operator:

- Layer: `backbone.features.0.3.conv.1.0`
- Input blob: `/inner/backbone/features.0/features.0.3/conv/conv.0/conv.0.2/Clip_output_0`
- Output blob: `/inner/backbone/features.0/features.0.3/conv/conv.1/conv.1.2/Clip_output_0`
- Tensor shape: `C=144, H=32, W=40`
- Per-channel element count: `1280`

## Verified Paths

Three execution paths are now frozen as the current baseline:

| Path | Meaning | Current status |
| --- | --- | --- |
| `full ncnn` | Unmodified detector path on Linux | PASS |
| `inpath_dw_cpu_full` | `prefix + CPU full depthwise + suffix` | PASS |
| `inpath_dw_pl_full` | `prefix + PL loop all channels + suffix` | PASS |

The old side-band validation path is still kept as a guardrail:

| Path | Meaning | Current status |
| --- | --- | --- |
| `runtime_dw_pl_compare` | Runtime blob, single channel, CPU/PL compare only | PASS |

## Commands Used

Full detector reference:

```powershell
powershell -ExecutionPolicy Bypass -File G:\FPGA\ir_zynq_detector\pc\scripts\run_ac880_linux_demo.ps1 `
  -RepoRoot G:\FPGA\ir_zynq_detector `
  -Mode gray8 `
  -ComPort COM3 `
  -BaudRate 115200
```

Single-channel runtime compare:

```powershell
powershell -ExecutionPolicy Bypass -File G:\FPGA\ir_zynq_detector\pc\scripts\run_ac880_linux_demo.ps1 `
  -RepoRoot G:\FPGA\ir_zynq_detector `
  -Mode runtime_dw_pl_compare `
  -ComPort COM3 `
  -BaudRate 115200
```

CPU in-path validation:

```powershell
powershell -ExecutionPolicy Bypass -File G:\FPGA\ir_zynq_detector\pc\scripts\run_ac880_linux_demo.ps1 `
  -RepoRoot G:\FPGA\ir_zynq_detector `
  -Mode inpath_dw_cpu_full `
  -ComPort COM3 `
  -BaudRate 115200
```

PL in-path validation:

```powershell
powershell -ExecutionPolicy Bypass -File G:\FPGA\ir_zynq_detector\pc\scripts\run_ac880_linux_demo.ps1 `
  -RepoRoot G:\FPGA\ir_zynq_detector `
  -Mode inpath_dw_pl_full `
  -ComPort COM3 `
  -BaudRate 115200
```

## Latest Frozen Outputs

### 1. Full ncnn detector

Observed board output:

```text
Runtime contract nchw=1x1x128x160 width=160 height=128
det_count=4
det0 class=car score=0.508 bbox=[231,214,334,297]
det1 class=car score=0.404 bbox=[143,229,179,261]
det2 class=car score=0.236 bbox=[396,235,423,253]
det3 class=car score=0.204 bbox=[207,234,226,251]
```

### 2. Prefix + CPU full depthwise + suffix

Observed board output:

```text
target_layer=backbone.features.0.3.conv.1.0
input_blob=/inner/backbone/features.0/features.0.3/conv/conv.0/conv.0.2/Clip_output_0
output_blob=/inner/backbone/features.0/features.0.3/conv/conv.1/conv.1.2/Clip_output_0
shape=144x40x32
backend=cpu_depthwise
cpu_dw_us=20419
full_ref det_count=4
inpath_dw_cpu_full rc=0
det_count=4
det0 class=car score=0.508 bbox=[231,214,334,297]
det1 class=car score=0.404 bbox=[143,229,179,261]
det2 class=car score=0.236 bbox=[396,235,423,253]
det3 class=car score=0.204 bbox=[207,234,226,251]
```

Interpretation:

- The cut point is correct.
- The suffix injection blob is correct.
- CPU-generated depthwise output matches the full detector result for this test
  image.

### 3. Prefix + PL full depthwise + suffix

Observed board output:

```text
target_layer=backbone.features.0.3.conv.1.0
input_blob=/inner/backbone/features.0/features.0.3/conv/conv.0/conv.0.2/Clip_output_0
output_blob=/inner/backbone/features.0/features.0.3/conv/conv.1/conv.1.2/Clip_output_0
shape=144x40x32
backend=pl_depthwise_loop_all_channels
channels=144
per_channel_count=1280
pl_calls=144
frac_bits=8
max_abs_acc_err=0
max_abs_float_err=0.026110
mean_abs_float_err=0.000993
cpu_dw_us=20380
pl_e2e_us=287641
pl_compute_us_total=49984
first_cpu_acc=39893
first_pl_acc=39893
last_cpu_acc=3108
last_pl_acc=3108
full_ref det_count=4
inpath_dw_pl_full rc=0
det_count=4
det0 class=car score=0.510 bbox=[231,214,334,297]
det1 class=car score=0.404 bbox=[143,229,179,261]
det2 class=car score=0.237 bbox=[396,235,423,253]
det3 class=car score=0.207 bbox=[207,234,226,251]
```

Interpretation:

- The PL output is now part of the true detector inference path.
- The detector does not crash after reinjection.
- The final SSD output remains valid.
- Bounding boxes are unchanged for the frozen sample.
- Small score drift is expected because the current PL path uses the verified
  quantized contract instead of the original full-float depthwise layer.

## Accuracy and Performance Summary

| Metric | `inpath_dw_cpu_full` | `inpath_dw_pl_full` |
| --- | --- | --- |
| Backend | CPU float full depthwise | PL quantized per-channel loop |
| Channels | `144` | `144` |
| Per-channel count | `1280` | `1280` |
| Compare status | full detector match | detector output still valid |
| `cpu_dw_us` | `20419` | `20380` |
| `pl_e2e_us` | not applicable | `287641` |
| `pl_compute_us_total` | not applicable | `49984` |
| `max_abs_acc_err` | not applicable | `0` |
| `max_abs_float_err` | not applicable | `0.026110` |
| `mean_abs_float_err` | not applicable | `0.000993` |

Important note:

- `pl_e2e_us` is much larger than `pl_compute_us_total` because this stage still
  uses AXI-Lite writes and reads for every channel.
- The current implementation is intentionally an operator-level proof, not a
  final DMA or streaming design.

## Acceptance Result

This stage is accepted because all of the following are now true at the same
time on the real board:

- runtime contract remains `1x1x128x160`
- detector still prints valid `det_count` and `bbox`
- PL single-channel runtime compare still passes
- CPU in-path reinjection passes
- PL in-path reinjection passes

The project has therefore moved from:

```text
offline exported real-layer replay -> PL compare
```

to:

```text
gray8 -> Linux prefix -> PL full depthwise -> Linux suffix -> SSD detections
```

## Current Limitations

- The PL full scheduler is still invoked one channel at a time.
- PS still performs quantization, per-channel transfer, and output tensor
  assembly.
- ReLU6 is still applied on PS after PL output dequantization.
- The result is not a final performance implementation.
- No DMA, stream, or boot-persistent path is introduced in this stage.

## Recommended Next Step

Keep the current four-mode regression baseline stable first:

- `gray8`
- `runtime_dw_pl_compare`
- `inpath_dw_cpu_full`
- `inpath_dw_pl_full`

Only after that should the project consider a higher-throughput transport path
such as DMA or a wider multi-channel PL design.
