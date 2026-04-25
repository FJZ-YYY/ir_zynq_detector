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
