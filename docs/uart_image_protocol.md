# UART Image Protocol

## This Step Goal

Use one simple and stable packet format to send one decoded grayscale image from the PC to the Zynq PS side over UART.

The first-stage target is only:

1. PC reads one image file and decodes it to grayscale pixels.
2. PC sends `header + payload` over UART.
3. PS receives one full frame.
4. PS prints width, height, payload size, and checksum.

The board does not parse `jpg/png` in v1.

## Payload Format

Transport format:

```text
| 32-byte fixed header | grayscale payload bytes |
```

Pixel format in v1:

- `GRAY8`
- 1 byte per pixel
- payload size must equal `width * height`

## Header Layout

Byte order is little-endian.

| Offset | Bytes | Field |
|--------|-------|-------|
| 0      | 4     | Magic = `"IRDT"` |
| 4      | 1     | Version = `1` |
| 5      | 1     | Pixel format = `1` for `GRAY8` |
| 6      | 2     | Flags, currently `0` |
| 8      | 4     | Frame ID |
| 12     | 2     | Width |
| 14     | 2     | Height |
| 16     | 4     | Payload bytes |
| 20     | 4     | Checksum32 |
| 24     | 4     | Reserved0 = `0` |
| 28     | 4     | Reserved1 = `0` |

Header size is always `32` bytes.

## Checksum Definition

`Checksum32` is the unsigned sum of all payload bytes modulo `2^32`.

This is not a strong CRC, but it is enough for first-stage UART bring-up:

- easy to implement on Python
- easy to implement on bare-metal C
- easy to print and compare during debugging

If we need stronger validation later, we can switch to CRC32 without changing the overall project structure.

## Recommended Limits

For the current board-side skeleton:

- max width: `640`
- max height: `512`
- max payload bytes: `327680`

This matches one full grayscale frame of `640 x 512`.

## Example Workflow

1. PC reads `FLIR_ADAS_v2` image.
2. PC decodes the file to grayscale pixels.
3. PC sends the packet over UART.
4. PS receives and stores the frame in DDR/BSS buffer.
5. PS prints:

```text
frame_id=1 width=640 height=512 payload=327680 checksum_rx=0x00123456 checksum_calc=0x00123456
```

## Why This Version Is Chosen

This version is intentionally minimal:

- no image file parsing on board
- no compression handling on board
- no resize in PC path by default
- no dependency on Linux for the first UART bring-up

That keeps the project focused on the actual deployment path instead of getting blocked by image decoding work.

