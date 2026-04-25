#include "ir_pl_dw3x3.h"

static int irdet_dw3x3_is_ready(const irdet_dw3x3_dev_t* dev) {
    if (dev == 0 || dev->read32 == 0 || dev->write32 == 0) {
        return 0;
    }
    return 1;
}

static uintptr_t reg_addr(const irdet_dw3x3_dev_t* dev, uint32_t offset) {
    return dev->base_addr + (uintptr_t)offset;
}

void irdet_dw3x3_init(
    irdet_dw3x3_dev_t* dev,
    uintptr_t base_addr,
    uint16_t max_width,
    uint16_t max_height,
    void* io_ctx,
    irdet_dw3x3_mmio_read_fn read32,
    irdet_dw3x3_mmio_write_fn write32) {
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

uint32_t irdet_dw3x3_read_status(const irdet_dw3x3_dev_t* dev) {
    if (!irdet_dw3x3_is_ready(dev)) {
        return 0U;
    }
    return dev->read32(dev->io_ctx, reg_addr(dev, IRDET_DW3X3_REG_CONTROL));
}

int irdet_dw3x3_configure(irdet_dw3x3_dev_t* dev, uint16_t width, uint16_t height, int32_t bias_q) {
    uint32_t dims;

    if (!irdet_dw3x3_is_ready(dev)) {
        return -1;
    }
    if (width == 0U || height == 0U) {
        return -2;
    }
    if (width > dev->max_width || height > dev->max_height) {
        return -3;
    }
    if (width != IRDET_DW3X3_WINDOW_W || height != IRDET_DW3X3_WINDOW_H) {
        return -4;
    }

    dims = ((uint32_t)height << 16) | (uint32_t)width;
    dev->write32(dev->io_ctx, reg_addr(dev, IRDET_DW3X3_REG_CFG_DIMS), dims);
    dev->write32(dev->io_ctx, reg_addr(dev, IRDET_DW3X3_REG_BIAS), (uint32_t)bias_q);
    return 0;
}

int irdet_dw3x3_write_window_q(irdet_dw3x3_dev_t* dev, const int16_t* data) {
    uint32_t idx;

    if (!irdet_dw3x3_is_ready(dev) || data == 0) {
        return -1;
    }

    for (idx = 0U; idx < IRDET_DW3X3_WINDOW_TAPS; ++idx) {
        dev->write32(dev->io_ctx, reg_addr(dev, IRDET_DW3X3_REG_FEAT_ADDR), idx);
        dev->write32(dev->io_ctx, reg_addr(dev, IRDET_DW3X3_REG_FEAT_DATA), (uint16_t)data[idx]);
    }
    return 0;
}

int irdet_dw3x3_write_weights_q(irdet_dw3x3_dev_t* dev, const int16_t* weights9) {
    uint32_t idx;

    if (!irdet_dw3x3_is_ready(dev) || weights9 == 0) {
        return -1;
    }

    for (idx = 0U; idx < IRDET_DW3X3_WINDOW_TAPS; ++idx) {
        dev->write32(dev->io_ctx, reg_addr(dev, IRDET_DW3X3_REG_WEIGHT_ADDR), idx);
        dev->write32(dev->io_ctx, reg_addr(dev, IRDET_DW3X3_REG_WEIGHT_DATA), (uint16_t)weights9[idx]);
    }
    return 0;
}

int irdet_dw3x3_start(irdet_dw3x3_dev_t* dev) {
    if (!irdet_dw3x3_is_ready(dev)) {
        return -1;
    }

    dev->write32(dev->io_ctx, reg_addr(dev, IRDET_DW3X3_REG_CONTROL), IRDET_DW3X3_CTRL_CLEAR_DONE);
    dev->write32(dev->io_ctx, reg_addr(dev, IRDET_DW3X3_REG_CONTROL), IRDET_DW3X3_CTRL_START);
    return 0;
}

int irdet_dw3x3_wait_done(const irdet_dw3x3_dev_t* dev, uint32_t max_polls) {
    uint32_t poll_idx;

    if (!irdet_dw3x3_is_ready(dev)) {
        return -1;
    }

    for (poll_idx = 0U; poll_idx < max_polls; ++poll_idx) {
        const uint32_t status = irdet_dw3x3_read_status(dev);
        if ((status & IRDET_DW3X3_CTRL_DONE) != 0U) {
            return 0;
        }
    }

    return -2;
}

int irdet_dw3x3_read_output_q(const irdet_dw3x3_dev_t* dev, int32_t* out_value) {
    if (!irdet_dw3x3_is_ready(dev) || out_value == 0) {
        return -1;
    }

    dev->write32(dev->io_ctx, reg_addr(dev, IRDET_DW3X3_REG_OUT_ADDR), 0U);
    *out_value = (int32_t)dev->read32(dev->io_ctx, reg_addr(dev, IRDET_DW3X3_REG_OUT_DATA));
    return 0;
}

int irdet_dw3x3_run_window_q(
    irdet_dw3x3_dev_t* dev,
    const int16_t* pixels9,
    const int16_t* weights9,
    int32_t bias_q,
    int32_t* out_value,
    uint32_t max_polls) {
    int rc;

    rc = irdet_dw3x3_configure(dev, IRDET_DW3X3_WINDOW_W, IRDET_DW3X3_WINDOW_H, bias_q);
    if (rc != 0) {
        return rc;
    }

    rc = irdet_dw3x3_write_window_q(dev, pixels9);
    if (rc != 0) {
        return rc;
    }

    rc = irdet_dw3x3_write_weights_q(dev, weights9);
    if (rc != 0) {
        return rc;
    }

    rc = irdet_dw3x3_start(dev);
    if (rc != 0) {
        return rc;
    }

    rc = irdet_dw3x3_wait_done(dev, max_polls);
    if (rc != 0) {
        return rc;
    }

    return irdet_dw3x3_read_output_q(dev, out_value);
}

int irdet_dw3x3_write_feature_map_q(irdet_dw3x3_dev_t* dev, const int16_t* data, uint32_t elem_count) {
    if (elem_count != IRDET_DW3X3_WINDOW_TAPS) {
        return -2;
    }
    return irdet_dw3x3_write_window_q(dev, data);
}

int irdet_dw3x3_read_output_map_q(const irdet_dw3x3_dev_t* dev, int32_t* out_data, uint32_t elem_count) {
    if (elem_count != 1U) {
        return -2;
    }
    return irdet_dw3x3_read_output_q(dev, out_data);
}
