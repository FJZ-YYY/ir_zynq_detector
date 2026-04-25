#include "ir_pl_dw3x3.h"
#include "ir_pl_dw3x3_realcase_batch_data.h"
#include "ir_pl_dw3x3_realcase_channel_data.h"
#include "ir_pl_dw3x3_realcase_data.h"

#include <stdint.h>
#include <stdio.h>

typedef struct {
    uint32_t regs[16];
    int16_t window[IRDET_DW3X3_WINDOW_TAPS];
    int16_t weights[IRDET_DW3X3_WINDOW_TAPS];
    uint16_t width;
    uint16_t height;
    int32_t bias;
    int32_t result;
} mock_dw3x3_hw_t;

static uint32_t reg_index(uint32_t offset) {
    return offset >> 2;
}

static int32_t run_expected(const mock_dw3x3_hw_t* hw) {
    int32_t acc = hw->bias;
    uint32_t idx;

    for (idx = 0U; idx < IRDET_DW3X3_WINDOW_TAPS; ++idx) {
        acc += (int32_t)hw->window[idx] * (int32_t)hw->weights[idx];
    }
    return acc;
}

static void mock_run_core(mock_dw3x3_hw_t* hw) {
    hw->result = run_expected(hw);
    hw->regs[reg_index(IRDET_DW3X3_REG_CONTROL)] &= ~IRDET_DW3X3_CTRL_BUSY;
    hw->regs[reg_index(IRDET_DW3X3_REG_CONTROL)] |= IRDET_DW3X3_CTRL_DONE | IRDET_DW3X3_CTRL_CFG_READY;
}

static uint32_t mock_read32(void* ctx, uintptr_t addr) {
    mock_dw3x3_hw_t* hw = (mock_dw3x3_hw_t*)ctx;
    const uint32_t offset = (uint32_t)addr;

    switch (offset) {
        case IRDET_DW3X3_REG_CONTROL:
            return hw->regs[reg_index(offset)];
        case IRDET_DW3X3_REG_CFG_DIMS:
            return ((uint32_t)hw->height << 16) | hw->width;
        case IRDET_DW3X3_REG_BIAS:
            return (uint32_t)hw->bias;
        case IRDET_DW3X3_REG_OUT_DATA:
            return (uint32_t)hw->result;
        default:
            return hw->regs[reg_index(offset)];
    }
}

static void mock_write32(void* ctx, uintptr_t addr, uint32_t value) {
    mock_dw3x3_hw_t* hw = (mock_dw3x3_hw_t*)ctx;
    const uint32_t offset = (uint32_t)addr;

    hw->regs[reg_index(offset)] = value;
    switch (offset) {
        case IRDET_DW3X3_REG_CONTROL:
            if ((value & IRDET_DW3X3_CTRL_CLEAR_DONE) != 0U) {
                hw->regs[reg_index(IRDET_DW3X3_REG_CONTROL)] &= ~IRDET_DW3X3_CTRL_DONE;
            }
            if ((value & IRDET_DW3X3_CTRL_START) != 0U) {
                hw->regs[reg_index(IRDET_DW3X3_REG_CONTROL)] &= ~IRDET_DW3X3_CTRL_DONE;
                hw->regs[reg_index(IRDET_DW3X3_REG_CONTROL)] |= IRDET_DW3X3_CTRL_BUSY;
                mock_run_core(hw);
            }
            break;
        case IRDET_DW3X3_REG_CFG_DIMS:
            hw->width = (uint16_t)(value & 0xFFFFu);
            hw->height = (uint16_t)((value >> 16) & 0xFFFFu);
            hw->regs[reg_index(IRDET_DW3X3_REG_CONTROL)] |= IRDET_DW3X3_CTRL_CFG_READY;
            break;
        case IRDET_DW3X3_REG_BIAS:
            hw->bias = (int32_t)value;
            break;
        case IRDET_DW3X3_REG_FEAT_DATA: {
            const uint32_t feat_idx = hw->regs[reg_index(IRDET_DW3X3_REG_FEAT_ADDR)] & 0xFu;
            if (feat_idx < IRDET_DW3X3_WINDOW_TAPS) {
                hw->window[feat_idx] = (int16_t)(value & 0xFFFFu);
            }
            break;
        }
        case IRDET_DW3X3_REG_WEIGHT_DATA: {
            const uint32_t weight_idx = hw->regs[reg_index(IRDET_DW3X3_REG_WEIGHT_ADDR)] & 0xFu;
            if (weight_idx < IRDET_DW3X3_WINDOW_TAPS) {
                hw->weights[weight_idx] = (int16_t)(value & 0xFFFFu);
            }
            break;
        }
        default:
            break;
    }
}

