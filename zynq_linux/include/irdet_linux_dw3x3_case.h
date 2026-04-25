#pragma once

#include <stdint.h>

#include <vector>

struct irdet_linux_dw3x3_case_config_t {
    const char* case_dir;
    bool apply_relu6;
};

struct irdet_linux_dw3x3_case_result_t {
    uint32_t channels;
    uint16_t width;
    uint16_t height;
    uint32_t count_per_channel;
    uint32_t total_count;
    uint32_t cpu_us;
    float first_value;
    float last_value;
    std::vector<float> output_values;
};

void irdet_linux_dw3x3_case_get_default_config(irdet_linux_dw3x3_case_config_t* cfg);

int irdet_linux_dw3x3_case_run_cpu_full(
    const irdet_linux_dw3x3_case_config_t* cfg,
    const float* input_blob_values,
    int blob_dims,
    int blob_w,
    int blob_h,
    int blob_c,
    irdet_linux_dw3x3_case_result_t* out_result);
