#include "ir_pl_dw3x3_full.h"

static int irdet_dw3x3_full_is_ready(const irdet_dw3x3_full_dev_t* dev) {
    if (dev == 0 || dev->read32 == 0 || dev->write32 == 0) {
        return 0;
    }
    return 1;
}

static uintptr_t reg_addr(const irdet_dw3x3_full_dev_t* dev, uint32_t offset) {
    return dev->base_addr + (uintptr_t)offset;
}

void irdet_dw3x3_full_init(
    irdet_dw3x3_full_dev_t* dev,
    uintptr_t base_addr,
    uint16_t max_width,
    uint16_t max_height,
    void* io_ctx,
    irdet_dw3x3_full_mmio_read_fn read32,
    irdet_dw3x3_full_mmio_write_fn write32) {
    if (dev == 0) {
        return;
    }

    dev->base_addr = base_addr;
    dev->max_width = max_width;
    dev->max_height = max_height;
    dev->io_ctx = io_ctx;
    dev->read32 = read32;
    dev->write32 = write32;
}

uint32_t irdet_dw3x3_full_read_status(const irdet_dw3x3_full_dev_t* dev) {
    if (!irdet_dw3x3_full_is_ready(dev)) {
        return 0U;
    }
    return dev->read32(dev->io_ctx, reg_addr(dev, IRDET_DW3X3_FULL_REG_CONTROL));
}

int irdet_dw3x3_full_configure(
    irdet_dw3x3_full_dev_t* dev,
    uint16_t width,
    uint16_t height,
    int32_t bias_q) {
    uint32_t dims;

    if (!irdet_dw3x3_full_is_ready(dev)) {
        return -1;
    }
    if (width == 0U || height == 0U) {
        return -2;
    }
    if (width > dev->max_width || height > dev->max_height) {
        return -3;
    }

    dims = ((uint32_t)height << 16) | (uint32_t)width;
    dev->write32(dev->io_ctx, reg_addr(dev, IRDET_DW3X3_FULL_REG_CFG_DIMS), dims);
    dev->write32(dev->io_ctx, reg_addr(dev, IRDET_DW3X3_FULL_REG_BIAS), (uint32_t)bias_q);
    return 0;
}

int irdet_dw3x3_full_write_feature_q(
    irdet_dw3x3_full_dev_t* dev,
    const int16_t* data,
    uint32_t elem_count) {
    uint32_t idx;
    uint32_t max_elems;

    if (!irdet_dw3x3_full_is_ready(dev) || data == 0) {
        return -1;
    }
    max_elems = (uint32_t)dev->max_width * (uint32_t)dev->max_height;
    if (elem_count > max_elems) {
        return -2;
    }

    for (idx = 0U; idx < elem_count; ++idx) {
        dev->write32(dev->io_ctx, reg_addr(dev, IRDET_DW3X3_FULL_REG_FEAT_ADDR), idx);
        dev->write32(dev->io_ctx, reg_addr(dev, IRDET_DW3X3_FULL_REG_FEAT_DATA), (uint16_t)data[idx]);
    }
    return 0;
}

int irdet_dw3x3_full_write_weights_q(irdet_dw3x3_full_dev_t* dev, const int16_t* weights9) {
    uint32_t idx;

    if (!irdet_dw3x3_full_is_ready(dev) || weights9 == 0) {
        return -1;
    }

    for (idx = 0U; idx < 9U; ++idx) {
        dev->write32(dev->io_ctx, reg_addr(dev, IRDET_DW3X3_FULL_REG_WEIGHT_ADDR), idx);
        dev->write32(dev->io_ctx, reg_addr(dev, IRDET_DW3X3_FULL_REG_WEIGHT_DATA), (uint16_t)weights9[idx]);
    }
    return 0;
}

int irdet_dw3x3_full_start(irdet_dw3x3_full_dev_t* dev) {
    if (!irdet_dw3x3_full_is_ready(dev)) {
        return -1;
    }

    dev->write32(dev->io_ctx, reg_addr(dev, IRDET_DW3X3_FULL_REG_CONTROL), IRDET_DW3X3_FULL_CTRL_CLEAR_DONE);
    dev->write32(dev->io_ctx, reg_addr(dev, IRDET_DW3X3_FULL_REG_CONTROL), IRDET_DW3X3_FULL_CTRL_START);
    return 0;
}

int irdet_dw3x3_full_wait_done(const irdet_dw3x3_full_dev_t* dev, uint32_t max_polls) {
    uint32_t poll_idx;

    if (!irdet_dw3x3_full_is_ready(dev)) {
        return -1;
    }

    for (poll_idx = 0U; poll_idx < max_polls; ++poll_idx) {
        const uint32_t status = irdet_dw3x3_full_read_status(dev);
        if ((status & IRDET_DW3X3_FULL_CTRL_DONE) != 0U) {
            return 0;
        }
    }

    return -2;
}

int irdet_dw3x3_full_read_output_q(
    const irdet_dw3x3_full_dev_t* dev,
    uint32_t index,
    int32_t* out_value) {
    uint32_t max_elems;

    if (!irdet_dw3x3_full_is_ready(dev) || out_value == 0) {
        return -1;
    }
    max_elems = (uint32_t)dev->max_width * (uint32_t)dev->max_height;
    if (index >= max_elems) {
        return -2;
    }

    dev->write32(dev->io_ctx, reg_addr(dev, IRDET_DW3X3_FULL_REG_OUT_ADDR), index);
    *out_value = (int32_t)dev->read32(dev->io_ctx, reg_addr(dev, IRDET_DW3X3_FULL_REG_OUT_DATA));
    return 0;
}
