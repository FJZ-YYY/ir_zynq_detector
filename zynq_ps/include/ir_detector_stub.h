#pragma once

#include <stdint.h>

#include "ir_model_runner.h"

int irdet_stub_run(
    const float* model_input,
    uint16_t input_width,
    uint16_t input_height,
    const irdet_preprocess_stats_t* pp_stats,
    const irdet_model_config_t* cfg,
    irdet_detection_t* out_detections,
    uint32_t max_detections,
    uint32_t* out_count);
