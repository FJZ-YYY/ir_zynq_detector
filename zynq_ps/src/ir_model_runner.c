#include "ir_model_runner.h"

#include "ir_detector_stub.h"
#include "ir_ssd_postprocess.h"
#include "ir_ssd_raw_sample_data.h"

#ifndef IRDET_MODEL_DEFAULT_BACKEND
#define IRDET_MODEL_DEFAULT_BACKEND  IRDET_MODEL_BACKEND_STUB
#endif

void irdet_model_get_default_config(irdet_model_config_t* cfg) {
    if (cfg == 0) {
        return;
    }

    cfg->backend = IRDET_MODEL_DEFAULT_BACKEND;
    if (cfg->backend == IRDET_MODEL_BACKEND_SSD_RAW_HEAD) {
        cfg->input_width = IRDET_SSD_RAW_SAMPLE_MODEL_WIDTH;
        cfg->input_height = IRDET_SSD_RAW_SAMPLE_MODEL_HEIGHT;
        cfg->score_threshold_x1000 = IRDET_SSD_RAW_SAMPLE_SCORE_THRESH_X1000;
        cfg->iou_threshold_x1000 = IRDET_SSD_RAW_SAMPLE_IOU_THRESH_X1000;
        return;
    }

    cfg->input_width = IRDET_MODEL_INPUT_W;
    cfg->input_height = IRDET_MODEL_INPUT_H;
    cfg->score_threshold_x1000 = 550U;
    cfg->iou_threshold_x1000 = 450U;
}

const char* irdet_model_backend_name(irdet_model_backend_t backend) {
    switch (backend) {
        case IRDET_MODEL_BACKEND_STUB:
            return "stub";
        case IRDET_MODEL_BACKEND_SSD_RAW_HEAD:
            return "ssd_raw_head";
        default:
            return "unknown";
    }
}

int irdet_model_runner_init(irdet_model_runner_t* runner, const irdet_model_config_t* cfg) {
    if (runner == 0 || cfg == 0) {
        return -1;
    }
    if (cfg->input_width == 0U || cfg->input_height == 0U) {
        return -2;
    }

    runner->cfg = *cfg;
    runner->is_initialized = 1U;
    return 0;
}

static int run_ssd_raw_head_sample_backend(
    const irdet_model_config_t* runner_cfg,
    irdet_detection_t* out_detections,
    uint32_t max_detections,
    uint32_t* out_count) {
    irdet_ssd_raw_head_tensors_t tensors;
    irdet_ssd_postprocess_config_t post_cfg;
    irdet_preprocess_stats_t sample_pp_stats;

    irdet_ssd_postprocess_get_default_config(&post_cfg);
    post_cfg.input_width = IRDET_SSD_RAW_SAMPLE_MODEL_WIDTH;
    post_cfg.input_height = IRDET_SSD_RAW_SAMPLE_MODEL_HEIGHT;
    post_cfg.score_threshold_x1000 = runner_cfg->score_threshold_x1000;
    post_cfg.iou_threshold_x1000 = runner_cfg->iou_threshold_x1000;

    sample_pp_stats.src_width = IRDET_SSD_RAW_SAMPLE_SOURCE_WIDTH;
    sample_pp_stats.src_height = IRDET_SSD_RAW_SAMPLE_SOURCE_HEIGHT;
    sample_pp_stats.dst_width = IRDET_SSD_RAW_SAMPLE_MODEL_WIDTH;
    sample_pp_stats.dst_height = IRDET_SSD_RAW_SAMPLE_MODEL_HEIGHT;
    sample_pp_stats.min_pixel = 0U;
    sample_pp_stats.max_pixel = 0U;
    sample_pp_stats.mean_x1000 = 0;

    tensors.bbox_regression = IRDET_SSD_RAW_SAMPLE_BBOX_REGRESSION;
    tensors.cls_logits = IRDET_SSD_RAW_SAMPLE_CLS_LOGITS;
    tensors.anchors_xyxy = IRDET_SSD_RAW_SAMPLE_ANCHORS_XYXY;
    tensors.num_anchors = IRDET_SSD_RAW_SAMPLE_NUM_ANCHORS;
    tensors.num_classes_with_bg = IRDET_SSD_RAW_SAMPLE_NUM_CLASSES_WITH_BG;

    return irdet_ssd_postprocess_run(
        &tensors,
        &post_cfg,
        &sample_pp_stats,
        out_detections,
        max_detections,
        out_count);
}

int irdet_model_runner_run(
    const irdet_model_runner_t* runner,
    const float* model_input,
    uint16_t input_width,
    uint16_t input_height,
    const irdet_preprocess_stats_t* pp_stats,
    irdet_detection_t* out_detections,
    uint32_t max_detections,
    uint32_t* out_count) {
    if (runner == 0 || model_input == 0 || pp_stats == 0 || out_detections == 0 || out_count == 0) {
        return -1;
    }
    if (runner->is_initialized == 0U) {
        *out_count = 0U;
        return -2;
    }

    switch (runner->cfg.backend) {
        case IRDET_MODEL_BACKEND_STUB:
            return irdet_stub_run(
                model_input,
                input_width,
                input_height,
                pp_stats,
                &runner->cfg,
                out_detections,
                max_detections,
                out_count);
        case IRDET_MODEL_BACKEND_SSD_RAW_HEAD:
            (void)model_input;
            (void)input_width;
            (void)input_height;
            (void)pp_stats;
            return run_ssd_raw_head_sample_backend(
                &runner->cfg,
                out_detections,
                max_detections,
                out_count);
        default:
            *out_count = 0U;
            return -3;
    }
}
