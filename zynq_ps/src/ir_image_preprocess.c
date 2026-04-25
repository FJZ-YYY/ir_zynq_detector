#include "ir_image_preprocess.h"

#include <stddef.h>
#include <stdint.h>

static uint16_t clamp_u16(int value, uint16_t max_value) {
    if (value < 0) {
        return 0U;
    }
    if ((uint32_t)value > (uint32_t)max_value) {
        return max_value;
    }
    return (uint16_t)value;
}

static float sample_gray8_bilinear(
    const uint8_t* src,
    uint16_t src_width,
    uint16_t src_height,
    float src_x,
    float src_y) {
    const uint16_t max_x = (uint16_t)(src_width - 1U);
    const uint16_t max_y = (uint16_t)(src_height - 1U);

    const int x0_i = (int)src_x;
    const int y0_i = (int)src_y;
    const int x1_i = x0_i + 1;
    const int y1_i = y0_i + 1;

    const uint16_t x0 = clamp_u16(x0_i, max_x);
    const uint16_t y0 = clamp_u16(y0_i, max_y);
    const uint16_t x1 = clamp_u16(x1_i, max_x);
    const uint16_t y1 = clamp_u16(y1_i, max_y);

    const float wx = src_x - (float)x0_i;
    const float wy = src_y - (float)y0_i;

    const float p00 = (float)src[(uint32_t)y0 * src_width + x0];
    const float p01 = (float)src[(uint32_t)y0 * src_width + x1];
    const float p10 = (float)src[(uint32_t)y1 * src_width + x0];
    const float p11 = (float)src[(uint32_t)y1 * src_width + x1];

    const float top = p00 + (p01 - p00) * wx;
    const float bot = p10 + (p11 - p10) * wx;
    return top + (bot - top) * wy;
}

void irdet_preprocess_get_default_config(irdet_preprocess_config_t* cfg) {
    if (cfg == NULL) {
        return;
    }

    cfg->input_scale = 1.0F / 255.0F;
    cfg->mean = 0.0F;
    cfg->stddev = 1.0F;
}

int irdet_preprocess_gray8_image(
    const uint8_t* src,
    uint16_t src_width,
    uint16_t src_height,
    const irdet_preprocess_config_t* cfg,
    float* dst,
    uint16_t dst_width,
    uint16_t dst_height,
    irdet_preprocess_stats_t* stats) {
    int64_t sum_x1000 = 0;
    uint8_t min_pixel = 255U;
    uint8_t max_pixel = 0U;
    uint16_t y;
    uint16_t x;
    float scale;
    float mean;
    float stddev;

    if (src == NULL || cfg == NULL || dst == NULL || stats == NULL) {
        return -1;
    }
    if (src_width == 0U || src_height == 0U || dst_width == 0U || dst_height == 0U) {
        return -2;
    }
    if (cfg->stddev == 0.0F) {
        return -3;
    }

    scale = cfg->input_scale;
    mean = cfg->mean;
    stddev = cfg->stddev;

    for (y = 0U; y < dst_height; ++y) {
        const float src_y = (((float)y + 0.5F) * (float)src_height / (float)dst_height) - 0.5F;
        for (x = 0U; x < dst_width; ++x) {
            const float src_x = (((float)x + 0.5F) * (float)src_width / (float)dst_width) - 0.5F;
            const float raw_pixel = sample_gray8_bilinear(src, src_width, src_height, src_x, src_y);
            uint8_t raw_u8;
            float norm_value;
            uint32_t dst_index;

            if (raw_pixel <= 0.0F) {
                raw_u8 = 0U;
            } else if (raw_pixel >= 255.0F) {
                raw_u8 = 255U;
            } else {
                raw_u8 = (uint8_t)(raw_pixel + 0.5F);
            }

            if (raw_u8 < min_pixel) {
                min_pixel = raw_u8;
            }
            if (raw_u8 > max_pixel) {
                max_pixel = raw_u8;
            }

            norm_value = ((raw_pixel * scale) - mean) / stddev;
            dst_index = (uint32_t)y * dst_width + x;
            dst[dst_index] = norm_value;

            if (norm_value >= 0.0F) {
                sum_x1000 += (int32_t)(norm_value * 1000.0F + 0.5F);
            } else {
                sum_x1000 += (int32_t)(norm_value * 1000.0F - 0.5F);
            }
        }
    }

    stats->src_width = src_width;
    stats->src_height = src_height;
    stats->dst_width = dst_width;
    stats->dst_height = dst_height;
    stats->min_pixel = min_pixel;
    stats->max_pixel = max_pixel;
    stats->mean_x1000 = (int32_t)(sum_x1000 / ((uint32_t)dst_width * dst_height));
    return 0;
}
