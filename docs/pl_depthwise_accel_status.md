# PL Depthwise Acceleration Status

## Goal

This project does not attempt to rewrite the whole detector in HDL.
The current PL target is a realistic operator-level acceleration path for
the `MobileNetV2 depthwise 3x3` layer used by the SSDLite detector.

The purpose of this stage is to prove:

- the trained model can provide a real target layer for PL validation
- PS and PL can share a clear tensor contract
- the chosen depthwise operator can be verified first as a kernel, then as a board-fit single-window accelerator

## Current Verified Milestones

### 1. PC-side real layer export is ready

The trained SSDLite + MobileNetV2 model exports a representative depthwise layer:

- layer name: `backbone.features.0.3.conv.1.0`
- fused weights and bias are already generated
- golden outputs before and after ReLU6 are available

Key artifact directory:

- `build/pl_layer_case_depthwise_formal/`

Important files:

- `layer_input.npy`
- `weight_fused.npy`
- `bias_fused.npy`
- `golden_bn_out.npy`
- `golden_relu6_out.npy`
- `layer_manifest.json`

### 2. PL single-window MAC kernel is verified

RTL:

- `zynq_pl/rtl/mobilenet_dw3x3_accel.sv`

Synthetic testbench:

- `zynq_pl/tb/mobilenet_dw3x3_accel_tb.sv`

Result:

- Vivado 2020.2 `xsim` pass
- arithmetic checks passed for signed MAC plus bias

### 3. Real model window test is verified

Quantized real-case exporter:

- `pc/scripts/export_depthwise_window_case.py`

Generated artifacts:

- `build/pl_depthwise_window_case_formal/depthwise_window_case.json`
- `build/pl_depthwise_window_case_formal/depthwise_window_case.svh`

Real-case testbench:

- `zynq_pl/tb/mobilenet_dw3x3_accel_realcase_tb.sv`

Result:

- Vivado 2020.2 `xsim` pass
- one real quantized window from the trained model was replayed in RTL
- current selected case:
  - channel `11`
  - y `19`
  - x `7`
- current quantized output check:
  - golden float `-2.75125146`
  - quantized replay `-2.75866699`
  - quantization error about `0.0074`

### 4. Board-fit single-window core is verified

RTL:

- `zynq_pl/rtl/mobilenet_dw3x3_channel_core.sv`

Testbench:

- `zynq_pl/tb/mobilenet_dw3x3_channel_core_tb.sv`

Current scope:

- loads one 3x3 input window
- loads one 3x3 weight set and one bias
- computes one signed depthwise output
- uses a time-multiplexed MAC so it fits Zynq-7020 comfortably

Result:

- Vivado 2020.2 `xsim` pass
- verified on a `3x3` example window with all-one weights

### 5. MMIO wrapper and PS-visible contract are verified

Wrapper RTL:

- `zynq_pl/rtl/mobilenet_dw3x3_channel_mmio.sv`

RTL testbench:

- `zynq_pl/tb/mobilenet_dw3x3_channel_mmio_tb.sv`

PS-side driver:

- `zynq_ps/include/ir_pl_dw3x3.h`
- `zynq_ps/src/ir_pl_dw3x3.c`

PS-side host mock test:

- `zynq_ps/tests/ir_pl_dw3x3_mock_test.c`

Current verified flow:

- PS-style register writes configure `3x3` window mode and bias
- PS-style register writes load 9 window pixels
- PS-style register writes load the 3x3 weights
- PS starts the core by writing the control register
- PL wrapper stores one output result register
- PS reads back the single output value through the same register contract

Result:

- Vivado 2020.2 `xsim` pass for the MMIO wrapper testbench
- host-side C mock test pass for the PS driver logic

### 6. AXI-Lite wrapper is verified

AXI wrapper RTL:

- `zynq_pl/rtl/mobilenet_dw3x3_channel_axi.v`
- `zynq_pl/rtl/mobilenet_dw3x3_channel_axi.sv`

AXI wrapper testbench:

- `zynq_pl/tb/mobilenet_dw3x3_channel_axi_tb.sv`

Current verified flow:

