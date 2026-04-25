# Board Bring-Up: UART Image Receiver

## This Step Goal

Bring up the first real board-side workflow:

1. Vivado creates a minimal Zynq PS hardware platform.
2. Vitis creates a bare-metal UART receiver application.
3. The board prints ready messages over UART.
4. The PC sends one decoded image frame.
5. The board prints width, height, payload bytes, and checksum status.

## Current Assumptions

- Host OS: Windows
- Vivado: `2020.2`
- Vitis: `2020.2`
- Device: `xc7z020clg400-1`
- Board UART path: PS UART1 on `MIO 48..49`
- First-stage image transport: UART only

The PS preset is aligned with the AC880 bare-metal UART example available in the local board资料.

## Step 1: Create Vivado Hardware Platform

Run:

```powershell
cd G:\FPGA\ir_zynq_detector
F:\Xilinx\Vivado\2020.2\bin\vivado.bat -mode batch -source hw\vivado\create_project.tcl
```

Expected output:

- a Vivado project under `build\vivado`
- an exported XSA at `build\vivado\export\ir_zynq_detector.xsa`

If you want a bitstream too:

```powershell
$env:IRDET_BUILD_BITSTREAM='1'
F:\Xilinx\Vivado\2020.2\bin\vivado.bat -mode batch -source hw\vivado\create_project.tcl
```

## Step 2: Create Vitis Bare-Metal Application

Run:

```powershell
cd G:\FPGA\ir_zynq_detector
F:\Xilinx\Vitis\2020.2\bin\xsct.bat vitis\create_baremetal_app.tcl
```

Expected result:

- workspace under `build\vitis`
- platform project `irdet_platform`
- application project `irdet_uart_rx`

Main application files:

- `zynq_ps/src/uart_image_receiver_baremetal.c`
- `zynq_ps/src/uart_image_proto.c`
- `zynq_ps/include/uart_image_proto.h`

## Step 3: Download and Open UART

On your side:

1. Connect JTAG and USB-UART.
2. Power on the board.
3. Use Vitis or XSCT to program the board and run the ELF.
4. Open the UART terminal at `921600`.

Expected startup text:

```text
IR detector UART image receiver ready.
Waiting for IRDT frame...
```

If you prefer XSCT instead of clicking in Vitis:

```powershell
F:\Xilinx\Vitis\2020.2\bin\xsct.bat vitis\run_uart_rx_on_board.tcl
```

This script prints the detected target list before it tries to select the A9 core.

## Step 4: Send One Image from the PC

Run:

```powershell
python pc\tools\send_uart_image.py --image path\to\test.png --port COMx --baud 921600 --wait-ack
```

Expected board text:

```text
frame_id=1 width=320 height=256 payload=81920 checksum_rx=0x0043B9D6 checksum_calc=0x0043B9D6 RX_OK
```

## If Something Fails

Please send back one of these:

- full Vivado batch log
- XSCT or Vitis build error
- UART terminal output
- screenshot of Vitis hardware target or debug launch failure

That is enough for the next round of fixes.
