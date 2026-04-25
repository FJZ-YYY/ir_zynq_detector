#include "ir_image_preprocess.h"
#include "ir_model_runner.h"
#include "ir_pl_dw3x3.h"
#include "ir_pl_dw3x3_selftest.h"
#include "uart_image_proto.h"

#include <string.h>

#include "sleep.h"
#include "xil_io.h"
#include "xil_printf.h"
#include "xparameters.h"
#include "xstatus.h"
#include "xuartps.h"

#ifndef XPAR_XUARTPS_0_DEVICE_ID
#error "PS UART is not enabled in the exported hardware platform."
#endif

#define IRDET_UART_DEVICE_ID XPAR_XUARTPS_0_DEVICE_ID
#define IRDET_UART_BAUDRATE  921600U

#ifndef IRDET_ENABLE_PL_SELFTEST_ON_BOOT
#define IRDET_ENABLE_PL_SELFTEST_ON_BOOT  0
#endif

static XUartPs g_uart;
static uint8_t g_image_buffer[IRDET_MAX_IMAGE_BYTES];
static uint8_t g_header_raw[IRDET_UART_HEADER_BYTES];
static float g_model_input[IRDET_MODEL_INPUT_ELEMS];
static irdet_detection_t g_detections[IRDET_MAX_DETECTIONS];

#if defined(XPAR_DW3X3_ACCEL_0_BASEADDR)
#define IRDET_HAVE_PL_DW3X3  1
#define IRDET_PL_DW3X3_BASE  XPAR_DW3X3_ACCEL_0_BASEADDR
#elif defined(XPAR_DW3X3_ACCEL_0_S_AXI_BASEADDR)
#define IRDET_HAVE_PL_DW3X3  1
#define IRDET_PL_DW3X3_BASE  XPAR_DW3X3_ACCEL_0_S_AXI_BASEADDR
#else
#define IRDET_HAVE_PL_DW3X3  0
#define IRDET_PL_DW3X3_BASE  0U
#endif

typedef struct {
    int status;
    int32_t cpu_ref;
    int32_t pl_out;
} pl_dw3x3_probe_t;

static int uart_init(uint16_t device_id, uint32_t baudrate) {
    XUartPs_Config* config_ptr;
    int status;

    config_ptr = XUartPs_LookupConfig(device_id);
    if (config_ptr == NULL) {
        return -1;
    }

    status = XUartPs_CfgInitialize(&g_uart, config_ptr, config_ptr->BaseAddress);
    if (status != XST_SUCCESS) {
        return -2;
    }

    XUartPs_SetBaudRate(&g_uart, baudrate);
    XUartPs_SetOperMode(&g_uart, XUARTPS_OPER_MODE_NORMAL);
    return 0;
}

static int uart_recv_exact(uint8_t* dst, uint32_t size_bytes) {
    uint32_t total = 0U;

    while (total < size_bytes) {
        total += XUartPs_Recv(&g_uart, &dst[total], size_bytes - total);
    }
    return 0;
}

static void uart_send_exact(const char* text) {
    uint32_t sent = 0U;
    const uint32_t size_bytes = (uint32_t)strlen(text);

    while (sent < size_bytes) {
        sent += XUartPs_Send(&g_uart, (uint8_t*)&text[sent], size_bytes - sent);
    }
    while (XUartPs_IsSending(&g_uart) != 0) {
    }
}

static uint32_t pl_read32(void* ctx, uintptr_t addr) {
    (void)ctx;
    return Xil_In32((UINTPTR)addr);
}

static void pl_write32(void* ctx, uintptr_t addr, uint32_t value) {
    (void)ctx;
    Xil_Out32((UINTPTR)addr, value);
}

static int16_t model_pixel_to_q8(float value) {
    float scaled = value * 255.0F;

    if (scaled <= 0.0F) {
        return 0;
    }
    if (scaled >= 255.0F) {
        return 255;
    }
    return (int16_t)(scaled + 0.5F);
}

