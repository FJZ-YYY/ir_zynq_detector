# AC880 Boot-Time PL Load Validation

## Goal

Move PL programming earlier than Linux user space on the AC880 board, while keeping the detector app and PL selftest runnable after boot.

## What We Found

1. The factory AC880 boot flow already loads a PL bitstream in U-Boot through `uEnv.txt`.
2. Simply swapping in our IR-detector bitstream is not enough.
3. The factory `system.dtb` still describes the vendor PL design, including `axi_vdma_0` and other nodes under `/amba_pl`.
4. If Linux boots with our bitstream and the old DTB, the kernel panics in `xilinx_dma_probe`.
5. A stripped DTB that removes the factory `/amba_pl` subtree allows Linux to boot cleanly with our bitstream.

## Files Added For This Flow

- `pc/scripts/make_ac880_ir_boot_dtb.py`
  - Builds a minimal `system_ir_boot.dtb` from the factory DTB.
- `pc/scripts/test_ac880_uboot_ir_boot.ps1`
  - Uses XSCT system reset + PS UART to:
    - stop autoboot
    - set temporary U-Boot env variables
    - boot with `system_wrapper.bit` + `system_ir_boot.dtb`
    - optionally run the Linux PL selftest after boot
- `pc/scripts/install_ac880_ir_boot_persistent.py`
  - Prepares a persistent boot configuration by backing up the current boot files and patching `uEnv.txt`.
  - Use `--dry-run` first.

## Generated Artifacts

- `build/ac880_uboot_pl_preload/factory_system.dtb`
- `build/ac880_uboot_pl_preload/system_ir_boot.dtb`
- `build/ac880_uboot_pl_preload/system_ir_boot.dts`
- `build/ac880_uboot_pl_preload/uboot_ir_boot_*.log`

## Validated Result

The following sequence now works:

1. XSCT system reset
2. Stop U-Boot autoboot
3. Set:
   - `bitstream_image=system_wrapper.bit`
   - `bitstream_size=0x3DBB6A`
   - `devicetree_image=system_ir_boot.dtb`
4. `run sdboot`
5. Linux boots successfully
6. Linux user-space PL selftest passes
7. Linux `ncnn` detector app still runs

## Important Note

The current automation uses XSCT reset instead of Linux `reboot`, because the factory image can crash on shutdown in an audio-codec path. This does not block the detector workflow, but it means board-reset automation is more reliable through JTAG than through the Linux reboot path.

## Recommended Next Step

1. Decide whether to make the boot configuration persistent through `uEnv.txt`.
2. After boot-time PL load is fixed, start wiring the validated `dw3x3` accelerator into the real detector inference path instead of using it only through selftest tooling.
