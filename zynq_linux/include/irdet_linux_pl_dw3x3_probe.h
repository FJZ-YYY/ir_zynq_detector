#pragma once

#include <stdint.h>

struct irdet_linux_pl_dw3x3_full_probe_config_t {
    uintptr_t full_base;
};

struct irdet_linux_pl_dw3x3_full_probe_result_t {
    uint32_t full_info;
    uint32_t output_count;
    int32_t first_acc;
    int32_t last_acc;
    uint32_t e2e_us;
    uint32_t compute_us;
};

void irdet_linux_pl_dw3x3_full_probe_get_default_config(
    irdet_linux_pl_dw3x3_full_probe_config_t* cfg);

int irdet_linux_pl_dw3x3_run_full_probe(
    const irdet_linux_pl_dw3x3_full_probe_config_t* cfg,
    irdet_linux_pl_dw3x3_full_probe_result_t* out_result);

struct irdet_linux_pl_dw3x3_real_layer_case_config_t {
    uintptr_t full_base;
    const char* case_dir;
};

struct irdet_linux_pl_dw3x3_real_layer_case_result_t {
    uint32_t full_info;
    uint32_t channel;
    uint16_t width;
    uint16_t height;
    uint32_t output_count;
    uint32_t frac_bits;
    int32_t bias_q;
    int32_t first_acc;
    int32_t last_acc;
    float max_abs_float_error;
    uint32_t status_before_start;
    uint32_t status_after_start;
    uint32_t status_after_wait;
    uint32_t e2e_us;
    uint32_t compute_us;
};

void irdet_linux_pl_dw3x3_real_layer_case_get_default_config(
    irdet_linux_pl_dw3x3_real_layer_case_config_t* cfg);

int irdet_linux_pl_dw3x3_run_real_layer_case(
    const irdet_linux_pl_dw3x3_real_layer_case_config_t* cfg,
    irdet_linux_pl_dw3x3_real_layer_case_result_t* out_result);
