#include "ir_pl_dw3x3_selftest.h"

#include <stdint.h>

#include "ir_pl_dw3x3.h"
#include "ir_pl_dw3x3_full.h"
#include "ir_pl_dw3x3_full_channel_data.h"
#include "ir_pl_dw3x3_realcase_batch_data.h"
#include "ir_pl_dw3x3_realcase_channel_data.h"
#include "ir_pl_dw3x3_realcase_data.h"
#include "xil_io.h"
#include "xil_printf.h"
#include "xparameters.h"
#include "xtime_l.h"

#if defined(XPAR_DW3X3_ACCEL_0_BASEADDR)
#define IRDET_HAVE_DW3X3_ACCEL  1
#define IRDET_DW3X3_BASEADDR    XPAR_DW3X3_ACCEL_0_BASEADDR
#elif defined(XPAR_DW3X3_ACCEL_0_S_AXI_BASEADDR)
#define IRDET_HAVE_DW3X3_ACCEL  1
#define IRDET_DW3X3_BASEADDR    XPAR_DW3X3_ACCEL_0_S_AXI_BASEADDR
#else
#define IRDET_HAVE_DW3X3_ACCEL  0
#define IRDET_DW3X3_BASEADDR    0U
#endif

#if defined(XPAR_DW3X3_FULL_0_BASEADDR)
#define IRDET_HAVE_DW3X3_FULL_ACCEL  1
#define IRDET_DW3X3_FULL_BASEADDR    XPAR_DW3X3_FULL_0_BASEADDR
#elif defined(XPAR_DW3X3_FULL_0_S_AXI_BASEADDR)
#define IRDET_HAVE_DW3X3_FULL_ACCEL  1
#define IRDET_DW3X3_FULL_BASEADDR    XPAR_DW3X3_FULL_0_S_AXI_BASEADDR
#elif defined(XPAR_MOBILENET_DW3X3_CHANNEL_FULL_AXI_0_BASEADDR)
#define IRDET_HAVE_DW3X3_FULL_ACCEL  1
#define IRDET_DW3X3_FULL_BASEADDR    XPAR_MOBILENET_DW3X3_CHANNEL_FULL_AXI_0_BASEADDR
#elif defined(XPAR_MOBILENET_DW3X3_CHANNEL_FULL_AXI_0_S_AXI_BASEADDR)
#define IRDET_HAVE_DW3X3_FULL_ACCEL  1
#define IRDET_DW3X3_FULL_BASEADDR    XPAR_MOBILENET_DW3X3_CHANNEL_FULL_AXI_0_S_AXI_BASEADDR
#else
#define IRDET_HAVE_DW3X3_FULL_ACCEL  0
#define IRDET_DW3X3_FULL_BASEADDR    0U
#endif

#if defined(XPAR_AXI_GPIO_0_BASEADDR)
#define IRDET_HAVE_AXI_GPIO_PROBE  1
#define IRDET_AXI_GPIO_BASEADDR    XPAR_AXI_GPIO_0_BASEADDR
#else
#define IRDET_HAVE_AXI_GPIO_PROBE  0
#define IRDET_AXI_GPIO_BASEADDR    0U
#endif

#define IRDET_AXI_GPIO_DATA_OFFSET  0x00U
#define IRDET_AXI_GPIO_TRI_OFFSET   0x04U
#define IRDET_AXI_GPIO_PATTERN      0xA5A55A5AU

static uint32_t irdet_xil_read32(void* ctx, uintptr_t addr) {
    (void)ctx;
    return Xil_In32((UINTPTR)addr);
}

static void irdet_xil_write32(void* ctx, uintptr_t addr, uint32_t value) {
    (void)ctx;
    Xil_Out32((UINTPTR)addr, value);
}