static pl_dw3x3_probe_t run_pl_dw3x3_frame_probe(
    const float* model_input,
    uint16_t width,
    uint16_t height) {
    pl_dw3x3_probe_t result;

    result.status = 1;
    result.cpu_ref = 0;
    result.pl_out = 0;

#if IRDET_HAVE_PL_DW3X3
    if (model_input == NULL || width < IRDET_DW3X3_WINDOW_W || height < IRDET_DW3X3_WINDOW_H) {
        result.status = -1;
        return result;
    }

    {
        static const int16_t k_weights[IRDET_DW3X3_WINDOW_TAPS] = {
            1, 1, 1,
            1, 1, 1,
            1, 1, 1,
        };
        int16_t window[IRDET_DW3X3_WINDOW_TAPS];
        irdet_dw3x3_dev_t dev;
        uint32_t idx = 0U;
        uint16_t y;
        uint16_t x;

        for (y = 0U; y < IRDET_DW3X3_WINDOW_H; ++y) {
            for (x = 0U; x < IRDET_DW3X3_WINDOW_W; ++x) {
                const int16_t q = model_pixel_to_q8(model_input[(uint32_t)y * width + x]);
                window[idx++] = q;
                result.cpu_ref += q;
            }
        }

        irdet_dw3x3_init(
            &dev,
            (uintptr_t)IRDET_PL_DW3X3_BASE,
            IRDET_DW3X3_WINDOW_W,
            IRDET_DW3X3_WINDOW_H,
            0,
            pl_read32,
            pl_write32);

        result.status = irdet_dw3x3_run_window_q(
            &dev,
            window,
            k_weights,
            0,
            &result.pl_out,
            1000000U);
    }
#endif

    return result;
}

static int uart_sync_header(uint8_t raw_header[IRDET_UART_HEADER_BYTES]) {
    const uint8_t magic[4] = { 'I', 'R', 'D', 'T' };
    uint32_t matched = 0U;
    uint8_t byte = 0U;

    while (matched < 4U) {
        uart_recv_exact(&byte, 1U);
        if (byte == magic[matched]) {
            raw_header[matched] = byte;
            ++matched;
        } else if (byte == magic[0]) {
            raw_header[0] = byte;
            matched = 1U;
        } else {
            matched = 0U;
        }
    }

    return uart_recv_exact(&raw_header[4], IRDET_UART_HEADER_BYTES - 4U);
}

static void print_frame_result(
    const irdet_uart_frame_header_t* header,
    uint32_t checksum_calc,
    int checksum_ok,
    const irdet_preprocess_stats_t* pp_stats,
    int preprocess_ok,
    const pl_dw3x3_probe_t* pl_probe,
    const irdet_detection_t* detections,
    uint32_t detection_count,
    int detect_ok) {
    xil_printf(
        "frame_id=%lu width=%u height=%u payload=%lu checksum_rx=0x%08lx checksum_calc=0x%08lx "
        "pre_in=%ux%u pre_out=%ux%u min=%u max=%u mean_x1000=%ld "
        "pl_dw3x3_rc=%d cpu=%ld pl=%ld det_count=%lu %s %s %s",
        (unsigned long)header->frame_id,
        (unsigned int)header->width,
        (unsigned int)header->height,
        (unsigned long)header->payload_bytes,
        (unsigned long)header->checksum32,
        (unsigned long)checksum_calc,
        (unsigned int)pp_stats->src_width,
        (unsigned int)pp_stats->src_height,
        (unsigned int)pp_stats->dst_width,
        (unsigned int)pp_stats->dst_height,
        (unsigned int)pp_stats->min_pixel,
        (unsigned int)pp_stats->max_pixel,
        (long)pp_stats->mean_x1000,
        pl_probe != NULL ? pl_probe->status : -99,
        pl_probe != NULL ? (long)pl_probe->cpu_ref : 0L,
        pl_probe != NULL ? (long)pl_probe->pl_out : 0L,
        (unsigned long)detection_count,
        checksum_ok ? "RX_OK" : "RX_BAD",
        preprocess_ok ? "PRE_OK" : "PRE_BAD",
        detect_ok ? "DET_OK" : "DET_BAD");

    if (detection_count > 0U) {
        const irdet_detection_t* det = &detections[0];

        xil_printf(
            " class=%s score=%u.%03u bbox=[%u,%u,%u,%u]\r\n",
            det->class_name,
            (unsigned int)(det->score_x1000 / 1000U),
            (unsigned int)(det->score_x1000 % 1000U),
            (unsigned int)det->x1,
            (unsigned int)det->y1,
            (unsigned int)det->x2,
            (unsigned int)det->y2);
        return;
    }

    xil_printf("\r\n");
}

