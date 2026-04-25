#pragma once

#include <stdint.h>

#define IRDET_DW3X3_FULL_REG_CONTROL      0x00u
#define IRDET_DW3X3_FULL_REG_CFG_DIMS     0x04u
#define IRDET_DW3X3_FULL_REG_BIAS         0x08u
#define IRDET_DW3X3_FULL_REG_FEAT_ADDR    0x0Cu
#define IRDET_DW3X3_FULL_REG_FEAT_DATA    0x10u
#define IRDET_DW3X3_FULL_REG_WEIGHT_ADDR  0x14u
#define IRDET_DW3X3_FULL_REG_WEIGHT_DATA  0x18u
#define IRDET_DW3X3_FULL_REG_OUT_ADDR     0x1Cu
#define IRDET_DW3X3_FULL_REG_OUT_DATA     0x20u
#define IRDET_DW3X3_FULL_REG_INFO         0x24u

#define IRDET_DW3X3_FULL_CTRL_START       0x00000001u
#define IRDET_DW3X3_FULL_CTRL_DONE        0x00000002u
#define IRDET_DW3X3_FULL_CTRL_BUSY        0x00000004u
#define IRDET_DW3X3_FULL_CTRL_CFG_READY   0x00000008u
#define IRDET_DW3X3_FULL_CTRL_CLEAR_DONE  0x00000002u

typedef uint32_t (*irdet_dw3x3_full_mmio_read_fn)(void* ctx, uintptr_t addr);
typedef void (*irdet_dw3x3_full_mmio_write_fn)(void* ctx, uintptr_t addr, uint32_t value);

typedef struct {
    uintptr_t base_addr;
    uint16_t max_width;
    uint16_t max_height;
    void* io_ctx;
    irdet_dw3x3_full_mmio_read_fn read32;
    irdet_dw3x3_full_mmio_write_fn write32;
} irdet_dw3x3_full_dev_t;

void irdet_dw3x3_full_init(
    irdet_dw3x3_full_dev_t* dev,
    uintptr_t base_addr,
    uint16_t max_width,
    uint16_t max_height,
    void* io_ctx,
    irdet_dw3x3_full_mmio_read_fn read32,
    irdet_dw3x3_full_mmio_write_fn write32);

uint32_t irdet_dw3x3_full_read_status(const irdet_dw3x3_full_dev_t* dev);
int irdet_dw3x3_full_configure(
    irdet_dw3x3_full_dev_t* dev,
    uint16_t width,
    uint16_t height,
    int32_t bias_q);
int irdet_dw3x3_full_write_feature_q(
    irdet_dw3x3_full_dev_t* dev,
    const int16_t* data,
    uint32_t elem_count);
int irdet_dw3x3_full_write_weights_q(irdet_dw3x3_full_dev_t* dev, const int16_t* weights9);
int irdet_dw3x3_full_start(irdet_dw3x3_full_dev_t* dev);
int irdet_dw3x3_full_wait_done(const irdet_dw3x3_full_dev_t* dev, uint32_t max_polls);
int irdet_dw3x3_full_read_output_q(
    const irdet_dw3x3_full_dev_t* dev,
    uint32_t index,
    int32_t* out_value);
