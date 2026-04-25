# Zynq Linux Runtime Workspace

This directory now contains the first `ncnn` Linux user-space detector
application skeleton.

Current project split:

- `zynq_ps/`: bare-metal UART, preprocessing, SSD postprocess, PL selftest demos
- `zynq_pl/`: RTL and simulation for PL acceleration modules
- `zynq_linux/`: Linux user-space detector app, Linux PL MMIO tool, and cross-build scaffolding

## Current Goal

The current Linux app target is:

```text
gray8/raw tensor -> preprocess -> ncnn -> SSD postprocess -> stdout/UART log
```

This is the realistic next step toward board-side true inference. It is separate
from the existing bare-metal UART demo path.

## Main Files

- `include/irdet_linux_ncnn_detector.h`
- `src/irdet_linux_ncnn_detector.cpp`
- `src/irdet_linux_main.cpp`
- `src/irdet_linux_pl_dw3x3_tool.cpp`
- `CMakeLists.txt`
- `cmake/toolchains/vitis_aarch32_linux.cmake`

The app reuses these already-verified PS-side modules:

- `zynq_ps/src/ir_image_preprocess.c`
- `zynq_ps/src/ir_ssd_postprocess.c`

So the Linux route does not reimplement SSD decode/NMS again from scratch.

## Current Verified Host Demo

The Windows host can already verify the Linux app logic end-to-end with the
current fixed-v2 runtime contract.

Export assets + build + run host demo:

```powershell
powershell -ExecutionPolicy Bypass `
  -File G:\FPGA\ir_zynq_detector\pc\scripts\run_linux_ncnn_host_demo.ps1
```

Verified result on 2026-04-23:

```text
Model backend=ncnn runtime_in=160x128 anchors=660 score_thresh=200 mean=0.5 std=0.5
pre_in=640x512 pre_out=160x128 min=17 max=251 mean_x1000=-212
det_count=2
det0 class=car score=0.718 bbox=[140,220,193,254]
det1 class=car score=0.551 bbox=[235,195,337,297]
```

This proves the current user-space app structure works with:

- raw gray8 source input
- preprocessing in C
- `ncnn` runtime inference
- reused C SSD postprocess

## Linux PL Validation Tool

The Linux workspace now also contains a user-space `/dev/mem` tool that reuses
the validated bare-metal PL register drivers:

- `zynq_ps/src/ir_pl_dw3x3.c`
- `zynq_ps/src/ir_pl_dw3x3_full.c`
- `zynq_ps/include/ir_pl_dw3x3_realcase_data.h`
- `zynq_ps/include/ir_pl_dw3x3_realcase_batch_data.h`
- `zynq_ps/include/ir_pl_dw3x3_realcase_channel_data.h`
- `zynq_ps/include/ir_pl_dw3x3_full_channel_data.h`

The generated ARM executable is:

```text
G:\FPGA\ir_zynq_detector\build\zynq_linux_arm_ncnn\irdet_linux_pl_dw3x3_tool
```

Its default job is to replay the same validated checks that already passed on
bare metal:

- AXI MMIO single-window check
- one real MobileNetV2 depthwise 3x3 window
- a `4x4` batch replay on one channel
- a full `40x32` same-channel replay
- full scheduler replay through the PL full-channel block

Bundled board-side command:

```sh
./run_pl_selftest.sh
```

The packaged Linux selftest currently skips the optional AXI GPIO probe by
default, because an absent or undecoded GPIO slave would raise a Linux
`Bus error` when touched through `/dev/mem`. The actual `dw3x3` MMIO and full
scheduler validation still run.

Expected output pattern:

```text
IR detector Linux PL dw3x3 tool
PL dw3x3 selftest PASS ...
PL dw3x3 realcase PASS ...
PL dw3x3 batch PASS ...
PL dw3x3 channel PASS ...
PL dw3x3 full scheduler PASS ...
PL dw3x3 linux tool rc=0
```

## Runtime Contract Used By This App

This app now follows the fixed deployment contract:

- runtime tensor: `1x1x128x160`
- runtime width: `160`
- runtime height: `128`
- normalization: `(gray8 / 255.0 - 0.5) / 0.5`
- outputs: `bbox_regression`, `cls_logits`
- anchors: loaded from external `anchors_xyxy_f32.bin`

This contract now matches the fixed-v2 training/export path and the deployment
contract checker.

## Cross-Compile Direction

The PC can remain Windows. Vitis 2020.2 already includes an ARM Linux compiler:

```text
F:\Xilinx\Vitis\2020.2\gnu\aarch32\nt\gcc-arm-linux-gnueabi\bin\arm-linux-gnueabihf-g++.exe
```

The toolchain file in this directory is prepared for that next step:

```text
G:\FPGA\ir_zynq_detector\zynq_linux\cmake\toolchains\vitis_aarch32_linux.cmake
```

Cross-build scripts:

```text
G:\FPGA\ir_zynq_detector\pc\scripts\build_ncnn_arm_linux_min.ps1
G:\FPGA\ir_zynq_detector\pc\scripts\build_zynq_linux_arm_ncnn.ps1
```

Verified ARM build artifacts on 2026-04-23:

```text
G:\FPGA\ir_zynq_detector\build\ncnn_arm_linux_min\src\libncnn.a
G:\FPGA\ir_zynq_detector\build\zynq_linux_arm_ncnn\irdet_linux_ncnn_app
G:\FPGA\ir_zynq_detector\build\zynq_linux_arm_ncnn\irdet_linux_pl_dw3x3_tool
```

The detector executable has been checked with `readelf`:

```text
Class: ELF32
Machine: ARM
Flags: hard-float ABI
```

What is still missing for the real board Linux demo:

- a Linux image on the board
- model/app/assets deployment onto the board filesystem
- the first on-board run and serial/network log capture

## Current AC880 Board Status

The AC880 factory Linux image on the tested board already boots into a root
shell over the PS UART at `115200`, and the vendor documentation states the
default login is:

```text
user: root
pass: root
```

The tested factory image is intentionally small and only exposes `glibc 2.25`,
so the first ARM app build from the Vitis 2020.2 toolchain will not run if you
copy only `irdet_linux_ncnn_app` by itself. The verified workaround is now part
of the packaged demo bundle:

- bundle directory: `build/zynq_linux_demo_bundle`
- bundled ARM runtime loader: `lib/ld-linux-armhf.so.3`
- bundled runtime libs: `lib/libc.so.6`, `lib/libm.so.6`, `lib/libstdc++.so.6`, etc.

The packaged ARM executables are now patched so their ELF interpreter and
RUNPATH resolve against `/home/root/irdet_demo/lib`. The generated board-side
scripts can therefore launch `./app/irdet_linux_ncnn_app` directly while still
avoiding the factory-rootfs `glibc` mismatch.

## One-Command AC880 Deploy

On the Windows PC, after the board is reachable over Ethernet and SSH:

```powershell
powershell -ExecutionPolicy Bypass `
  -File G:\FPGA\ir_zynq_detector\pc\scripts\run_ac880_linux_demo.ps1 `
  -BoardHost auto `
  -User root `
  -Password root `
  -Mode gray8
```