static int32_t irdet_dw3x3_cpu_ref_q(const int16_t* window, const int16_t* weights, int32_t bias_q) {
    int32_t acc = bias_q;
    uint32_t idx;

    for (idx = 0U; idx < IRDET_DW3X3_WINDOW_TAPS; ++idx) {
        acc += (int32_t)window[idx] * (int32_t)weights[idx];
    }
    return acc;
}

static uint32_t irdet_elapsed_us(XTime start_time, XTime end_time) {
    const uint64_t ticks = (uint64_t)(end_time - start_time);
    const uint64_t usec = (ticks * 1000000ULL) / (uint64_t)COUNTS_PER_SECOND;

    if (usec > 0xFFFFFFFFULL) {
        return 0xFFFFFFFFU;
    }
    return (uint32_t)usec;
}

int irdet_dw3x3_pl_selftest_report(void) {
#if IRDET_HAVE_DW3X3_ACCEL
    xil_printf(
        "PL dw3x3 accelerator present at 0x%08lx. "
        "Build bitstream and enable boot selftest when ready.\r\n",
        (unsigned long)IRDET_DW3X3_BASEADDR);
    return 0;
#else
    xil_printf("PL dw3x3 accelerator not present in xparameters.\r\n");
    return 1;
#endif
}

static int irdet_axi_gpio_probe(void) {
#if IRDET_HAVE_AXI_GPIO_PROBE
    uint32_t readback;

    xil_printf("AXI GPIO probe base=0x%08lx writing TRI...\r\n", (unsigned long)IRDET_AXI_GPIO_BASEADDR);
    Xil_Out32((UINTPTR)(IRDET_AXI_GPIO_BASEADDR + IRDET_AXI_GPIO_TRI_OFFSET), 0x00000000U);

    xil_printf("AXI GPIO probe writing DATA=0x%08lx...\r\n", (unsigned long)IRDET_AXI_GPIO_PATTERN);
    Xil_Out32((UINTPTR)(IRDET_AXI_GPIO_BASEADDR + IRDET_AXI_GPIO_DATA_OFFSET), IRDET_AXI_GPIO_PATTERN);

    xil_printf("AXI GPIO probe reading DATA...\r\n");
    readback = Xil_In32((UINTPTR)(IRDET_AXI_GPIO_BASEADDR + IRDET_AXI_GPIO_DATA_OFFSET));
    xil_printf("AXI GPIO probe readback=0x%08lx\r\n", (unsigned long)readback);
    return 0;
#else
    xil_printf("AXI GPIO probe not present in xparameters.\r\n");
    return 1;
#endif
}

