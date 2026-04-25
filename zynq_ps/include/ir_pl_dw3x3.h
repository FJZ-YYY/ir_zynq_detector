#pragma once

#include <stddef.h>
#include <stdint.h>

#define IRDET_DW3X3_WINDOW_W        3u
#define IRDET_DW3X3_WINDOW_H        3u
#define IRDET_DW3X3_WINDOW_TAPS     9u

#define IRDET_DW3X3_REG_CONTROL      0x00u
#define IRDET_DW3X3_REG_CFG_DIMS     0x04u
#define IRDET_DW3X3_REG_BIAS         0x08u
#define IRDET_DW3X3_REG_FEAT_ADDR    0x0Cu
#define IRDET_DW3X3_REG_FEAT_DATA    0x10u
#define IRDET_DW3X3_REG_WEIGHT_ADDR  0x14u
#define IRDET_DW3X3_REG_WEIGHT_DATA  0x18u
#define IRDET_DW3X3_REG_OUT_ADDR     0x1Cu
#define IRDET_DW3X3_REG_OUT_DATA     0x20u
#define IRDET_DW3X3_REG_INFO         0x24u

#define IRDET_DW3X3_CTRL_START       0x00000001u
#define IRDET_DW3X3_CTRL_DONE        0x00000002u
#define IRDET_DW3X3_CTRL_BUSY        0x00000004u
#define IRDET_DW3X3_CTRL_CFG_READY   0x00000008u
#define IRDET_DW3X3_CTRL_CLEAR_DONE  0x00000002u

typedef uint32_t (*irdet_dw3x3_mmio_read_fn)(void* ctx, uintptr_t addr);
typedef void (*irdet_dw3x3_mmio_write_fn)(void* ctx, uintptr_t addr, uint32_t value);

typedef struct {
    uintptr_t base_addr;
    uint16_t max_width;
    uint16_t max_height;
    void* io_ctx;
    irdet_dw3x3_mmio_read_fn read32;
    irdet_dw3x3_mmio_write_fn write32;
} irdet_dw3x3_dev_t;

void irdet_dw3x3_init(
    irdet_dw3x3_dev_t* dev,
    uintptr_t base_addr,
    uint16_t max_width,
    uint16_t max_height,
    void* io_ctx,
    irdet_dw3x3_mmio_read_fn read32,
    irdet_dw3x3_mmio_write_fn write32);

uint32_t irdet_dw3x3_read_status(const irdet_dw3x3_dev_t* dev);
int irdet_dw3x3_configure(irdet_dw3x3_dev_t* dev, uint16_t width, uint16_t height, int32_t bias_q);
int irdet_dw3x3_write_window_q(irdet_dw3x3_dev_t* dev, const int16_t* pixels9);
int irdet_dw3x3_write_weights_q(irdet_dw3x3_dev_t* dev, const int16_t* weights9);
int irdet_dw3x3_start(irdet_dw3x3_dev_t* dev);
int irdet_dw3x3_wait_done(const irdet_dw3x3_dev_t* dev, uint32_t max_polls);
int irdet_dw3x3_read_output_q(const irdet_dw3x3_dev_t* dev, int32_t* out_value);
int irdet_dw3x3_run_window_q(
    irdet_dw3x3_dev_t* dev,
    const int16_t* pixels9,
    const int16_t* weights9,
    int32_t bias_q,
    int32_t* out_value,
    uint32_t max_polls);

/* Compatibility wrappers for the earlier full-map prototype API. */
int irdet_dw3x3_write_feature_map_q(irdet_dw3x3_dev_t* dev, const int16_t* data, uint32_t elem_count);
int irdet_dw3x3_read_output_map_q(const irdet_dw3x3_dev_t* dev, int32_t* out_data, uint32_t elem_count);
