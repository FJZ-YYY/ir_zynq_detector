#include "ir_ssd_postprocess.h"

#include <math.h>
#include <stddef.h>
#include <stdlib.h>

typedef struct {
    uint8_t class_id;
    float score;
    float box[IRDET_SSD_BOX_VALUES];
} irdet_ssd_candidate_t;

static const char* k_irdet_ssd_class_names[IRDET_SSD_NUM_FG_CLASSES] = {
    "person",
    "bicycle",
    "car",
};

static float clampf(float value, float low, float high) {
    if (value < low) {
        return low;
    }
    if (value > high) {
        return high;
    }
    return value;
}

static uint16_t float_to_u16_pixel(float value, uint16_t max_value) {
    const float clamped = clampf(value, 0.0f, (float)max_value);
    return (uint16_t)(clamped + 0.5f);
}

static float compute_iou_xyxy(const float* a, const float* b) {
    float inter_x1;
    float inter_y1;
    float inter_x2;
    float inter_y2;
    float inter_w;
    float inter_h;
    float inter_area;
    float area_a;
    float area_b;
    float union_area;

    inter_x1 = (a[0] > b[0]) ? a[0] : b[0];
    inter_y1 = (a[1] > b[1]) ? a[1] : b[1];
    inter_x2 = (a[2] < b[2]) ? a[2] : b[2];
    inter_y2 = (a[3] < b[3]) ? a[3] : b[3];
    inter_w = inter_x2 - inter_x1;
    inter_h = inter_y2 - inter_y1;
    if (inter_w <= 0.0f || inter_h <= 0.0f) {
        return 0.0f;
    }

    inter_area = inter_w * inter_h;
    area_a = clampf(a[2] - a[0], 0.0f, 1.0e9f) * clampf(a[3] - a[1], 0.0f, 1.0e9f);
    area_b = clampf(b[2] - b[0], 0.0f, 1.0e9f) * clampf(b[3] - b[1], 0.0f, 1.0e9f);
    union_area = area_a + area_b - inter_area;
    if (union_area <= 1.0e-6f) {
        return 0.0f;
    }
    return inter_area / union_area;
}

static void softmax_logits(const float* logits, uint32_t count, float* probs_out) {
    uint32_t idx;
    float max_logit = logits[0];
    float sum_exp = 0.0f;

    for (idx = 1U; idx < count; ++idx) {
        if (logits[idx] > max_logit) {
            max_logit = logits[idx];
        }
    }

    for (idx = 0U; idx < count; ++idx) {
        probs_out[idx] = expf(logits[idx] - max_logit);
        sum_exp += probs_out[idx];
    }

    if (sum_exp <= 0.0f) {
        for (idx = 0U; idx < count; ++idx) {
            probs_out[idx] = 0.0f;
        }
        return;
    }

    for (idx = 0U; idx < count; ++idx) {
        probs_out[idx] /= sum_exp;
    }
}

static void decode_box_xyxy(
    const float* rel_codes,
    const float* anchor_xyxy,
    const float* weights,
    uint16_t input_width,
    uint16_t input_height,
    float* out_box) {
    const float width = anchor_xyxy[2] - anchor_xyxy[0];
    const float height = anchor_xyxy[3] - anchor_xyxy[1];
    const float ctr_x = anchor_xyxy[0] + 0.5f * width;
    const float ctr_y = anchor_xyxy[1] + 0.5f * height;
    const float dx = rel_codes[0] / weights[0];
    const float dy = rel_codes[1] / weights[1];
    const float dw = rel_codes[2] / weights[2];
    const float dh = rel_codes[3] / weights[3];
    const float dw_clamped = clampf(dw, -10.0f, 4.1351666f);
    const float dh_clamped = clampf(dh, -10.0f, 4.1351666f);
    const float pred_ctr_x = dx * width + ctr_x;
    const float pred_ctr_y = dy * height + ctr_y;
    const float pred_w = expf(dw_clamped) * width;
    const float pred_h = expf(dh_clamped) * height;
    const float half_w = 0.5f * pred_w;
    const float half_h = 0.5f * pred_h;
    const float x_max = (float)input_width;
    const float y_max = (float)input_height;

    out_box[0] = clampf(pred_ctr_x - half_w, 0.0f, x_max);
    out_box[1] = clampf(pred_ctr_y - half_h, 0.0f, y_max);
    out_box[2] = clampf(pred_ctr_x + half_w, 0.0f, x_max);
    out_box[3] = clampf(pred_ctr_y + half_h, 0.0f, y_max);
}