static int irdet_dw3x3_replay_windows_timed(
    const char* name,
    uint32_t channel,
    uint32_t count,
    uint32_t patch_h,
    uint32_t patch_w,
    const int16_t windows[][IRDET_DW3X3_WINDOW_TAPS],
    const uint16_t* ys,
    const uint16_t* xs,
    const int16_t* weights,
    int32_t bias_q,
    const int32_t* expected_acc,
    uint32_t acc_scale,
    int32_t* first_acc,
    int32_t* last_acc,
    uint32_t* cpu_us,
    uint32_t* pl_us) {
#if IRDET_HAVE_DW3X3_ACCEL
    irdet_dw3x3_dev_t dev;
    XTime t0;
    XTime t1;
    uint32_t idx;
    int status;

    *first_acc = 0;
    *last_acc = 0;
    *cpu_us = 0U;
    *pl_us = 0U;

    xil_printf(
        "PL dw3x3 starting real MobileNetV2 %s replay channel=%lu count=%lu patch=%lux%lu...\r\n",
        name,
        (unsigned long)channel,
        (unsigned long)count,
        (unsigned long)patch_h,
        (unsigned long)patch_w);

    XTime_GetTime(&t0);
    for (idx = 0U; idx < count; ++idx) {
        const int32_t cpu_expected = irdet_dw3x3_cpu_ref_q(windows[idx], weights, bias_q);
        if (cpu_expected != expected_acc[idx]) {
            xil_printf(
                "PL dw3x3 %s CPU mismatch idx=%lu y=%u x=%u expected=%ld cpu=%ld\r\n",
                name,
                (unsigned long)idx,
                (unsigned int)ys[idx],
                (unsigned int)xs[idx],
                (long)expected_acc[idx],
                (long)cpu_expected);
            return -30;
        }
    }
    XTime_GetTime(&t1);
    *cpu_us = irdet_elapsed_us(t0, t1);

    irdet_dw3x3_init(
        &dev,
        (uintptr_t)IRDET_DW3X3_BASEADDR,
        IRDET_DW3X3_WINDOW_W,
        IRDET_DW3X3_WINDOW_H,
        0,
        irdet_xil_read32,
        irdet_xil_write32);

    XTime_GetTime(&t0);
    status = irdet_dw3x3_configure(&dev, IRDET_DW3X3_WINDOW_W, IRDET_DW3X3_WINDOW_H, bias_q);
    if (status != 0) {
        xil_printf("PL dw3x3 %s configure failed rc=%d\r\n", name, status);
        return -31;
    }

    status = irdet_dw3x3_write_weights_q(&dev, weights);
    if (status != 0) {
        xil_printf("PL dw3x3 %s write weights failed rc=%d\r\n", name, status);
        return -32;
    }

    for (idx = 0U; idx < count; ++idx) {
        int32_t out_value = 0;

        status = irdet_dw3x3_write_window_q(&dev, windows[idx]);
        if (status != 0) {
            xil_printf(
                "PL dw3x3 %s write window failed idx=%lu y=%u x=%u rc=%d\r\n",
                name,
                (unsigned long)idx,
                (unsigned int)ys[idx],
                (unsigned int)xs[idx],
                status);
            return -33;
        }

        status = irdet_dw3x3_start(&dev);
        if (status != 0) {
            xil_printf(
                "PL dw3x3 %s start failed idx=%lu y=%u x=%u rc=%d\r\n",
                name,
                (unsigned long)idx,
                (unsigned int)ys[idx],
                (unsigned int)xs[idx],
                status);
            return -34;
        }

        status = irdet_dw3x3_wait_done(&dev, 1000000U);
        if (status != 0) {
            xil_printf(
                "PL dw3x3 %s wait failed idx=%lu y=%u x=%u rc=%d status=0x%08lx\r\n",
                name,
                (unsigned long)idx,
                (unsigned int)ys[idx],
                (unsigned int)xs[idx],
                status,
                (unsigned long)irdet_dw3x3_read_status(&dev));
            return -35;
        }

        status = irdet_dw3x3_read_output_q(&dev, &out_value);
        if (status != 0) {
            xil_printf(
                "PL dw3x3 %s read failed idx=%lu y=%u x=%u rc=%d\r\n",
                name,
                (unsigned long)idx,
                (unsigned int)ys[idx],
                (unsigned int)xs[idx],
                status);
            return -36;
        }

        if (out_value != expected_acc[idx]) {
            xil_printf(
                "PL dw3x3 %s mismatch idx=%lu y=%u x=%u expected_acc=%ld pl_acc=%ld\r\n",
                name,
                (unsigned long)idx,
                (unsigned int)ys[idx],
                (unsigned int)xs[idx],
                (long)expected_acc[idx],
                (long)out_value);
            return -37;
        }

        if (idx == 0U) {
            *first_acc = out_value;
        }
        *last_acc = out_value;
    }
    XTime_GetTime(&t1);
    *pl_us = irdet_elapsed_us(t0, t1);

    xil_printf(
        "PL dw3x3 %s PASS channel=%lu count=%lu first_acc=%ld last_acc=%ld scale=%lu cpu_us=%lu pl_us=%lu pl_per_window_us_x1000=%lu\r\n",
        name,
        (unsigned long)channel,
        (unsigned long)count,
        (long)*first_acc,
        (long)*last_acc,
        (unsigned long)acc_scale,
        (unsigned long)*cpu_us,
        (unsigned long)*pl_us,
        (unsigned long)(((uint64_t)(*pl_us) * 1000ULL) / (uint64_t)count));
    return 0;
#else
    (void)name;
    (void)channel;
    (void)count;
    (void)patch_h;
    (void)patch_w;
    (void)windows;
    (void)ys;
    (void)xs;
    (void)weights;
    (void)bias_q;
    (void)expected_acc;
    (void)acc_scale;
    (void)first_acc;
    (void)last_acc;
    (void)cpu_us;
    (void)pl_us;
    xil_printf("PL dw3x3 timed replay skipped: accelerator base address not defined.\r\n");
    return 1;
#endif
}

