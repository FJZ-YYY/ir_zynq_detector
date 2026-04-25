# PL DW3X3 Full-Channel Scheduler Demo

## Goal

This demo is the next step after the AXI-Lite single-window depthwise 3x3
accelerator.

The single-window accelerator proves correctness, but PS must schedule every
output window one by one. The full-channel scheduler changes the contract:

- PS writes one input feature channel.
- PS writes one 3x3 depthwise kernel and bias.
- PS writes one start command.
- PL internally iterates the whole `40x32` output feature map.
- PS reads back the output buffer and compares it with exported golden data.

This is still a validation accelerator, not a full neural-network hardware
implementation.

## Current Hardware Map

Current Vivado block design contains both accelerators:

- `0x43C00000`: original single-window `dw3x3_accel_0`
- `0x43C10000`: new full-channel scheduler `dw3x3_full_0`
- `0x41200000`: AXI GPIO debug probe

Keeping both IP blocks is intentional. The single-window block remains the
board-proven golden reference while the full-channel block is validated.

## Key Files

RTL:

- `zynq_pl/rtl/mobilenet_dw3x3_channel_full_mmio.sv`
- `zynq_pl/rtl/mobilenet_dw3x3_channel_full_axi.v`
- `zynq_pl/rtl/mobilenet_dw3x3_channel_full_axi.sv`

Testbench:

- `zynq_pl/tb/mobilenet_dw3x3_channel_full_axi_tb.sv`

PC export:

- `pc/scripts/export_depthwise_full_channel.py`

Generated PS-side golden data:

- `zynq_ps/include/ir_pl_dw3x3_full_channel_data.h`

PS driver:

- `zynq_ps/include/ir_pl_dw3x3_full.h`
- `zynq_ps/src/ir_pl_dw3x3_full.c`

Board selftest:

- `zynq_ps/src/ir_pl_dw3x3_selftest.c`
- `vitis/create_dw3x3_selftest_app.tcl`
- `vitis/run_dw3x3_selftest_on_board.tcl`

## Verified PC/Vivado Steps

Generate the full-channel exported case:

```powershell
G:\FPGA\ir_zynq_detector\.venv-train\Scripts\python.exe `
  G:\FPGA\ir_zynq_detector\pc\scripts\export_depthwise_full_channel.py `
  --input-dir G:\FPGA\ir_zynq_detector\build\pl_layer_case_depthwise_formal `
  --output-dir G:\FPGA\ir_zynq_detector\build\pl_depthwise_full_channel_formal `
  --c-header-out G:\FPGA\ir_zynq_detector\zynq_ps\include\ir_pl_dw3x3_full_channel_data.h `
  --channel 11
```

Expected export summary:

```text
channel=11 shape=40x32 count=1280 first_acc=93502 last_acc=-18304 max_abs_quant_error=0.01435205
```

Run RTL simulation:

```powershell
F:\Xilinx\Vivado\2020.2\bin\xvlog.bat --sv `
  G:\FPGA\ir_zynq_detector\zynq_pl\rtl\mobilenet_dw3x3_channel_full_mmio.sv `
  G:\FPGA\ir_zynq_detector\zynq_pl\rtl\mobilenet_dw3x3_channel_full_axi.v `
  G:\FPGA\ir_zynq_detector\zynq_pl\rtl\mobilenet_dw3x3_channel_full_axi.sv `
  G:\FPGA\ir_zynq_detector\zynq_pl\tb\mobilenet_dw3x3_channel_full_axi_tb.sv