int main(void) {
    irdet_uart_frame_header_t header;
    irdet_preprocess_config_t preprocess_cfg;
    irdet_preprocess_stats_t preprocess_stats;
    irdet_model_config_t model_cfg;
    irdet_model_runner_t model_runner;
    pl_dw3x3_probe_t pl_probe;
    uint32_t checksum_calc;
    uint32_t detection_count;
    int detect_status;
    int status;

    status = uart_init(IRDET_UART_DEVICE_ID, IRDET_UART_BAUDRATE);
    if (status != 0) {
        xil_printf("UART init failed, rc=%d\r\n", status);
        return status;
    }

    uart_send_exact("\r\nIR detector UART image receiver ready.\r\n");
    uart_send_exact("Waiting for IRDT frame...\r\n");
    irdet_preprocess_get_default_config(&preprocess_cfg);
    irdet_model_get_default_config(&model_cfg);
    status = irdet_model_runner_init(&model_runner, &model_cfg);
    if (status != 0) {
        xil_printf("Model init failed, rc=%d\r\n", status);
        return status;
    }
    xil_printf(
        "Model backend=%s input=%ux%u threshold=%u.%03u\r\n",
        irdet_model_backend_name(model_cfg.backend),
        (unsigned int)model_cfg.input_width,
        (unsigned int)model_cfg.input_height,
        (unsigned int)(model_cfg.score_threshold_x1000 / 1000U),
        (unsigned int)(model_cfg.score_threshold_x1000 % 1000U));
#if IRDET_ENABLE_PL_SELFTEST_ON_BOOT
    status = irdet_dw3x3_pl_selftest_run();
    xil_printf("PL boot selftest rc=%d\r\n", status);
#else
    irdet_dw3x3_pl_selftest_report();
#endif

    while (1) {
        status = uart_sync_header(g_header_raw);
        if (status != 0) {
            xil_printf("Header sync failed, rc=%d\r\n", status);
            continue;
        }

        if (!irdet_header_has_magic(g_header_raw)) {
            uart_send_exact("Bad magic after sync.\r\n");
            continue;
        }

        irdet_decode_header(g_header_raw, &header);
        status = irdet_validate_header(&header, IRDET_MAX_IMAGE_BYTES);
        if (status != 0) {
            xil_printf("Header validate failed, rc=%d\r\n", status);
            continue;
        }

        uart_recv_exact(g_image_buffer, header.payload_bytes);
        checksum_calc = irdet_checksum32(g_image_buffer, header.payload_bytes);
        status = irdet_preprocess_gray8_image(
            g_image_buffer,
            header.width,
            header.height,
            &preprocess_cfg,
            g_model_input,
            IRDET_MODEL_INPUT_W,
            IRDET_MODEL_INPUT_H,
            &preprocess_stats);
        if (status == 0) {
            pl_probe = run_pl_dw3x3_frame_probe(
                g_model_input,
                IRDET_MODEL_INPUT_W,
                IRDET_MODEL_INPUT_H);
        } else {
            pl_probe.status = -10;
            pl_probe.cpu_ref = 0;
            pl_probe.pl_out = 0;
        }
        detect_status = irdet_model_runner_run(
            &model_runner,
            g_model_input,
            model_cfg.input_width,
            model_cfg.input_height,
            &preprocess_stats,
            g_detections,
            IRDET_MAX_DETECTIONS,
            &detection_count);
        print_frame_result(
            &header,
            checksum_calc,
            checksum_calc == header.checksum32,
            &preprocess_stats,
            status == 0,
            &pl_probe,
            g_detections,
            detection_count,
            detect_status == 0);

        usleep(1000U);
    }
}
