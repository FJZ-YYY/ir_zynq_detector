#pragma once

#include <stddef.h>
#include <stdint.h>

#define IRDET_UART_HEADER_BYTES 32U
#define IRDET_UART_VERSION      1U
#define IRDET_PIXEL_GRAY8       1U
#define IRDET_MAX_IMAGE_BYTES   (640U * 512U)

typedef struct {
    uint8_t magic[4];
    uint8_t version;
    uint8_t pixel_format;
    uint16_t flags;
    uint32_t frame_id;
    uint16_t width;
    uint16_t height;
    uint32_t payload_bytes;
    uint32_t checksum32;
    uint32_t reserved0;
    uint32_t reserved1;
} irdet_uart_frame_header_t;

uint32_t irdet_checksum32(const uint8_t* data, uint32_t size_bytes);
void irdet_decode_header(const uint8_t raw[IRDET_UART_HEADER_BYTES], irdet_uart_frame_header_t* out_header);
int irdet_validate_header(const irdet_uart_frame_header_t* header, uint32_t max_payload_bytes);
int irdet_header_has_magic(const uint8_t raw[IRDET_UART_HEADER_BYTES]);