int irdet_dw3x3_pl_realcase_selftest_run(void) {
#if IRDET_HAVE_DW3X3_ACCEL
    irdet_dw3x3_dev_t dev;
    int32_t cpu_expected;
    int32_t out_value = 0;
    int status;

    irdet_dw3x3_init(
        &dev,
        (uintptr_t)IRDET_DW3X3_BASEADDR,
        IRDET_DW3X3_WINDOW_W,
        IRDET_DW3X3_WINDOW_H,
        0,
        irdet_xil_read32,
        irdet_xil_write32);

    xil_printf(
        "PL dw3x3 starting real MobileNetV2 window replay channel=%d y=%d x=%d...\r\n",
        IRDET_DW3X3_REALCASE_CHANNEL,
        IRDET_DW3X3_REALCASE_Y,
        IRDET_DW3X3_REALCASE_X);

    cpu_expected = irdet_dw3x3_cpu_ref_q(
        IRDET_DW3X3_REALCASE_WINDOW_Q,
        IRDET_DW3X3_REALCASE_WEIGHT_Q,
        IRDET_DW3X3_REALCASE_BIAS_Q);

    if (cpu_expected != IRDET_DW3X3_REALCASE_EXPECTED_ACC) {
        xil_printf(
            "PL dw3x3 realcase CPU reference mismatch expected=%ld cpu=%ld\r\n",
            (long)IRDET_DW3X3_REALCASE_EXPECTED_ACC,
            (long)cpu_expected);
        return -10;
    }

    status = irdet_dw3x3_run_window_q(
        &dev,
        IRDET_DW3X3_REALCASE_WINDOW_Q,
        IRDET_DW3X3_REALCASE_WEIGHT_Q,
        IRDET_DW3X3_REALCASE_BIAS_Q,
        &out_value,
        1000000U);
    if (status != 0) {
        xil_printf("PL dw3x3 realcase run failed rc=%d\r\n", status);
        return -11;
    }

    if (out_value != IRDET_DW3X3_REALCASE_EXPECTED_ACC) {
        xil_printf(
            "PL dw3x3 realcase mismatch expected_acc=%ld pl_acc=%ld scale=%ld\r\n",
            (long)IRDET_DW3X3_REALCASE_EXPECTED_ACC,
            (long)out_value,
            (long)IRDET_DW3X3_REALCASE_ACC_SCALE);
        return -12;
    }

    xil_printf(
        "PL dw3x3 realcase PASS channel=%d y=%d x=%d expected_acc=%ld pl_acc=%ld scale=%ld\r\n",
        IRDET_DW3X3_REALCASE_CHANNEL,
        IRDET_DW3X3_REALCASE_Y,
        IRDET_DW3X3_REALCASE_X,
        (long)IRDET_DW3X3_REALCASE_EXPECTED_ACC,
        (long)out_value,
        (long)IRDET_DW3X3_REALCASE_ACC_SCALE);
    return 0;
#else
    xil_printf("PL dw3x3 realcase skipped: accelerator base address not defined.\r\n");
    return 1;
#endif
}

