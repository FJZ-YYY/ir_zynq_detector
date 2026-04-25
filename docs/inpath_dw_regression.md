# In-Path Regression Baseline

Date: 2026-04-26

## Goal

This document freezes the minimum regression baseline that should stay green
while the detector keeps moving forward.

The purpose is simple:

- keep the unmodified detector path alive
- keep the runtime single-channel PL contract alive
- keep the CPU in-path split alive
- keep the PL in-path split alive

## Baseline Modes

| Mode | What it proves | Must remain true |
| --- | --- | --- |
| `gray8` | full ncnn detector still works | valid `det_count` and `bbox` |
| `runtime_dw_pl_compare` | runtime blob extraction and PL quant contract still match | `rc=0`, `max_abs_acc_err=0` |
| `inpath_dw_cpu_full` | prefix/suffix cut point still correct | `rc=0`, detection result matches or is extremely close to full detector |
| `inpath_dw_pl_full` | PL output still enters the real inference path | `rc=0`, detector remains valid, score drift stays small |

## One-Click Regression Script

Host-side regression entrypoint:

```text
G:\FPGA\ir_zynq_detector\pc\scripts\run_ac880_inpath_regression.ps1
```

Default command:

```powershell
powershell -ExecutionPolicy Bypass -File G:\FPGA\ir_zynq_detector\pc\scripts\run_ac880_inpath_regression.ps1 `
  -RepoRoot G:\FPGA\ir_zynq_detector `
  -ComPort COM3 `
  -BaudRate 115200
```

This script runs these modes in order:

1. `gray8`
2. `runtime_dw_pl_compare`
3. `inpath_dw_cpu_full`
4. `inpath_dw_pl_full`

Behavior:

- first mode may package and deploy the latest Linux bundle
- later modes reuse the same bundle through the fast SSH/SFTP path
- if SSH is not reachable and `ComPort` is provided, the existing serial link
  preparation path can still be reused

## Fast Path Variant

If the bundle is already up to date, skip packaging on all steps:

```powershell
powershell -ExecutionPolicy Bypass -File G:\FPGA\ir_zynq_detector\pc\scripts\run_ac880_inpath_regression.ps1 `
  -RepoRoot G:\FPGA\ir_zynq_detector `
  -ComPort COM3 `
  -BaudRate 115200 `
  -SkipPackageAll
```

## Expected Checks

### `gray8`

Expected lines:

```text
Runtime contract nchw=1x1x128x160 width=160 height=128
det_count=...
det0 class=... bbox=[...]
```

### `runtime_dw_pl_compare`

Expected lines:

```text
runtime_dw_pl_compare rc=0
channel=11
shape=40x32
count=1280
max_abs_acc_err=0
```

### `inpath_dw_cpu_full`

Expected lines:

```text
inpath_dw_cpu_full rc=0
backend=cpu_depthwise
shape=144x40x32
det_count=...
```

### `inpath_dw_pl_full`

Expected lines:

```text
inpath_dw_pl_full rc=0
backend=pl_depthwise_loop_all_channels
channels=144
pl_calls=144
max_abs_acc_err=0
det_count=...
```

## Failure Classification

Use these categories when a regression fails:

- blob extraction failure
- shape mismatch
- quantization parameter mismatch
- PL timeout
- CPU/PL error too large
- suffix reinjection failure
- detector output broken

This keeps the next debugging step clear instead of only reporting a generic
demo failure.