- AXI write transactions configure the `3x3` window mode and bias
- AXI write transactions load 9 window pixels and 9 weights
- AXI start transaction kicks off the compute core
- AXI polling reads the done status
- AXI readback returns the single computed output

Result:

- Vivado 2020.2 `xsim` pass for the AXI wrapper

### 7. Vivado hardware platform integration is verified

Vivado scripts:

- `hw/vivado/create_project.tcl`
- `hw/vivado/bd/create_zynq_ps_uart_bd.tcl`

Current integrated hardware path:

- PS UART on MIO 48/49
- PS `M_AXI_GP0`
- AXI interconnect
- AXI GPIO debug probe
- AXI protocol converter
- custom `dw3x3` AXI slave
- synchronized reset generation with `proc_sys_reset`

Result:

- Vivado batch project creation pass
- bitstream generation pass on `xc7z020clg400-1`
- routed timing passes at the current `50 MHz` PS FCLK0 setting
- generated XSA includes the PL accelerator
- assigned base address:
  - `0x43C00000`
- AXI GPIO probe base address:
  - `0x41200000`

### 8. Board-side selftest passes on the real board

Files:

- `zynq_ps/include/ir_pl_dw3x3_selftest.h`
- `zynq_ps/include/ir_pl_dw3x3_realcase_data.h`
- `zynq_ps/include/ir_pl_dw3x3_realcase_batch_data.h`
- `zynq_ps/src/ir_pl_dw3x3_selftest.c`

Behavior:

- reports accelerator presence from `xparameters.h`
- provides a real PL smoke test routine using Xilinx MMIO access
- first probes an official Xilinx `AXI GPIO` register path
- then reads the custom `dw3x3` info register
- then writes one `3x3` pixel window, all-one weights, starts the core, polls done, and reads the result
- then replays one real quantized MobileNetV2 depthwise window exported from the trained model
- board-verified build also replays a `4x4` patch, so PS continuously schedules 16 real windows through PL
- latest build expands this to one full exported channel with `40x32=1280` windows and timing counters

Result:

- Vitis 2020.2 workspace/app rebuild pass with the new hardware platform
- real board UART output confirms:
  - `AXI GPIO` readback `0xA5A55A5A`
  - `dw3x3` info register `0xD3030302`
  - `dw3x3` result `45`
  - `PL dw3x3 selftest rc=0`
- updated expected real-case replay:
  - channel `11`, y `19`, x `7`
  - expected fixed-point accumulator `-180792`
  - accumulator scale `65536`
- updated batch replay is built and ready for board verification:
  - channel `11`
  - patch `4x4`, count `16`
  - first fixed-point accumulator `11848`
  - last fixed-point accumulator `26589`
- board UART output confirms `PL dw3x3 batch PASS`
- latest full-channel replay is built and ready for board verification:
  - channel `11`
  - patch `40x32`, count `1280`
  - first fixed-point accumulator `93502`
  - last fixed-point accumulator `-18304`
- board UART output confirms `PL dw3x3 channel PASS`
- measured full-channel timing:
  - CPU reference time `553 us`
  - PL AXI-Lite replay time `13489 us`
  - PL replay average `10.538 us/window`

Important bring-up lesson:

- PL access only worked reliably when the XSCT run script used this order:
  - system reset
  - `ps7_init`
  - program PL bitstream
  - `ps7_post_config`
  - download and run ELF
- Programming PL before PS init/post-config caused PS AXI writes to PL to hang.

### 9. UART image receiver now has a real PL operator probe

Files:

- `zynq_ps/src/uart_image_receiver_baremetal.c`
- `vitis/run_uart_rx_on_board.tcl`

Behavior:

- receives one decoded grayscale image frame over UART
- resizes/normalizes to `160x128`
- takes one `3x3` window from the preprocessed model input
- computes a CPU reference sum
- calls the PL `dw3x3` accelerator for the same window
- appends the result to the normal frame result line:
  - `pl_dw3x3_rc=0`
  - `cpu=<value>`
  - `pl=<value>`

The main UART run script now follows the same verified PS/PL initialization order as the selftest flow.

### 10. Full-channel PL scheduler is verified on the real board

