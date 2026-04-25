#include "uart_image_proto.h"

static uint16_t irdet_read_le16(const uint8_t* p) {
    return (uint16_t)((uint16_t)p[0] | ((uint16_t)p[1] << 8));
}

static uint32_t irdet_read_le32(const uint8_t* p) {
    return (uint32_t)p[0]
        | ((uint32_t)p[1] << 8)
        | ((uint32_t)p[2] << 16)
        | ((uint32_t)p[3] << 24);
}

uint32_t irdet_checksum32(const uint8_t* data, uint32_t size_bytes) {
    uint32_t sum = 0U;
    uint32_t i;

    for (i = 0U; i < size_bytes; ++i) {
        sum += (uint32_t)data[i];
    }
    return sum;
}

void irdet_decode_header(const uint8_t raw[IRDET_UART_HEADER_BYTES], irdet_uart_frame_header_t* out_header) {
    if (out_header == NULL) {
        return;
    }

    out_header->magic[0] = raw[0];
    out_header->magic[1] = raw[1];
    out_header->magic[2] = raw[2];
    out_header->magic[3] = raw[3];
    out_header->version = raw[4];
    out_header->pixel_format = raw[5];
    out_header->flags = irdet_read_le16(&raw[6]);
    out_header->frame_id = irdet_read_le32(&raw[8]);
    out_header->width = irdet_read_le16(&raw[12]);
    out_header->height = irdet_read_le16(&raw[14]);
    out_header->payload_bytes = irdet_read_le32(&raw[16]);
    out_header->checksum32 = irdet_read_le32(&raw[20]);
    out_header->reserved0 = irdet_read_le32(&raw[24]);
    out_header->reserved1 = irdet_read_le32(&raw[28]);
}

int irdet_header_has_magic(const uint8_t raw[IRDET_UART_HEADER_BYTES]) {
    return raw[0] == 'I' && raw[1] == 'R' && raw[2] == 'D' && raw[3] == 'T';
}

int irdet_validate_header(const irdet_uart_frame_header_t* header, uint32_t max_payload_bytes) {
    uint32_t expected_bytes;

    if (header == NULL) {
        return -1;
    }
    if (header->magic[0] != 'I' || header->magic[1] != 'R'
        || header->magic[2] != 'D' || header->magic[3] != 'T') {
        return -2;
    }
    if (header->version != IRDET_UART_VERSION) {
        return -3;
    }
    if (header->pixel_format != IRDET_PIXEL_GRAY8) {
        return -4;
    }
    if (header->width == 0U || header->height == 0U) {
        return -5;
    }

    expected_bytes = (uint32_t)header->width * (uint32_t)header->height;
    if (header->payload_bytes != expected_bytes) {
        return -6;
    }
    if (header->payload_bytes > max_payload_bytes) {
        return -7;
    }
    return 0;
}