int irdet_dw3x3_pl_realcase_batch_selftest_run(void) {
#if IRDET_HAVE_DW3X3_ACCEL
    int32_t first_acc = 0;
    int32_t last_acc = 0;
    uint32_t cpu_us = 0U;
    uint32_t pl_us = 0U;

    return irdet_dw3x3_replay_windows_timed(
        "batch",
        IRDET_DW3X3_BATCH_CHANNEL,
        IRDET_DW3X3_BATCH_COUNT,
        IRDET_DW3X3_BATCH_PATCH_H,
        IRDET_DW3X3_BATCH_PATCH_W,
        IRDET_DW3X3_BATCH_WINDOW_Q,
        IRDET_DW3X3_BATCH_Y,
        IRDET_DW3X3_BATCH_X,
        IRDET_DW3X3_BATCH_WEIGHT_Q,
        IRDET_DW3X3_BATCH_BIAS_Q,
        IRDET_DW3X3_BATCH_EXPECTED_ACC,
        IRDET_DW3X3_BATCH_ACC_SCALE,
        &first_acc,
        &last_acc,
        &cpu_us,
        &pl_us);
#else
    xil_printf("PL dw3x3 batch skipped: accelerator base address not defined.\r\n");
    return 1;
#endif
}

int irdet_dw3x3_pl_realcase_channel_selftest_run(void) {
#if IRDET_HAVE_DW3X3_ACCEL
    int32_t first_acc = 0;
    int32_t last_acc = 0;
    uint32_t cpu_us = 0U;
    uint32_t pl_us = 0U;

    return irdet_dw3x3_replay_windows_timed(
        "channel",
        IRDET_DW3X3_CHANNEL_CHANNEL,
        IRDET_DW3X3_CHANNEL_COUNT,
        IRDET_DW3X3_CHANNEL_PATCH_H,
        IRDET_DW3X3_CHANNEL_PATCH_W,
        IRDET_DW3X3_CHANNEL_WINDOW_Q,
        IRDET_DW3X3_CHANNEL_Y,
        IRDET_DW3X3_CHANNEL_X,
        IRDET_DW3X3_CHANNEL_WEIGHT_Q,
        IRDET_DW3X3_CHANNEL_BIAS_Q,
        IRDET_DW3X3_CHANNEL_EXPECTED_ACC,
        IRDET_DW3X3_CHANNEL_ACC_SCALE,
        &first_acc,
        &last_acc,
        &cpu_us,
        &pl_us);
#else
    xil_printf("PL dw3x3 channel skipped: accelerator base address not defined.\r\n");
    return 1;
#endif
}

