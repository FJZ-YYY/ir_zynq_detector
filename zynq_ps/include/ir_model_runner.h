#pragma once

#include <stdint.h>

#include "ir_image_preprocess.h"

#ifdef __cplusplus
extern "C" {
#endif

#define IRDET_MAX_DETECTIONS  4U

typedef enum {
    IRDET_MODEL_BACKEND_STUB = 0,
    IRDET_MODEL_BACKEND_SSD_RAW_HEAD = 1,
} irdet_model_backend_t;

typedef struct {
    uint8_t class_id;
    const char* class_name;
    uint16_t score_x1000;
    uint16_t x1;
    uint16_t y1;
    uint16_t x2;
    uint16_t y2;
} irdet_detection_t;

typedef struct {
    irdet_model_backend_t backend;
    uint16_t input_width;
    uint16_t input_height;
    uint16_t score_threshold_x1000;
    uint16_t iou_threshold_x1000;
} irdet_model_config_t;

typedef struct {
    uint8_t is_initialized;
    irdet_model_config_t cfg;
} irdet_model_runner_t;

void irdet_model_get_default_config(irdet_model_config_t* cfg);
const char* irdet_model_backend_name(irdet_model_backend_t backend);
int irdet_model_runner_init(irdet_model_runner_t* runner, const irdet_model_config_t* cfg);
int irdet_model_runner_run(
    const irdet_model_runner_t* runner,
    const float* model_input,
    uint16_t input_width,
    uint16_t input_height,
    const irdet_preprocess_stats_t* pp_stats,
    irdet_detection_t* out_detections,
    uint32_t max_detections,
    uint32_t* out_count);

#ifdef __cplusplus
}
#endif