static void scale_box_to_source(
    const float* in_box,
    const irdet_preprocess_stats_t* pp_stats,
    uint16_t fallback_width,
    uint16_t fallback_height,
    float* out_box) {
    float src_w;
    float src_h;
    float dst_w;
    float dst_h;
    float scale_x = 1.0f;
    float scale_y = 1.0f;

    if (pp_stats != NULL && pp_stats->src_width > 0U && pp_stats->src_height > 0U) {
        src_w = (float)pp_stats->src_width;
        src_h = (float)pp_stats->src_height;
        dst_w = (float)((pp_stats->dst_width > 0U) ? pp_stats->dst_width : fallback_width);
        dst_h = (float)((pp_stats->dst_height > 0U) ? pp_stats->dst_height : fallback_height);
        if (dst_w > 0.0f) {
            scale_x = src_w / dst_w;
        }
        if (dst_h > 0.0f) {
            scale_y = src_h / dst_h;
        }
        out_box[0] = clampf(in_box[0] * scale_x, 0.0f, (float)(pp_stats->src_width - 1U));
        out_box[1] = clampf(in_box[1] * scale_y, 0.0f, (float)(pp_stats->src_height - 1U));
        out_box[2] = clampf(in_box[2] * scale_x, 0.0f, (float)(pp_stats->src_width - 1U));
        out_box[3] = clampf(in_box[3] * scale_y, 0.0f, (float)(pp_stats->src_height - 1U));
        return;
    }

    out_box[0] = clampf(in_box[0], 0.0f, (float)(fallback_width > 0U ? (fallback_width - 1U) : 0U));
    out_box[1] = clampf(in_box[1], 0.0f, (float)(fallback_height > 0U ? (fallback_height - 1U) : 0U));
    out_box[2] = clampf(in_box[2], 0.0f, (float)(fallback_width > 0U ? (fallback_width - 1U) : 0U));
    out_box[3] = clampf(in_box[3], 0.0f, (float)(fallback_height > 0U ? (fallback_height - 1U) : 0U));
}

static int compare_candidates_desc(const void* lhs, const void* rhs) {
    const irdet_ssd_candidate_t* a = (const irdet_ssd_candidate_t*)lhs;
    const irdet_ssd_candidate_t* b = (const irdet_ssd_candidate_t*)rhs;
    if (a->score < b->score) {
        return 1;
    }
    if (a->score > b->score) {
        return -1;
    }
    return 0;
}

static void maybe_push_candidate(
    irdet_ssd_candidate_t* candidates,
    uint32_t* candidate_count,
    uint8_t class_id,
    float score,
    const float* box) {
    uint32_t idx;
    uint32_t lowest_index = 0U;
    float lowest_score = 1.0e9f;

    if (*candidate_count < IRDET_SSD_MAX_CANDIDATES) {
        idx = *candidate_count;
        ++(*candidate_count);
        candidates[idx].class_id = class_id;
        candidates[idx].score = score;
        candidates[idx].box[0] = box[0];
        candidates[idx].box[1] = box[1];
        candidates[idx].box[2] = box[2];
        candidates[idx].box[3] = box[3];
        return;
    }

    for (idx = 0U; idx < *candidate_count; ++idx) {
        if (candidates[idx].score < lowest_score) {
            lowest_score = candidates[idx].score;
            lowest_index = idx;
        }
    }

    if (score <= lowest_score) {
        return;
    }

    candidates[lowest_index].class_id = class_id;
    candidates[lowest_index].score = score;
    candidates[lowest_index].box[0] = box[0];
    candidates[lowest_index].box[1] = box[1];
    candidates[lowest_index].box[2] = box[2];
    candidates[lowest_index].box[3] = box[3];
}

void irdet_ssd_postprocess_get_default_config(irdet_ssd_postprocess_config_t* cfg) {
    if (cfg == NULL) {
        return;
    }

    cfg->input_width = IRDET_MODEL_INPUT_W;
    cfg->input_height = IRDET_MODEL_INPUT_H;
    cfg->score_threshold_x1000 = 350U;
    cfg->iou_threshold_x1000 = 450U;
    cfg->box_coder_weights[0] = 10.0f;
    cfg->box_coder_weights[1] = 10.0f;
    cfg->box_coder_weights[2] = 5.0f;
    cfg->box_coder_weights[3] = 5.0f;
}

const char* irdet_ssd_class_name(uint8_t class_id) {
    if (class_id >= IRDET_SSD_NUM_FG_CLASSES) {
        return "unknown";
    }
    return k_irdet_ssd_class_names[class_id];
}