int irdet_dw3x3_pl_full_scheduler_selftest_run(void) {
#if IRDET_HAVE_DW3X3_FULL_ACCEL
    irdet_dw3x3_full_dev_t dev;
    XTime t0;
    XTime t1;
    XTime t_compute0;
    XTime t_compute1;
    uint32_t idx;
    uint32_t e2e_us;
    uint32_t compute_us;
    int32_t first_acc = 0;
    int32_t last_acc = 0;
    int status;

    irdet_dw3x3_full_init(
        &dev,
        (uintptr_t)IRDET_DW3X3_FULL_BASEADDR,
        IRDET_DW3X3_FULL_CH_WIDTH,
        IRDET_DW3X3_FULL_CH_HEIGHT,
        0,
        irdet_xil_read32,
        irdet_xil_write32);

    xil_printf(
        "PL dw3x3 full scheduler present at 0x%08lx info=0x%08lx\r\n",
        (unsigned long)IRDET_DW3X3_FULL_BASEADDR,
        (unsigned long)dev.read32(dev.io_ctx, dev.base_addr + IRDET_DW3X3_FULL_REG_INFO));

    xil_printf(
        "PL dw3x3 starting full-channel scheduler channel=%d count=%d shape=%dx%d...\r\n",
        IRDET_DW3X3_FULL_CH_CHANNEL,
        IRDET_DW3X3_FULL_CH_COUNT,
        IRDET_DW3X3_FULL_CH_HEIGHT,
        IRDET_DW3X3_FULL_CH_WIDTH);

    XTime_GetTime(&t0);
    status = irdet_dw3x3_full_configure(
        &dev,
        IRDET_DW3X3_FULL_CH_WIDTH,
        IRDET_DW3X3_FULL_CH_HEIGHT,
        IRDET_DW3X3_FULL_CH_BIAS_Q);
    if (status != 0) {
        xil_printf("PL dw3x3 full configure failed rc=%d\r\n", status);
        return -40;
    }

    status = irdet_dw3x3_full_write_feature_q(
        &dev,
        IRDET_DW3X3_FULL_CH_INPUT_Q,
        IRDET_DW3X3_FULL_CH_COUNT);
    if (status != 0) {
        xil_printf("PL dw3x3 full write feature failed rc=%d\r\n", status);
        return -41;
    }

    status = irdet_dw3x3_full_write_weights_q(&dev, IRDET_DW3X3_FULL_CH_WEIGHT_Q);
    if (status != 0) {
        xil_printf("PL dw3x3 full write weights failed rc=%d\r\n", status);
        return -42;
    }

    XTime_GetTime(&t_compute0);
    status = irdet_dw3x3_full_start(&dev);
    if (status != 0) {
        xil_printf("PL dw3x3 full start failed rc=%d\r\n", status);
        return -43;
    }

    status = irdet_dw3x3_full_wait_done(&dev, 10000000U);
    XTime_GetTime(&t_compute1);
    if (status != 0) {
        xil_printf(
            "PL dw3x3 full wait failed rc=%d status=0x%08lx\r\n",
            status,
            (unsigned long)irdet_dw3x3_full_read_status(&dev));
        return -44;
    }

    for (idx = 0U; idx < IRDET_DW3X3_FULL_CH_COUNT; ++idx) {
        int32_t out_value = 0;

        status = irdet_dw3x3_full_read_output_q(&dev, idx, &out_value);
        if (status != 0) {
            xil_printf("PL dw3x3 full read output failed idx=%lu rc=%d\r\n", (unsigned long)idx, status);
            return -45;
        }

        if (out_value != IRDET_DW3X3_FULL_CH_EXPECTED_ACC[idx]) {
            xil_printf(
                "PL dw3x3 full mismatch idx=%lu expected_acc=%ld pl_acc=%ld\r\n",
                (unsigned long)idx,
                (long)IRDET_DW3X3_FULL_CH_EXPECTED_ACC[idx],
                (long)out_value);
            return -46;
        }

        if (idx == 0U) {
            first_acc = out_value;
        }
        last_acc = out_value;
    }
    XTime_GetTime(&t1);

    e2e_us = irdet_elapsed_us(t0, t1);
    compute_us = irdet_elapsed_us(t_compute0, t_compute1);

    xil_printf(
        "PL dw3x3 full scheduler PASS channel=%d count=%d first_acc=%ld last_acc=%ld e2e_us=%lu compute_us=%lu e2e_per_output_us_x1000=%lu\r\n",
        IRDET_DW3X3_FULL_CH_CHANNEL,
        IRDET_DW3X3_FULL_CH_COUNT,
        (long)first_acc,
        (long)last_acc,
        (unsigned long)e2e_us,
        (unsigned long)compute_us,
        (unsigned long)(((uint64_t)e2e_us * 1000ULL) / (uint64_t)IRDET_DW3X3_FULL_CH_COUNT));
    return 0;
#else
    xil_printf("PL dw3x3 full scheduler skipped: accelerator base address not defined.\r\n");
    return 0;
#endif
}

