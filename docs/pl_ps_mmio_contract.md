# PL-PS MMIO Contract For Depthwise 3x3 Core

## Goal

This document defines the first stable software-visible interface between:

- PS software on Zynq
- the PL depthwise 3x3 validation block

This contract is carried by an AXI-Lite visible slave, but the register semantics
are intentionally kept very small and MMIO-like so PS software can stay simple.

The goal is to freeze:

- register meaning
- software load/start/readback flow
- module responsibilities

## Target PL Block

Current wrapper:

- `zynq_pl/rtl/mobilenet_dw3x3_channel_mmio.sv`

Current compute core inside the wrapper:

- `zynq_pl/rtl/mobilenet_dw3x3_channel_core.sv`

Current scope:

- one `3x3` input window
- one `3x3` depthwise kernel
- one bias
- one signed output result register

## Register Map

Base address plus offsets:

- `0x00` `CONTROL`
- `0x04` `CFG_DIMS`
- `0x08` `BIAS`
- `0x0C` `FEAT_ADDR`
- `0x10` `FEAT_DATA`
- `0x14` `WEIGHT_ADDR`
- `0x18` `WEIGHT_DATA`
- `0x1C` `OUT_ADDR`
- `0x20` `OUT_DATA`
- `0x24` `INFO`

## Register Details

### `CONTROL` at `0x00`

Write bits:

- bit `0`: `START`
- bit `1`: `CLEAR_DONE`

Read bits:

- bit `1`: `DONE`
- bit `2`: `BUSY`
- bit `3`: `CFG_READY`

### `CFG_DIMS` at `0x04`

- `[15:0]` window width
- `[31:16]` window height
- current stable value is `3x3`

### `BIAS` at `0x08`

- signed 32-bit bias for the current depthwise channel

### `FEAT_ADDR` at `0x0C`

- window element index `0..8` to be written next

### `FEAT_DATA` at `0x10`

- lower 16 bits carry one signed feature element
- a write stores the value at `FEAT_ADDR`

### `WEIGHT_ADDR` at `0x14`

- weight tap index `0..8`

### `WEIGHT_DATA` at `0x18`

- lower 16 bits carry one signed weight value
- a write stores the value at `WEIGHT_ADDR`

### `OUT_ADDR` at `0x1C`

- reserved for software compatibility
- current single-window implementation reads only one output, so software writes `0`

### `OUT_DATA` at `0x20`

- signed 32-bit output value for the current `3x3` window

### `INFO` at `0x24`

Simple build info register:

- `[7:0]` version
- `[15:8]` supported width
- `[23:16]` supported height

## PS Software Sequence

Recommended first-version sequence:

1. Write `CFG_DIMS = 3x3`
2. Write `BIAS`
3. Loop over 9 window pixels:
   write `FEAT_ADDR`, then write `FEAT_DATA`
4. Loop over 9 weights:
   write `WEIGHT_ADDR`, then write `WEIGHT_DATA`
5. Write `CONTROL.START = 1`
6. Poll `CONTROL.DONE`
7. Write `OUT_ADDR = 0`, then read `OUT_DATA`

## Current Software Driver

PS-side driver skeleton:

- `zynq_ps/include/ir_pl_dw3x3.h`
- `zynq_ps/src/ir_pl_dw3x3.c`

Current provided operations:

- configure `3x3` window mode and bias
- write one `3x3` window
- write 9 weights
- start compute
- poll done
- read back one output value

## Current Validation

### RTL-side

Testbench:

- `zynq_pl/tb/mobilenet_dw3x3_channel_mmio_tb.sv`

Validated flow:

- MMIO writes for config, window pixels, and weights
- start pulse
- done polling
- single output readback and compare

### PS-side

Mock test:

- `zynq_ps/tests/ir_pl_dw3x3_mock_test.c`

Validated flow:

- software driver uses the same register contract
- a mock MMIO device emulates the PL behavior
- single output value matches the expected depthwise result

## Why This Step Matters

This interface is the bridge from:

- “we have a correct RTL operator”

to:

- “PS software can call a PL accelerator in a controlled way”

Once this interface is stable, moving to:

- real AXI-Lite register bank
- BRAM-backed buffers
- AXI DMA or AXI-Stream

becomes an implementation upgrade rather than a project rewrite.

## Current Integration Note

The contract is now carried through an AXI-accessible wrapper in hardware:

- AXI wrapper:
  - `zynq_pl/rtl/mobilenet_dw3x3_channel_axi.v`
  - `zynq_pl/rtl/mobilenet_dw3x3_channel_axi.sv`
- integrated block design cell:
  - `dw3x3_accel_0`

With the current generated hardware platform, the accelerator base address is:

- `0x43C00000`

In software, this is exposed through:

- `XPAR_DW3X3_ACCEL_0_BASEADDR`