Files:

- `zynq_pl/rtl/mobilenet_dw3x3_channel_full_mmio.sv`
- `zynq_pl/rtl/mobilenet_dw3x3_channel_full_axi.v`
- `zynq_pl/rtl/mobilenet_dw3x3_channel_full_axi.sv`
- `zynq_pl/tb/mobilenet_dw3x3_channel_full_axi_tb.sv`
- `zynq_ps/include/ir_pl_dw3x3_full.h`
- `zynq_ps/src/ir_pl_dw3x3_full.c`
- `zynq_ps/include/ir_pl_dw3x3_full_channel_data.h`

Behavior:

- PS writes a full `40x32` input feature channel into the accelerator register window
- PS writes one fused MobileNetV2 depthwise `3x3` kernel and bias
- PS writes one start command
- PL internally iterates all `1280` output windows
- PS reads the full output buffer and compares it with exported golden accumulators

Address map:

- old single-window accelerator: `0x43C00000`
- new full-channel scheduler: `0x43C10000`
- AXI GPIO debug probe: `0x41200000`

Current verified result:

- full-channel AXI RTL simulation pass
- Vivado project/XSA generation pass
- bitstream generation pass
- routed timing pass at 50 MHz
- Vitis selftest application rebuild pass
- Vitis UART image receiver application rebuild pass
- XSCT download flow reaches `ELF downloaded and CPU resumed`
- board-side UART confirms `PL dw3x3 full scheduler PASS`
- verified full scheduler result:
  - channel `11`
  - output count `1280`
  - first fixed-point accumulator `93502`
  - last fixed-point accumulator `-18304`
  - end-to-end time `3020 us`
  - compute time `692 us`
  - end-to-end average `2.359 us/output`
- measured improvement versus old PS-scheduled PL replay:
  - old replay time `13489 us`
  - full scheduler end-to-end speedup about `4.47x`
  - full scheduler compute-only speedup about `19.5x`

Resource note:

- this version is suitable for functional proof and resource discussion
- feature/output buffers now infer BRAM
- final routed utilization:
  - LUT about `4.81%`
  - registers about `3.29%`
  - BRAM tile `3`
  - DSP `4`
- final routed WNS is `5.079 ns` at 50 MHz

### 11. Linux runtime can now dump intermediate NCNN blobs

Files:

- `zynq_linux/include/irdet_linux_ncnn_detector.h`
- `zynq_linux/src/irdet_linux_ncnn_detector.cpp`
- `zynq_linux/src/irdet_linux_main.cpp`
- `pc/scripts/list_ncnn_depthwise_blobs.py`

Behavior:

- the Linux detector app can now extract an arbitrary named `ncnn` blob
- the blob is written as `float32` binary plus JSON shape metadata
- a PC-side helper can list all `ConvolutionDepthWise` blob names from the
  fixed-v2 `ncnn` param file

Result:

- the project now has a direct path to capture a real runtime feature tensor
  from the deployed detector graph
- this is the bridge from "offline replay validation" to "real inference-path
  PL call integration"

## PS-side Progress Related To Real Deployment

The PS side already has a real SSD raw-head postprocess path:

- `zynq_ps/include/ir_ssd_postprocess.h`
- `zynq_ps/src/ir_ssd_postprocess.c`
- `zynq_ps/tests/ir_ssd_postprocess_smoke.c`

What is already verified:

- decode SSD raw box regression
- class softmax
- class-wise NMS
- map model-space boxes back to source image space

## Why This PL Plan Is Reasonable

This path is intentionally incremental:

1. verify a 3x3 depthwise MAC kernel
2. verify the same kernel on real model-derived data
3. verify a board-fit single-window AXI accelerator
4. then move to PS-driven window replay, streaming, DMA, and larger operators

This is a better first version for Zynq-7020 than trying to hardware-map the entire detector at once.

## Next Recommended Steps

### Near-term

- keep the current AXI-Lite single-window design as the correctness baseline
- keep the full-channel scheduler as the current PL acceleration demo milestone
- use the timing result to justify moving from per-window AXI-Lite control toward batched PL execution
- pipeline the DSP datapath if we want to push FCLK beyond the current 50 MHz demo clock

