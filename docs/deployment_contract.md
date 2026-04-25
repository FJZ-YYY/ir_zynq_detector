# Deployment Contract

## Goal

This document defines what is locked for the current Zynq demo and what must be
locked before the next model-quality retraining run.

The current project has two separate truths:

- the live UART image path is already `gray8 -> resize -> normalize -> detector`
- the current real-model backend is still a raw-head sample used to validate SSD
  decode and NMS on the PS side

So this stage should not be described as complete board-side neural inference.
It should be described as a verified deployment interface bridge.

## Current Demo Contract

Config file:

```text
G:\FPGA\ir_zynq_detector\configs\deploy_contract_ssdlite_ir_v1.json
```

Live image input:

- PC decodes FLIR `jpg/png`
- PC sends decoded `gray8` pixels through UART
- packet carries width, height, payload length, frame id, and checksum
- board validates checksum before preprocessing

PS preprocessing output:

- layout: `NCHW`
- dtype: `float32`
- shape: `1x1x128x160`
- width: `160`
- height: `128`
- normalization: `(gray8 / 255.0 - 0.5) / 0.5`

Current SSDLite raw-head sample:

- classes: background, person, bicycle, car
- anchors: `660`
- classes with background: `4`
- SSD postprocess: decode, softmax, score threshold, class-wise NMS, source-box
  remap
- current demo expected first detection: `car score=0.719 bbox=[140,220,193,254]`
- board raw-sample UART demo: verified on 2026-04-23

PL acceleration proof:

- operator: MobileNetV2 depthwise `3x3`
- single-window MMIO accelerator: `0x43C00000`
- full-channel scheduler: `0x43C10000`
- verified real replay: channel `11`, feature map `40x32`, outputs `1280`

## Important Current Limitation

The current trained checkpoint is internally consistent, but its exported
torchvision SSD transform reports a raw-head tensor space of `width=128` and
`height=160`.

This is acceptable for the current interface validation because:

- PC raw-head verification matches PyTorch detector output
- transform-free runtime legacy export matches the current checkpoint's
  transformed tensor space
- C postprocess reproduces the exported real raw-head sample
- board raw-sample backend uses the exported raw-head tensor dimensions

This should not be treated as the final fixed training contract.

## When To Lock The Fixed Input Contract

Do not retrain only to clean up the width/height convention. That would spend a
long training run without improving model quality.

Lock the fixed contract immediately before the next model-quality retraining
pass. At that point, these fields must be frozen together:

- class list: `person`, `bicycle`, `car`
- tensor layout: `NCHW`
- channel count: `1`
- input shape: `1x1x128x160`
- intended image size: `height=128`, `width=160`
- normalization formula
- anchor generation dimensions
- raw-head output dimensions
- PS postprocess dimensions
- ONNX metadata format

The retraining pass should only start after a small export smoke test proves
that train, eval, export, PS preprocess, and SSD postprocess agree on the same
width/height convention.

## Next Engineering Step

The raw-sample UART app has been verified on the board. The next step is to
continue toward a real inference backend:

- keep the raw-sample backend as a known-good PS postprocess reference
- prefer board Linux plus a lightweight C/C++ inference runtime for full
  SSDLite-MobileNetV2 inference
- keep the PL depthwise accelerator as the operator-level acceleration proof
- only start the next model-quality retraining pass after the fixed input
  contract checks are in place

Detailed runtime route:

```text
G:\FPGA\ir_zynq_detector\docs\true_inference_runtime_plan.md
```
