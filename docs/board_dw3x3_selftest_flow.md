# Board DW3X3 Selftest Flow

## Goal

This flow verifies the hardware path:

- PS bare-metal software
- `M_AXI_GP0`
- AXI protocol converter
- custom `dw3x3` AXI slave in PL

before returning to the UART image receiver application.

## What This Flow Uses

Hardware:

- `hw/vivado/build_bitstream.tcl`

Board-side selftest app:

- `vitis/create_dw3x3_selftest_app.tcl`
- `vitis/run_dw3x3_selftest_on_board.tcl`

Board app entry:

- `zynq_ps/src/dw3x3_selftest_baremetal.c`

## Step 1. Build the bitstream

```powershell
F:\Xilinx\Vivado\2020.2\bin\vivado.bat `
  -mode batch `
  -source G:\FPGA\ir_zynq_detector\hw\vivado\build_bitstream.tcl
```

Expected result:

- `build/vivado/ir_zynq_detector.runs/impl_1/system_wrapper.bit`
- updated `build/vivado/export/ir_zynq_detector.xsa`

## Step 2. Build the standalone selftest app

```powershell
F:\Xilinx\Vitis\2020.2\bin\xsct.bat `
  G:\FPGA\ir_zynq_detector\vitis\create_dw3x3_selftest_app.tcl
```

Expected result:

- `build/vitis_dw3x3_selftest/irdet_dw3x3_selftest/Debug/irdet_dw3x3_selftest.elf`

## Step 3. Program the board and run the selftest app

```powershell
F:\Xilinx\Vitis\2020.2\bin\xsct.bat `
  G:\FPGA\ir_zynq_detector\vitis\run_dw3x3_selftest_on_board.tcl
```

This script:

- connects to `hw_server`
- applies PS init
- programs the bitstream
- applies PS post-config after PL configuration
- downloads the selftest ELF
- starts the CPU

## Expected UART Output

At `921600` baud, you should see lines similar to:

```text
IR detector PL dw3x3 bare-metal selftest
This app assumes the PL bitstream is already programmed.
PL dw3x3 accelerator present at 0x43C00000.
PL dw3x3 starting AXI MMIO single-window test...
AXI GPIO probe base=0x41200000 writing TRI...
AXI GPIO probe writing DATA=0xA5A55A5A...
AXI GPIO probe reading DATA...
AXI GPIO probe readback=0xA5A55A5A
PL dw3x3 reading INFO register...
PL dw3x3 info=0xD3030302
PL dw3x3 configure window...
PL dw3x3 write pixels...
PL dw3x3 write weights...
PL dw3x3 start core...
PL dw3x3 wait done...
PL dw3x3 read output...
PL dw3x3 selftest PASS base=0x43C00000 mode=single_window result=45
PL dw3x3 starting real MobileNetV2 window replay channel=11 y=19 x=7...
PL dw3x3 realcase PASS channel=11 y=19 x=7 expected_acc=-180792 pl_acc=-180792 scale=65536
PL dw3x3 starting real MobileNetV2 batch replay channel=11 count=16 patch=4x4...
PL dw3x3 batch PASS channel=11 count=16 first_acc=11848 last_acc=26589 scale=65536 cpu_us=7 pl_us=178 pl_per_window_us_x1000=11125
PL dw3x3 starting real MobileNetV2 channel replay channel=11 count=1280 patch=40x32...
PL dw3x3 channel PASS channel=11 count=1280 first_acc=93502 last_acc=-18304 scale=65536 cpu_us=553 pl_us=13489 pl_per_window_us_x1000=10538
PL dw3x3 full scheduler present at 0x43C10000 info=0xF3282006
PL dw3x3 starting full-channel scheduler channel=11 count=1280 shape=40x32...
PL dw3x3 full scheduler PASS channel=11 count=1280 first_acc=93502 last_acc=-18304 e2e_us=3020 compute_us=692 e2e_per_output_us_x1000=2359
PL dw3x3 selftest rc=0
```

## Verified Board Result

On the Zynq-7020 board, the selftest has passed with:

- `AXI GPIO` readback: `0xA5A55A5A`
- `dw3x3` info register: `0xD3030302`
- `dw3x3` result: `45`

This proves that PS `M_AXI_GP0`, the PL interconnect, the AXI GPIO probe,
and the custom `dw3x3` AXI-Lite accelerator are reachable from bare-metal PS code.

The updated selftest also replays one real quantized MobileNetV2 depthwise
window exported from the trained SSDLite model:

- channel: `11`
- y: `19`
- x: `7`
- expected fixed-point accumulator: `-180792`
- accumulator scale: `65536`

The next updated selftest also runs a small PS-managed sliding-window batch:

- channel: `11`
- patch: `4x4`
- windows: `16`
- first accumulator: `11848`
- last accumulator: `26589`

The latest build expands this to one complete exported channel:

- channel: `11`
- patch: `40x32`
- windows: `1280`
- first accumulator: `93502`
- last accumulator: `-18304`
- CPU reference time: `553 us`
- old PS-scheduled PL replay time: `13489 us`
- old PL average replay time: `10.538 us/window`

The latest full-channel scheduler moves the `40x32` sliding-window loop into PL:

- full scheduler base address: `0x43C10000`
- full scheduler end-to-end time: `3020 us`
- full scheduler compute time: `692 us`
- full scheduler average time: `2.359 us/output`
- end-to-end speedup over the old PS-scheduled PL replay: about `4.47x`

## If It Fails

### If XSCT says bitstream not found

- run the bitstream build step first

### If UART prints only the banner and then hangs

- likely the PL bitstream was not programmed correctly
- or the board is not running the updated hardware platform
- confirm the run script applies `ps7_init`, then programs PL, then applies `ps7_post_config`

### If UART hangs at the AXI GPIO probe

- the issue is below the custom `dw3x3` IP
- check PS `M_AXI_GP0`, FCLK0, PL reset, and run-script initialization order

### If the selftest reports a timeout

- check that the accelerator is present in hardware
- confirm the generated `xparameters.h` contains:
  - `XPAR_DW3X3_ACCEL_0_BASEADDR 0x43C00000`

### If the selftest reports a mismatch

- PS can already reach the PL block
- the issue is likely inside the `3x3` datapath or result readback logic

## After This Passes

Once this selftest passes on real hardware, the next step is:

- return to the UART image receiver app
- keep the PL block in hardware
- keep the board-proven full scheduler as the PL acceleration demo milestone
- move the next performance prototype toward AXI DMA / AXI-Stream transfer
- continue the PS-side real inference/postprocess integration in parallel