int main(void) {
    static const int16_t k_window[IRDET_DW3X3_WINDOW_TAPS] = {
        1, 2, 3,
        4, 5, 6,
        7, 8, 9,
    };
    static const int16_t k_weights[IRDET_DW3X3_WINDOW_TAPS] = {
        1, 1, 1,
        1, 1, 1,
        1, 1, 1,
    };

    mock_dw3x3_hw_t mock_hw = { 0 };
    irdet_dw3x3_dev_t dev;
    int32_t out_value = 0;
    int rc;

    irdet_dw3x3_init(
        &dev,
        0U,
        IRDET_DW3X3_WINDOW_W,
        IRDET_DW3X3_WINDOW_H,
        &mock_hw,
        mock_read32,
        mock_write32);

    rc = irdet_dw3x3_run_window_q(&dev, k_window, k_weights, 0, &out_value, 16U);
    if (rc != 0) {
        printf("run_window failed rc=%d\n", rc);
        return 1;
    }

    if (out_value != 45) {
        printf("mismatch expected=45 got=%ld\n", (long)out_value);
        return 2;
    }

    rc = irdet_dw3x3_run_window_q(
        &dev,
        IRDET_DW3X3_REALCASE_WINDOW_Q,
        IRDET_DW3X3_REALCASE_WEIGHT_Q,
        IRDET_DW3X3_REALCASE_BIAS_Q,
        &out_value,
        16U);
    if (rc != 0) {
        printf("realcase run_window failed rc=%d\n", rc);
        return 3;
    }

    if (out_value != IRDET_DW3X3_REALCASE_EXPECTED_ACC) {
        printf(
            "realcase mismatch expected=%ld got=%ld\n",
            (long)IRDET_DW3X3_REALCASE_EXPECTED_ACC,
            (long)out_value);
        return 4;
    }

    for (uint32_t idx = 0U; idx < IRDET_DW3X3_BATCH_COUNT; ++idx) {
        rc = irdet_dw3x3_run_window_q(
            &dev,
            IRDET_DW3X3_BATCH_WINDOW_Q[idx],
            IRDET_DW3X3_BATCH_WEIGHT_Q,
            IRDET_DW3X3_BATCH_BIAS_Q,
            &out_value,
            16U);
        if (rc != 0) {
            printf("batch run_window failed idx=%lu rc=%d\n", (unsigned long)idx, rc);
            return 5;
        }

        if (out_value != IRDET_DW3X3_BATCH_EXPECTED_ACC[idx]) {
            printf(
                "batch mismatch idx=%lu expected=%ld got=%ld\n",
                (unsigned long)idx,
                (long)IRDET_DW3X3_BATCH_EXPECTED_ACC[idx],
                (long)out_value);
            return 6;
        }
    }

    for (uint32_t idx = 0U; idx < IRDET_DW3X3_CHANNEL_COUNT; ++idx) {
        rc = irdet_dw3x3_run_window_q(
            &dev,
            IRDET_DW3X3_CHANNEL_WINDOW_Q[idx],
            IRDET_DW3X3_CHANNEL_WEIGHT_Q,
            IRDET_DW3X3_CHANNEL_BIAS_Q,
            &out_value,
            16U);
        if (rc != 0) {
            printf("channel run_window failed idx=%lu rc=%d\n", (unsigned long)idx, rc);
            return 7;
        }

        if (out_value != IRDET_DW3X3_CHANNEL_EXPECTED_ACC[idx]) {
            printf(
                "channel mismatch idx=%lu expected=%ld got=%ld\n",
                (unsigned long)idx,
                (long)IRDET_DW3X3_CHANNEL_EXPECTED_ACC[idx],
                (long)out_value);
            return 8;
        }
    }

    printf(
        "Mock OK: status=0x%08lX synthetic=45 realcase=%ld batch_count=%u channel_count=%u\n",
        (unsigned long)irdet_dw3x3_read_status(&dev),
        (long)IRDET_DW3X3_REALCASE_EXPECTED_ACC,
        (unsigned int)IRDET_DW3X3_BATCH_COUNT,
        (unsigned int)IRDET_DW3X3_CHANNEL_COUNT);
    return 0;
}