This now performs the whole deployment path:

- rebuild/package the Linux demo bundle
- copy the bundle onto `/home/root/irdet_demo`
- upload the matching ARM runtime libs
- run the detector on the sample `gray8` image

For the Linux-side PL validation path, use:

```powershell
powershell -ExecutionPolicy Bypass `
  -File G:\FPGA\ir_zynq_detector\pc\scripts\run_ac880_linux_demo.ps1 `
  -BoardHost auto `
  -User root `
  -Password root `
  -Mode pl_selftest
```

If SSH is temporarily unavailable but the PS UART Linux shell is still alive on
`COM3 @ 115200`, there is now a serial fallback path:

```powershell
powershell -ExecutionPolicy Bypass `
  -File G:\FPGA\ir_zynq_detector\pc\scripts\run_ac880_linux_serial_demo.ps1 `
  -RepoRoot G:\FPGA\ir_zynq_detector `
  -ComPort COM3 `
  -Mode gray8
```

For the Linux-side PL validation with a fresh JTAG bitstream download first:

```powershell
powershell -ExecutionPolicy Bypass `
  -File G:\FPGA\ir_zynq_detector\pc\scripts\run_ac880_linux_serial_demo.ps1 `
  -RepoRoot G:\FPGA\ir_zynq_detector `
  -ComPort COM3 `
  -Mode pl_selftest `
  -ProgramPl
```

For the one-command board demo path, use:

```powershell
powershell -ExecutionPolicy Bypass `
  -File G:\FPGA\ir_zynq_detector\pc\scripts\run_ac880_linux_serial_demo.ps1 `
  -RepoRoot G:\FPGA\ir_zynq_detector `
  -ComPort COM3 `
  -Mode full_demo `
  -ProgramPl
```

This runs, in order:

- JTAG-only PL bitstream programming
- Linux-side `dw3x3` and full-scheduler validation
- Linux-side `ncnn` detector on the bundled `gray8` sample

The `-ProgramPl` option wraps:

```powershell
powershell -ExecutionPolicy Bypass `
  -File G:\FPGA\ir_zynq_detector\pc\scripts\program_ac880_pl_only.ps1
```

which only programs `system_wrapper.bit` over JTAG and does not reset Linux or
download a bare-metal ELF.

Verified on the AC880 factory Linux board:

```text
Model backend=ncnn runtime_in=160x128 anchors=660 score_thresh=200 mean=0.5 std=0.5
pre_in=640x512 pre_out=160x128 min=17 max=251 mean_x1000=-212
det_count=2
det0 class=car score=0.718 bbox=[140,220,193,254]
det1 class=car score=0.551 bbox=[235,195,337,297]
```

Verified Linux PL validation on the AC880 factory Linux board after JTAG-only
bitstream programming:

```text
IR detector Linux PL dw3x3 tool
PL dw3x3 info=0xd3030302
PL dw3x3 selftest PASS base=0x43c00000 mode=single_window result=45
PL dw3x3 realcase PASS channel=11 y=19 x=7 expected_acc=-180792 pl_acc=-180792 scale=65536
PL dw3x3 batch PASS channel=11 count=16 first_acc=11848 last_acc=26589 scale=65536
PL dw3x3 channel PASS channel=11 count=1280 first_acc=93502 last_acc=-18304 scale=65536
PL dw3x3 full scheduler PASS channel=11 count=1280 first_acc=93502 last_acc=-18304
PL dw3x3 linux tool rc=0
```

## PC-Select / Board-Infer Flow

The next validated step is no longer limited to the one bundled sample file.
The PC can now:

- pick a FLIR image from the dataset
- decode it into `GRAY8`
- upload the raw bytes to the board over SSH/SFTP
- trigger the board-side detector on that uploaded frame

One-command example:

```powershell
powershell -ExecutionPolicy Bypass `
  -File G:\FPGA\ir_zynq_detector\pc\scripts\run_ac880_linux_image_infer.ps1 `
  -BoardHost 169.254.132.113 `
  -User root `
  -Password root `
  -DatasetRoot "G:\chormxiazai\FLIR_ADAS_v2" `
  -Match "images_thermal_val\data" `
  -Index 0
```

With local result files:

```powershell
powershell -ExecutionPolicy Bypass `
  -File G:\FPGA\ir_zynq_detector\pc\scripts\run_ac880_linux_image_infer.ps1 `
  -BoardHost 169.254.132.113 `
  -User root `
  -Password root `
  -DatasetRoot "G:\chormxiazai\FLIR_ADAS_v2" `
  -Match "images_thermal_val\data" `
  -Index 0 `
  -ResultJson "G:\FPGA\ir_zynq_detector\build\board_infer\result.json" `
  -AnnotatedOut "G:\FPGA\ir_zynq_detector\build\board_infer\annotated.png" `
  -WithGt
```

Expected output shape:

```text
Selected dataset image index=0 out_of=...
Decoded image=... width=640 height=512 payload=327680 checksum=...
Model backend=ncnn runtime_in=160x128 ...
pre_in=640x512 pre_out=160x128 ...
det_count=2
det0 class=car score=...
```

## Fixed-v2 PL Real-Layer Replay

The Linux detector can now call the PL full-scheduler on a real exported
fixed-v2 MobileNetV2 depthwise layer case:

```powershell
powershell -ExecutionPolicy Bypass `
  -File G:\FPGA\ir_zynq_detector\pc\scripts\run_ac880_linux_serial_demo.ps1 `
  -RepoRoot G:\FPGA\ir_zynq_detector `
  -ComPort COM3 `
  -Mode gray8_pl_real_layer
```

Verified board output on 2026-04-24:

```text
Model backend=ncnn runtime_in=160x128 anchors=660 score_thresh=200 mean=0.5 std=0.5
Runtime contract nchw=1x1x128x160 width=160 height=128
pl_real_layer rc=0 base=0x43c10000 channel=11 shape=40x32 count=1280 frac_bits=8 bias_q=11067 first_acc=30834 last_acc=-4821 max_abs_float_err=1.211182 status_before=0x0000000a status_after_start=0x00000004 status_after_wait=0x0000000a e2e_us=2234 compute_us=347
pre_in=640x512 pre_out=160x128 min=20 max=240 mean_x1000=-211
det_count=4
det0 class=car score=0.508 bbox=[231,214,334,297]
...
```

This is the first verified board run where:

- Linux `ncnn` inference still completes
- the detector app invokes the PL full-scheduler on a real exported layer case
- PL returns the expected fixed-v2 first/last accumulators

## Serial Update Fallback

When SSH upload is unavailable, the project now has a serial-only file update
path:

- `pc/scripts/upload_file_over_serial.py`
- `pc/scripts/deploy_ac880_real_layer_update_over_serial.ps1`

The uploader hex-encodes a local file, streams it over `COM3`, reconstructs it
on the AC880 Linux shell, and verifies the remote SHA-256.

## Temporary U-Boot Wrapper

`pc/scripts/run_ac880_temp_uboot_demo.ps1` now performs:

1. temporary U-Boot boot with the IR DTB
2. JTAG programming of the current local `system_wrapper.bit`
3. Linux serial demo execution

This matches the current project decision to avoid persistent boot-partition
changes while still ensuring the board runs the latest local PL bitstream.