int irdet_dw3x3_pl_selftest_run(void) {
#if IRDET_HAVE_DW3X3_ACCEL
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

    irdet_dw3x3_dev_t dev;
    int32_t out_value = 0;
    int status;
    int realcase_status;
    int batch_status;
    int channel_status;
    int full_status;

    irdet_dw3x3_init(
        &dev,
        (uintptr_t)IRDET_DW3X3_BASEADDR,
        IRDET_DW3X3_WINDOW_W,
        IRDET_DW3X3_WINDOW_H,
        0,
        irdet_xil_read32,
        irdet_xil_write32);

    xil_printf("PL dw3x3 starting AXI MMIO single-window test...\r\n");

    (void)irdet_axi_gpio_probe();

    xil_printf("PL dw3x3 reading INFO register...\r\n");
    xil_printf("PL dw3x3 info=0x%08lx\r\n",
               (unsigned long)dev.read32(dev.io_ctx, dev.base_addr + IRDET_DW3X3_REG_INFO));

    xil_printf("PL dw3x3 configure window...\r\n");
    status = irdet_dw3x3_configure(&dev, IRDET_DW3X3_WINDOW_W, IRDET_DW3X3_WINDOW_H, 0);
    if (status != 0) {
        xil_printf("PL dw3x3 configure failed rc=%d\r\n", status);
        return -1;
    }

    xil_printf("PL dw3x3 write pixels...\r\n");
    status = irdet_dw3x3_write_window_q(&dev, k_window);
    if (status != 0) {
        xil_printf("PL dw3x3 write pixels failed rc=%d\r\n", status);
        return -1;
    }

    xil_printf("PL dw3x3 write weights...\r\n");
    status = irdet_dw3x3_write_weights_q(&dev, k_weights);
    if (status != 0) {
        xil_printf("PL dw3x3 write weights failed rc=%d\r\n", status);
        return -1;
    }

    xil_printf("PL dw3x3 start core...\r\n");
    status = irdet_dw3x3_start(&dev);
    if (status != 0) {
        xil_printf("PL dw3x3 start failed rc=%d\r\n", status);
        return -1;
    }

    xil_printf("PL dw3x3 wait done...\r\n");
    status = irdet_dw3x3_wait_done(&dev, 1000000U);
    if (status != 0) {
        xil_printf("PL dw3x3 wait done failed rc=%d status=0x%08lx\r\n",
                   status,
                   (unsigned long)irdet_dw3x3_read_status(&dev));
        return -1;
    }

    xil_printf("PL dw3x3 read output...\r\n");
    status = irdet_dw3x3_read_output_q(&dev, &out_value);
    if (status != 0) {
        xil_printf("PL dw3x3 read output failed rc=%d\r\n", status);
        return -1;
    }

    if (out_value != 45) {
        xil_printf("PL dw3x3 mismatch exp=45 got=%ld\r\n", (long)out_value);
        return -2;
    }

    xil_printf(
        "PL dw3x3 selftest PASS base=0x%08lx mode=single_window result=%ld\r\n",
        (unsigned long)IRDET_DW3X3_BASEADDR,
        (long)out_value);

    realcase_status = irdet_dw3x3_pl_realcase_selftest_run();
    if (realcase_status != 0) {
        xil_printf("PL dw3x3 realcase selftest rc=%d\r\n", realcase_status);
        return realcase_status;
    }

    batch_status = irdet_dw3x3_pl_realcase_batch_selftest_run();
    if (batch_status != 0) {
        xil_printf("PL dw3x3 batch selftest rc=%d\r\n", batch_status);
        return batch_status;
    }

    channel_status = irdet_dw3x3_pl_realcase_channel_selftest_run();
    if (channel_status != 0) {
        xil_printf("PL dw3x3 channel selftest rc=%d\r\n", channel_status);
        return channel_status;
    }

    full_status = irdet_dw3x3_pl_full_scheduler_selftest_run();
    if (full_status != 0) {
        xil_printf("PL dw3x3 full scheduler selftest rc=%d\r\n", full_status);
        return full_status;
    }

    return 0;
#else
    xil_printf("PL dw3x3 selftest skipped: accelerator base address not defined.\r\n");
    return 1;
#endif
}
