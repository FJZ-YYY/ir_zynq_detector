# AC880 PC Visual Demo

This demo adds a PC-side image selection and visualization flow on top of the
already verified board runtime path:

```text
PC image -> GRAY8 raw -> SSH/SFTP upload -> AC880 Linux detector ->
parse det_count / detN -> draw bbox on PC -> save result image
```

The board-side detector app already supports custom input files through:

```text
--gray8 <path> --src-width <w> --src-height <h>
```

So this visual demo does not change the current inference contract, does not
touch `inpath_dw_pl_full` core logic, and does not modify the PL RTL.

## Supported Modes

- `gray8`
- `inpath_dw_cpu_full`
- `inpath_dw_pl_full`

Default mode for the new demo is:

```text
inpath_dw_pl_full
```

## Command Line Demo

Script:

```text
G:\FPGA\ir_zynq_detector\pc\tools\board_visual_infer.py
```

Example with one fixed image:

```powershell
python G:\FPGA\ir_zynq_detector\pc\tools\board_visual_infer.py `
  --image "G:\chormxiazai\FLIR_ADAS_v2\images_thermal_val\data\video-10-frame-00116.png" `
  --mode inpath_dw_pl_full
```

After a board power cycle, you can recover the current PL bitstream first:

```powershell
python G:\FPGA\ir_zynq_detector\pc\tools\board_visual_infer.py `
  --image "G:\path\to\thermal.png" `
  --mode inpath_dw_pl_full `
  --recover-pl
```

Example with dataset selection:

```powershell
python G:\FPGA\ir_zynq_detector\pc\tools\board_visual_infer.py `
  --dataset-root "G:\chormxiazai\FLIR_ADAS_v2" `
  --match "images_thermal_val\data" `
  --index 0 `
  --mode inpath_dw_pl_full
```

Optional first-run bundle refresh:

```powershell
python G:\FPGA\ir_zynq_detector\pc\tools\board_visual_infer.py `
  --image "G:\path\to\thermal.png" `
  --mode inpath_dw_pl_full `
  --refresh-bundle
```

The script will:

- decode the selected image to `GRAY8`
- upload the raw bytes to `/home/root/irdet_demo/data/board_vis/`
- invoke the board-side detector directly with the chosen mode
- parse `det_count` and `detN class=... score=... bbox=[...]`
- save results to `G:\FPGA\ir_zynq_detector\outputs\board_vis\`

Saved artifacts:

- `*.png`: annotated result image
- `*.json`: parsed result metadata
- `*.log`: full board stdout/stderr log

## GUI Demo

Script:

```text
G:\FPGA\ir_zynq_detector\pc\tools\board_visual_demo_gui.py
```

Launch:

```powershell
python G:\FPGA\ir_zynq_detector\pc\tools\board_visual_demo_gui.py
```

The GUI provides:

- `选择图片`
- `Recover PL`
- `运行板端推理`
- mode dropdown: `gray8 / inpath_dw_cpu_full / inpath_dw_pl_full`
- `Auto Recover PL`
- log window
- original image preview
- annotated result preview

The GUI imports and reuses the core inference logic from
`board_visual_infer.py`, so the upload, board execution, log parsing, and bbox
drawing logic stays in one place.

Power-cycle note:

- after a board power cycle, `gray8` and `inpath_dw_cpu_full` usually only need
  Linux + SSH to come back
- `inpath_dw_pl_full` usually needs the PL bitstream to be programmed again
- the GUI `Recover PL` button and the CLI `--recover-pl` flag both reuse
  `pc/scripts/program_ac880_pl_only.ps1`

## Expected Output Pattern

For `inpath_dw_pl_full`, the board log should still include lines such as:

```text
Runtime contract nchw=1x1x128x160 width=160 height=128
inpath_dw_pl_full rc=0
det_count=...
det0 class=car score=... bbox=[...]
```

This proves the saved PC visualization came from the real board inference path,
not from a PC-only mock detector.