int irdet_ssd_postprocess_run(
    const irdet_ssd_raw_head_tensors_t* tensors,
    const irdet_ssd_postprocess_config_t* cfg,
    const irdet_preprocess_stats_t* pp_stats,
    irdet_detection_t* out_detections,
    uint32_t max_detections,
    uint32_t* out_count) {
    irdet_ssd_candidate_t candidates[IRDET_SSD_MAX_CANDIDATES];
    float kept_model_boxes[IRDET_MAX_DETECTIONS][IRDET_SSD_BOX_VALUES];
    float probs[IRDET_SSD_NUM_CLASSES_WITH_BG];
    uint32_t candidate_count = 0U;
    uint32_t idx;
    uint32_t det_count = 0U;
    float score_threshold;
    float iou_threshold;

    if (out_count == NULL) {
        return -1;
    }
    *out_count = 0U;

    if (tensors == NULL || cfg == NULL || out_detections == NULL) {
        return -2;
    }
    if (tensors->bbox_regression == NULL || tensors->cls_logits == NULL || tensors->anchors_xyxy == NULL) {
        return -3;
    }
    if (tensors->num_classes_with_bg != IRDET_SSD_NUM_CLASSES_WITH_BG || cfg->input_width == 0U || cfg->input_height == 0U) {
        return -4;
    }

    score_threshold = (float)cfg->score_threshold_x1000 / 1000.0f;
    iou_threshold = (float)cfg->iou_threshold_x1000 / 1000.0f;

    for (idx = 0U; idx < tensors->num_anchors; ++idx) {
        const float* rel_codes = &tensors->bbox_regression[idx * IRDET_SSD_BOX_VALUES];
        const float* logits = &tensors->cls_logits[idx * tensors->num_classes_with_bg];
        const float* anchor = &tensors->anchors_xyxy[idx * IRDET_SSD_BOX_VALUES];
        float decoded_box[IRDET_SSD_BOX_VALUES];
        uint32_t class_idx;

        softmax_logits(logits, tensors->num_classes_with_bg, probs);
        decode_box_xyxy(rel_codes, anchor, cfg->box_coder_weights, cfg->input_width, cfg->input_height, decoded_box);

        for (class_idx = 1U; class_idx < tensors->num_classes_with_bg; ++class_idx) {
            if (probs[class_idx] < score_threshold) {
                continue;
            }
            maybe_push_candidate(
                candidates,
                &candidate_count,
                (uint8_t)(class_idx - 1U),
                probs[class_idx],
                decoded_box);
        }
    }

    if (candidate_count == 0U) {
        return 0;
    }

    qsort(candidates, candidate_count, sizeof(candidates[0]), compare_candidates_desc);
    for (idx = 0U; idx < candidate_count && det_count < max_detections; ++idx) {
        uint32_t kept_idx;
        int keep = 1;
        float scaled_box[IRDET_SSD_BOX_VALUES];

        for (kept_idx = 0U; kept_idx < det_count; ++kept_idx) {
            if (out_detections[kept_idx].class_id != candidates[idx].class_id) {
                continue;
            }

            if (compute_iou_xyxy(candidates[idx].box, kept_model_boxes[kept_idx]) > iou_threshold) {
                keep = 0;
                break;
            }
        }

        if (keep == 0) {
            continue;
        }

        scale_box_to_source(candidates[idx].box, pp_stats, cfg->input_width, cfg->input_height, scaled_box);
        kept_model_boxes[det_count][0] = candidates[idx].box[0];
        kept_model_boxes[det_count][1] = candidates[idx].box[1];
        kept_model_boxes[det_count][2] = candidates[idx].box[2];
        kept_model_boxes[det_count][3] = candidates[idx].box[3];
        out_detections[det_count].class_id = candidates[idx].class_id;
        out_detections[det_count].class_name = irdet_ssd_class_name(candidates[idx].class_id);
        out_detections[det_count].score_x1000 = (uint16_t)(candidates[idx].score * 1000.0f + 0.5f);
        out_detections[det_count].x1 = float_to_u16_pixel(
            scaled_box[0],
            (pp_stats != NULL && pp_stats->src_width > 0U) ? (uint16_t)(pp_stats->src_width - 1U) : (uint16_t)(cfg->input_width - 1U));
        out_detections[det_count].y1 = float_to_u16_pixel(
            scaled_box[1],
            (pp_stats != NULL && pp_stats->src_height > 0U) ? (uint16_t)(pp_stats->src_height - 1U) : (uint16_t)(cfg->input_height - 1U));
        out_detections[det_count].x2 = float_to_u16_pixel(
            scaled_box[2],
            (pp_stats != NULL && pp_stats->src_width > 0U) ? (uint16_t)(pp_stats->src_width - 1U) : (uint16_t)(cfg->input_width - 1U));
        out_detections[det_count].y2 = float_to_u16_pixel(
            scaled_box[3],
            (pp_stats != NULL && pp_stats->src_height > 0U) ? (uint16_t)(pp_stats->src_height - 1U) : (uint16_t)(cfg->input_height - 1U));
        ++det_count;
    }

    *out_count = det_count;
    return 0;
}
