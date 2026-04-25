#include "ir_detector_stub.h"

static uint16_t clamp_u16_range(uint32_t value, uint16_t min_value, uint16_t max_value) {
    if (value < (uint32_t)min_value) {
        return min_value;
    }
    if (value > (uint32_t)max_value) {
        return max_value;
    }
    return (uint16_t)value;
}

static uint16_t clamp_box_coord(int32_t value, uint16_t max_value) {
    if (value < 0) {
        return 0U;
    }
    if ((uint32_t)value > (uint32_t)max_value) {
        return max_value;
    }
    return (uint16_t)value;
}

static uint8_t choose_class_id(float center_value, uint8_t dynamic_range) {
    if (center_value >= 0.55F) {
        return 0U;
    }
    if (dynamic_range >= 96U) {
        return 2U;
    }
    return 1U;
}

static const char* choose_class_name(uint8_t class_id) {
    static const char* kClassNames[3] = {
        "person",
        "bicycle",
        "car",
    };

    if (class_id >= 3U) {
        return "unknown";
    }
    return kClassNames[class_id];
}

int irdet_stub_run(
    const float* model_input,
    uint16_t input_width,
    uint16_t input_height,
    const irdet_preprocess_stats_t* pp_stats,
    const irdet_model_config_t* cfg,
    irdet_detection_t* out_detections,
    uint32_t max_detections,
    uint32_t* out_count) {
    uint32_t center_index;
    float center_value;
    uint8_t dynamic_range;
    uint8_t class_id;
    uint16_t score_x1000;
    uint16_t box_w;
    uint16_t box_h;
    uint16_t center_x;
    uint16_t center_y;
    int32_t offset_x;
    int32_t offset_y;
    int32_t x1;
    int32_t y1;
    int32_t x2;
    int32_t y2;

    if (model_input == 0 || pp_stats == 0 || cfg == 0 || out_detections == 0 || out_count == 0) {
        return -1;
    }
    if (input_width == 0U || input_height == 0U || max_detections == 0U) {
        return -2;
    }

    *out_count = 0U;
    center_index = ((uint32_t)input_height / 2U) * input_width + ((uint32_t)input_width / 2U);
    center_value = model_input[center_index];
    dynamic_range = (uint8_t)(pp_stats->max_pixel - pp_stats->min_pixel);
    class_id = choose_class_id(center_value, dynamic_range);

    score_x1000 = 520U
        + clamp_u16_range((uint32_t)(center_value * 220.0F + 0.5F), 0U, 220U)
        + clamp_u16_range((uint32_t)dynamic_range, 0U, 180U);
    if (score_x1000 > 990U) {
        score_x1000 = 990U;
    }
    if (score_x1000 < cfg->score_threshold_x1000) {
        return 0;
    }

    box_w = (uint16_t)(input_width / 4U + ((uint32_t)dynamic_range * input_width) / 1020U);
    box_h = (uint16_t)(input_height / 4U + ((uint32_t)dynamic_range * input_height) / 1275U);
    box_w = clamp_u16_range(box_w, input_width / 6U, input_width - 1U);
    box_h = clamp_u16_range(box_h, input_height / 6U, input_height - 1U);

    center_x = (uint16_t)(input_width / 2U);
    center_y = (uint16_t)(input_height / 2U);
    offset_x = (int32_t)(pp_stats->max_pixel % 9U) - 4;
    offset_y = (int32_t)(pp_stats->min_pixel % 7U) - 3;

    x1 = (int32_t)center_x + offset_x - (int32_t)(box_w / 2U);
    y1 = (int32_t)center_y + offset_y - (int32_t)(box_h / 2U);
    x2 = x1 + (int32_t)box_w;
    y2 = y1 + (int32_t)box_h;

    out_detections[0].class_id = class_id;
    out_detections[0].class_name = choose_class_name(class_id);
    out_detections[0].score_x1000 = score_x1000;
    out_detections[0].x1 = clamp_box_coord(x1, (uint16_t)(input_width - 1U));
    out_detections[0].y1 = clamp_box_coord(y1, (uint16_t)(input_height - 1U));
    out_detections[0].x2 = clamp_box_coord(x2, (uint16_t)(input_width - 1U));
    out_detections[0].y2 = clamp_box_coord(y2, (uint16_t)(input_height - 1U));
    *out_count = 1U;
    return 0;
}