F:\Xilinx\Vivado\2020.2\bin\xelab.bat mobilenet_dw3x3_channel_full_axi_tb -s mobilenet_dw3x3_channel_full_axi_tb_sim
F:\Xilinx\Vivado\2020.2\bin\xsim.bat mobilenet_dw3x3_channel_full_axi_tb_sim -runall
```

Expected simulation result:

```text
PASS full-channel axi outputs=16
mobilenet_dw3x3_channel_full_axi_tb PASS
```

Build Vivado bitstream:

```powershell
cd /d G:\FPGA\ir_zynq_detector
F:\Xilinx\Vivado\2020.2\bin\vivado.bat -mode batch -source hw\vivado\build_bitstream.tcl
```

Current verified result:

- bitstream generated successfully
- routed timing passes at 50 MHz
- WNS `5.079 ns`, TNS `0.000 ns`
- bitstream path: `build/vivado/ir_zynq_detector.runs/impl_1/system_wrapper.bit`
- exported XSA path: `build/vivado/export/ir_zynq_detector.xsa`
- routed DRC has no BRAM async-control warnings; remaining warnings are DSP pipeline suggestions

Current utilization note:

- Slice LUTs: about `4.81%`
- Slice Registers: about `3.29%`
- DSPs: `4`
- Block RAM Tile: `3`

The full scheduler now uses BRAM-backed feature/output storage. This is a much
better Zynq-7020 fit than the earlier register-buffer build.

## Build Vitis Selftest

```powershell
cd /d G:\FPGA\ir_zynq_detector
F:\Xilinx\Vitis\2020.2\bin\xsct.bat vitis\create_dw3x3_selftest_app.tcl
```

Expected build artifact:

```text
build/vitis_dw3x3_selftest/irdet_dw3x3_selftest/Debug/irdet_dw3x3_selftest.elf
```

The selftest workspace script now deletes the generated workspace before
rebuilding, which avoids stale Vitis 2020.2 metadata problems on Windows.

The latest selftest and UART apps have both been rebuilt against the final XSA.

## Run On Board

Open the UART terminal at:

- baud: `921600`
- data bits: `8`
- stop bits: `1`
- parity: none

Then download bitstream and ELF:

```powershell
cd /d G:\FPGA\ir_zynq_detector
F:\Xilinx\Vitis\2020.2\bin\xsct.bat vitis\run_dw3x3_selftest_on_board.tcl
```

The XSCT download flow should end with:

```text
INFO: Bitstream programmed: G:/FPGA/ir_zynq_detector/build/vivado/ir_zynq_detector.runs/impl_1/system_wrapper.bit
INFO: ELF downloaded and CPU resumed.
```

Expected UART output should include the already verified single-window and
PS-scheduled channel checks, plus the new full scheduler check:

```text
PL dw3x3 selftest PASS base=0x43C00000 mode=single_window result=45
PL dw3x3 realcase PASS channel=11 y=19 x=7 expected_acc=-180792 pl_acc=-180792 scale=65536
PL dw3x3 batch PASS channel=11 count=16 first_acc=11848 last_acc=26589 scale=65536
PL dw3x3 channel PASS channel=11 count=1280 first_acc=93502 last_acc=-18304 scale=65536
PL dw3x3 full scheduler PASS channel=11 count=1280 first_acc=93502 last_acc=-18304
PL dw3x3 selftest rc=0
```

Verified board UART output:

```text
PL dw3x3 batch PASS channel=11 count=16 first_acc=11848 last_acc=26589 scale=65536 cpu_us=7 pl_us=178 pl_per_window_us_x1000=11125
PL dw3x3 channel PASS channel=11 count=1280 first_acc=93502 last_acc=-18304 scale=65536 cpu_us=553 pl_us=13489 pl_per_window_us_x1000=10538
PL dw3x3 full scheduler present at 0x43C10000 info=0xF3282006
PL dw3x3 full scheduler PASS channel=11 count=1280 first_acc=93502 last_acc=-18304 e2e_us=3020 compute_us=692 e2e_per_output_us_x1000=2359
PL dw3x3 selftest rc=0
```

If XSCT prints no APU/PS7 target, the board app has not run yet. Check:

- board power
- JTAG cable
- USB driver
- boot/config jumpers
- stale `hw_server`

Then rerun:

```powershell
F:\Xilinx\Vitis\2020.2\bin\xsct.bat G:\FPGA\ir_zynq_detector\vitis\probe_jtag_targets.tcl
```

## Acceptance Criteria

This stage is accepted when the board UART shows:

- `PL dw3x3 full scheduler PASS`
- `count=1280`
- `first_acc=93502`
- `last_acc=-18304`
- `PL dw3x3 selftest rc=0`

Timing should be compared against the earlier PS-scheduled AXI-Lite replay:

- previous PS-scheduled full-channel replay: `13489 us`
- full scheduler end-to-end time: `3020 us`
- full scheduler compute time: `692 us`
- end-to-end improvement over the PS-scheduled PL replay: about `4.47x`
- compute-only improvement over the PS-scheduled PL replay: about `19.5x`

This result proves that moving the window loop into PL removes most of the
per-window PS/PL control overhead. The current demo still uses AXI-Lite buffer
load/readback, so it should be presented as an operator-level scheduler
acceleration milestone, not as the final whole-network acceleration result.

## Fixed-v2 Real-Layer Follow-Up

After the first formal full-scheduler milestone above, the project moved to the
fixed-v2 detector contract where the target MobileNetV2 depthwise layer exports
as `H=32, W=40`.

That exposed a real integration issue:

- the original full-scheduler RTL defaulted to `MAX_H=40, MAX_W=32`
- the fixed-v2 exported real layer needed `MAX_H=32, MAX_W=40`
- the PL start condition therefore stayed idle for the real layer case even
  though the earlier `32x40` validation case still passed

The RTL defaults have now been updated in:

- `zynq_pl/rtl/mobilenet_dw3x3_channel_full_mmio.sv`
- `zynq_pl/rtl/mobilenet_dw3x3_channel_full_axi.sv`
- `zynq_pl/rtl/mobilenet_dw3x3_channel_full_axi.v`

Current rebuilt local bitstream result:

- local build path: `build/vivado/ir_zynq_detector.runs/impl_1/system_wrapper.bit`
- routed timing still passes
- post-change full-scheduler info register on board: `0xF3202806`

Verified Linux detector replay with the real fixed-v2 layer:

```text
pl_real_layer rc=0 base=0x43c10000 channel=11 shape=40x32 count=1280 frac_bits=8 bias_q=11067 first_acc=30834 last_acc=-4821 max_abs_float_err=1.211182 status_before=0x0000000a status_after_start=0x00000004 status_after_wait=0x0000000a e2e_us=2234 compute_us=347
```

This is the current strongest PL result in the project:

- the PL full-scheduler is no longer only replaying the old formal case
- it now accepts the real fixed-v2 exported MobileNetV2 layer geometry
- the Linux detector app can call that PL path and still finish inference on the
  same board run