### After that

- move from AXI-Lite memory-loaded validation to AXI-stream or AXI DMA controlled operation
- benchmark latency for one channel and estimate full-layer runtime
- decide whether to keep PL as operator accelerator only or to expand into a bottleneck-level accelerator

## Useful Commands

Generate the quantized real-case window:

```powershell
G:\FPGA\ir_zynq_detector\.venv-train\Scripts\python.exe `
  G:\FPGA\ir_zynq_detector\pc\scripts\export_depthwise_window_case.py `
  --input-dir G:\FPGA\ir_zynq_detector\build\pl_layer_case_depthwise_formal `
  --output-dir G:\FPGA\ir_zynq_detector\build\pl_depthwise_window_case_formal `
  --c-header-out G:\FPGA\ir_zynq_detector\zynq_ps\include\ir_pl_dw3x3_realcase_data.h
```

Generate the quantized `4x4` real-case batch:

```powershell
G:\FPGA\ir_zynq_detector\.venv-train\Scripts\python.exe `
  G:\FPGA\ir_zynq_detector\pc\scripts\export_depthwise_window_batch.py `
  --input-dir G:\FPGA\ir_zynq_detector\build\pl_layer_case_depthwise_formal `
  --output-dir G:\FPGA\ir_zynq_detector\build\pl_depthwise_window_batch_formal `
  --c-header-out G:\FPGA\ir_zynq_detector\zynq_ps\include\ir_pl_dw3x3_realcase_batch_data.h `
  --channel 11 `
  --start-y 18 `
  --start-x 6 `
  --patch-h 4 `
  --patch-w 4
```

Generate the full-channel replay dataset:

```powershell
G:\FPGA\ir_zynq_detector\.venv-train\Scripts\python.exe `
  G:\FPGA\ir_zynq_detector\pc\scripts\export_depthwise_window_batch.py `
  --input-dir G:\FPGA\ir_zynq_detector\build\pl_layer_case_depthwise_formal `
  --output-dir G:\FPGA\ir_zynq_detector\build\pl_depthwise_channel_replay_formal `
  --c-header-out G:\FPGA\ir_zynq_detector\zynq_ps\include\ir_pl_dw3x3_realcase_channel_data.h `
  --channel 11 `
  --start-y 0 `
  --start-x 0 `
  --patch-h 40 `
  --patch-w 32 `
  --symbol-prefix IRDET_DW3X3_CHANNEL `
  --description "Replays a full same-channel MobileNetV2 depthwise feature map on PL."
```

Run the real-case RTL simulation:

```powershell
F:\Xilinx\Vivado\2020.2\bin\xvlog.bat --sv `
  -i G:\FPGA\ir_zynq_detector\build\pl_depthwise_window_case_formal `
  G:\FPGA\ir_zynq_detector\zynq_pl\rtl\mobilenet_dw3x3_accel.sv `
  G:\FPGA\ir_zynq_detector\zynq_pl\tb\mobilenet_dw3x3_accel_realcase_tb.sv

F:\Xilinx\Vivado\2020.2\bin\xelab.bat mobilenet_dw3x3_accel_realcase_tb -s mobilenet_dw3x3_accel_realcase_tb_sim
F:\Xilinx\Vivado\2020.2\bin\xsim.bat mobilenet_dw3x3_accel_realcase_tb_sim -runall
```

Run the single-channel feature-map core simulation:

```powershell
F:\Xilinx\Vivado\2020.2\bin\xvlog.bat --sv `
  G:\FPGA\ir_zynq_detector\zynq_pl\rtl\mobilenet_dw3x3_channel_core.sv `
  G:\FPGA\ir_zynq_detector\zynq_pl\tb\mobilenet_dw3x3_channel_core_tb.sv

F:\Xilinx\Vivado\2020.2\bin\xelab.bat mobilenet_dw3x3_channel_core_tb -s mobilenet_dw3x3_channel_core_tb_sim
F:\Xilinx\Vivado\2020.2\bin\xsim.bat mobilenet_dw3x3_channel_core_tb_sim -runall
```
