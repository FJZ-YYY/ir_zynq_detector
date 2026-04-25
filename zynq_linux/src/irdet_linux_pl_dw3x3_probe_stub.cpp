#include "irdet_linux_pl_dw3x3_probe.h"

#include <string.h>

namespace {

constexpr uintptr_t kDefaultDw3x3FullBase = 0x43C10000u;

}  // namespace

void irdet_linux_pl_dw3x3_full_probe_get_default_config(
    irdet_linux_pl_dw3x3_full_probe_config_t* cfg) {
    if (cfg == nullptr) {
        return;
    }
    cfg->full_base = kDefaultDw3x3FullBase;
}

int irdet_linux_pl_dw3x3_run_full_probe(
    const irdet_linux_pl_dw3x3_full_probe_config_t* cfg,
    irdet_linux_pl_dw3x3_full_probe_result_t* out_result) {
    (void)cfg;
    if (out_result != nullptr) {
        memset(out_result, 0, sizeof(*out_result));
    }
    return -200;
}

void irdet_linux_pl_dw3x3_real_layer_case_get_default_config(
    irdet_linux_pl_dw3x3_real_layer_case_config_t* cfg) {
    if (cfg == nullptr) {
        return;
    }
    cfg->full_base = kDefaultDw3x3FullBase;
    cfg->case_dir = "";
}

int irdet_linux_pl_dw3x3_run_real_layer_case(
    const irdet_linux_pl_dw3x3_real_layer_case_config_t* cfg,
    irdet_linux_pl_dw3x3_real_layer_case_result_t* out_result) {
    (void)cfg;
    if (out_result != nullptr) {
        memset(out_result, 0, sizeof(*out_result));
    }
    return -201;
}

void irdet_linux_pl_dw3x3_runtime_blob_compare_get_default_config(
    irdet_linux_pl_dw3x3_runtime_blob_compare_config_t* cfg) {
    if (cfg == nullptr) {
        return;
    }
    cfg->full_base = kDefaultDw3x3FullBase;
    cfg->case_dir = "";
    cfg->channel = 11U;
}

int irdet_linux_pl_dw3x3_run_runtime_blob_compare(
    const irdet_linux_pl_dw3x3_runtime_blob_compare_config_t* cfg,
    const float* blob_values,
    int blob_dims,
    int blob_w,
    int blob_h,
    int blob_c,
    irdet_linux_pl_dw3x3_runtime_blob_compare_result_t* out_result) {
    (void)cfg;
    (void)blob_values;
    (void)blob_dims;
    (void)blob_w;
    (void)blob_h;
    (void)blob_c;
    if (out_result != nullptr) {
        memset(out_result, 0, sizeof(*out_result));
    }
    return -202;
}

void irdet_linux_pl_dw3x3_runtime_blob_full_get_default_config(
    irdet_linux_pl_dw3x3_runtime_blob_full_config_t* cfg) {
    if (cfg == nullptr) {
        return;
    }
    cfg->full_base = kDefaultDw3x3FullBase;
    cfg->case_dir = "";
    cfg->apply_relu6 = true;
}

int irdet_linux_pl_dw3x3_run_runtime_blob_full(
    const irdet_linux_pl_dw3x3_runtime_blob_full_config_t* cfg,
    const float* blob_values,
    int blob_dims,
    int blob_w,
    int blob_h,
    int blob_c,
    std::vector<float>* out_output_values,
    irdet_linux_pl_dw3x3_runtime_blob_full_result_t* out_result) {
    (void)cfg;
    (void)blob_values;
    (void)blob_dims;
    (void)blob_w;
    (void)blob_h;
    (void)blob_c;
    if (out_output_values != nullptr) {
        out_output_values->clear();
    }
    if (out_result != nullptr) {
        memset(out_result, 0, sizeof(*out_result));
    }
    return -203;
}
