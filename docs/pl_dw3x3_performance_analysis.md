# PL DW3X3 Performance Analysis

## Verified Board Result

The full-channel replay has passed on the real Zynq-7020 board.

Verified UART output:

```text
PL dw3x3 batch PASS channel=11 count=16 first_acc=11848 last_acc=26589 scale=65536 cpu_us=7 pl_us=178 pl_per_window_us_x1000=11125
PL dw3x3 channel PASS channel=11 count=1280 first_acc=93502 last_acc=-18304 scale=65536 cpu_us=553 pl_us=13489 pl_per_window_us_x1000=10538
PL dw3x3 full scheduler present at 0x43C10000 info=0xF3282006
PL dw3x3 full scheduler PASS channel=11 count=1280 first_acc=93502 last_acc=-18304 e2e_us=3020 compute_us=692 e2e_per_output_us_x1000=2359
PL dw3x3 selftest rc=0
```

## What These Numbers Mean

For the full exported channel:

- channel: `11`
- output windows: `40x32 = 1280`
- CPU reference check time: `553 us`
- old PS-scheduled PL replay time: `13489 us`
- old PS-scheduled PL replay average: `10.538 us/window`
- new full scheduler end-to-end time: `3020 us`
- new full scheduler compute time: `692 us`
- new full scheduler end-to-end average: `2.359 us/output`

This proves the PL operator is functionally correct over a complete real
MobileNetV2 depthwise channel. It also shows that moving the window loop from
PS into PL removes most of the old per-window AXI-Lite control overhead.

Measured improvement:

- full scheduler end-to-end versus old PS-scheduled PL replay: about `4.47x`
- full scheduler compute-only versus old PS-scheduled PL replay: about `19.5x`
- average output time improves from `10.538 us` to `2.359 us`

The old replay sequence for each window was:

- write 9 input pixels through AXI-Lite
- start the PL core
- poll done
- read one output value
- repeat 1280 times

The full scheduler replaces that loop with one channel load, one start command,
and one output-buffer readback.

## Engineering Conclusion

The current PL stage is a valid correctness demo and a strong project milestone:

- real trained-model data is used
- real PL hardware is used
- a complete depthwise channel is verified
- board timing is measured

However, it should not be presented as final acceleration performance.

The fair explanation is:

> The first PL version validates the MobileNetV2 depthwise 3x3 operator and PS/PL integration. The full-channel scheduler then removes most per-window PS/PL control overhead and gives a measured scheduler-level improvement. The remaining bottleneck is AXI-Lite feature/output transfer, so the next throughput-oriented version should use streaming or DMA.

## Recommended Next Route

The next most reasonable route is not to jump directly to the whole neural
network in HDL. The selected route is:

1. Keep the current AXI-Lite single-window core as the golden board validation baseline.
2. Build a full-channel PL scheduler that loads one channel feature map and one 3x3 kernel, then computes all `40x32` output windows after one start command.
3. Use AXI-Lite only for control and small debug registers.
4. Use BRAM-style memory or AXI BRAM Controller for the first full-channel prototype.
5. Move to AXI DMA / AXI-Stream only after the full-channel scheduler is verified.

This route gives a clear story:

- current version: correct but transaction-bound
- next version: reduce PS/PL transaction overhead
- later version: use DMA for throughput

## Full-Channel Scheduler Build Status

The full-channel scheduler implementation has now been added:

- RTL wrapper: `mobilenet_dw3x3_channel_full_axi`
- address: `0x43C10000`
- driver: `ir_pl_dw3x3_full`
- board selftest integration: `ir_pl_dw3x3_pl_full_scheduler_selftest_run`

Verified so far:

- full-channel AXI testbench passes in Vivado `xsim`
- Vivado project generation passes
- bitstream generation passes
- Vitis selftest ELF builds successfully
- routed timing passes at 50 MHz with WNS `5.079 ns`
- routed utilization is now low enough for Zynq-7020 bring-up:
  - LUT `4.81%`
  - registers `3.29%`
  - BRAM tile `3`
  - DSP `4`
- board UART confirms `PL dw3x3 full scheduler PASS`
- measured board timing:
  - old PS-scheduled PL replay: `13489 us`
  - full scheduler end-to-end: `3020 us`
  - full scheduler compute: `692 us`

Resource note:

- the feature/output buffers now infer BRAM successfully
- the earlier register-buffer version has been replaced
- remaining Vivado DRC warnings are DSP pipeline suggestions, not BRAM/control correctness warnings

## Full-Channel Acceptance Criteria

The full-channel scheduler version passes if:

- PS writes one channel input buffer and one 3x3 weight buffer
- PS writes `start`
- PL internally iterates `40x32` windows
- PS reads back an output buffer
- all `1280` outputs match the exported expected values
- timing improves versus the old `13489 us` AXI-Lite per-window replay

Detailed run steps are documented in:

- `docs/pl_dw3x3_full_scheduler_demo.md`
