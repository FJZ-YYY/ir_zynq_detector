#pragma once

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define IRDET_MODEL_INPUT_W      160U
#define IRDET_MODEL_INPUT_H      128U
#define IRDET_MODEL_INPUT_ELEMS  (IRDET_MODEL_INPUT_W * IRDET_MODEL_INPUT_H)

typedef struct {
    float input_scale;
    float mean;
    float stddev;
} irdet_preprocess_config_t;

typedef struct {
    uint16_t src_width;
    uint16_t src_height;
    uint16_t dst_width;
    uint16_t dst_height;
    uint8_t min_pixel;
    uint8_t max_pixel;
    int32_t mean_x1000;
} irdet_preprocess_stats_t;

void irdet_preprocess_get_default_config(irdet_preprocess_config_t* cfg);
int irdet_preprocess_gray8_image(
    const uint8_t* src,
    uint16_t src_width,
    uint16_t src_height,
    const irdet_preprocess_config_t* cfg,
    float* dst,
    uint16_t dst_width,
    uint16_t dst_height,
    irdet_preprocess_stats_t* stats);

#ifdef __cplusplus
}
#endif
