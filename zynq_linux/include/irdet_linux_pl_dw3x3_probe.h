#pragma once

#include <stdint.h>

#include <vector>

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

struct irdet_linux_pl_dw3x3_runtime_blob_compare_config_t {
    uintptr_t full_base;
    const char* case_dir;
    uint32_t channel;
};

struct irdet_linux_pl_dw3x3_runtime_blob_compare_result_t {
    uint32_t full_info;
    uint32_t channel;
    uint16_t width;
    uint16_t height;
    uint32_t output_count;
    uint32_t blob_dims;
    uint16_t blob_width;
    uint16_t blob_height;
    uint32_t blob_channels;
    uint32_t frac_bits;
    int32_t bias_q;
    int32_t first_cpu_acc;
    int32_t first_pl_acc;
    int32_t last_cpu_acc;
    int32_t last_pl_acc;
    int32_t max_abs_acc_error;
    float max_abs_float_error;
    float mean_abs_float_error;
    uint32_t status_before_start;
    uint32_t status_after_start;
    uint32_t status_after_wait;
    uint32_t cpu_us;
    uint32_t e2e_us;
    uint32_t compute_us;
};

void irdet_linux_pl_dw3x3_runtime_blob_compare_get_default_config(
    irdet_linux_pl_dw3x3_runtime_blob_compare_config_t* cfg);

int irdet_linux_pl_dw3x3_run_runtime_blob_compare(
    const irdet_linux_pl_dw3x3_runtime_blob_compare_config_t* cfg,
    const float* blob_values,
    int blob_dims,
    int blob_w,
    int blob_h,
    int blob_c,
    irdet_linux_pl_dw3x3_runtime_blob_compare_result_t* out_result);

struct irdet_linux_pl_dw3x3_runtime_blob_full_config_t {
    uintptr_t full_base;
    const char* case_dir;
    bool apply_relu6;
};

struct irdet_linux_pl_dw3x3_runtime_blob_full_result_t {
    uint32_t full_info;
    uint16_t width;
    uint16_t height;
    uint32_t channels;
    uint32_t count_per_channel;
    uint32_t total_count;
    uint32_t frac_bits;
    uint32_t pl_calls;
    uint32_t failed_channel;
    int32_t first_cpu_acc;
    int32_t first_pl_acc;
    int32_t last_cpu_acc;
    int32_t last_pl_acc;
    int32_t max_abs_acc_error;
    float max_abs_float_error;
    float mean_abs_float_error;
    uint32_t status_before_start;
    uint32_t status_after_start;
    uint32_t status_after_wait;
    uint32_t cpu_us;
    uint32_t e2e_us;
    uint32_t compute_us_total;
};

void irdet_linux_pl_dw3x3_runtime_blob_full_get_default_config(
    irdet_linux_pl_dw3x3_runtime_blob_full_config_t* cfg);

int irdet_linux_pl_dw3x3_run_runtime_blob_full(
    const irdet_linux_pl_dw3x3_runtime_blob_full_config_t* cfg,
    const float* blob_values,
    int blob_dims,
    int blob_w,
    int blob_h,
    int blob_c,
    std::vector<float>* out_output_values,
    irdet_linux_pl_dw3x3_runtime_blob_full_result_t* out_result);
