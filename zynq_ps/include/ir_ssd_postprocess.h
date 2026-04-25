#pragma once

#include <stdint.h>

#include "ir_model_runner.h"

#ifdef __cplusplus
extern "C" {
#endif

#define IRDET_SSD_NUM_CLASSES_WITH_BG  4U
#define IRDET_SSD_NUM_FG_CLASSES       3U
#define IRDET_SSD_BOX_VALUES           4U
#define IRDET_SSD_DEFAULT_NUM_ANCHORS  660U
#define IRDET_SSD_MAX_CANDIDATES       512U

typedef struct {
    const float* bbox_regression;
    const float* cls_logits;
    const float* anchors_xyxy;
    uint32_t num_anchors;
    uint32_t num_classes_with_bg;
} irdet_ssd_raw_head_tensors_t;

typedef struct {
    uint16_t input_width;
    uint16_t input_height;
    uint16_t score_threshold_x1000;
    uint16_t iou_threshold_x1000;
    float box_coder_weights[IRDET_SSD_BOX_VALUES];
} irdet_ssd_postprocess_config_t;

void irdet_ssd_postprocess_get_default_config(irdet_ssd_postprocess_config_t* cfg);
const char* irdet_ssd_class_name(uint8_t class_id);
int irdet_ssd_postprocess_run(
    const irdet_ssd_raw_head_tensors_t* tensors,
    const irdet_ssd_postprocess_config_t* cfg,
    const irdet_preprocess_stats_t* pp_stats,
    irdet_detection_t* out_detections,
    uint32_t max_detections,
    uint32_t* out_count);

#ifdef __cplusplus
}
#endif
