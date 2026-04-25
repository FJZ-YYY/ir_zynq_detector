#include <stdio.h>
#include <string.h>

#include "ir_model_runner.h"
#include "ir_ssd_raw_sample_data.h"

static int assert_true(int condition, const char* message) {
    if (!condition) {
        fprintf(stderr, "ASSERT FAILED: %s\n", message);
        return -1;
    }
    return 0;
}

int main(void) {
    irdet_model_config_t cfg;
    irdet_model_runner_t runner;
    irdet_preprocess_stats_t pp_stats;
    irdet_detection_t detections[IRDET_MAX_DETECTIONS];
    float dummy_input[1] = { 0.0f };
    uint32_t detection_count = 0U;
    int rc;

    memset(&pp_stats, 0, sizeof(pp_stats));
    pp_stats.src_width = IRDET_SSD_RAW_SAMPLE_SOURCE_WIDTH;
    pp_stats.src_height = IRDET_SSD_RAW_SAMPLE_SOURCE_HEIGHT;
    pp_stats.dst_width = IRDET_SSD_RAW_SAMPLE_MODEL_WIDTH;
    pp_stats.dst_height = IRDET_SSD_RAW_SAMPLE_MODEL_HEIGHT;

    irdet_model_get_default_config(&cfg);
    cfg.backend = IRDET_MODEL_BACKEND_SSD_RAW_HEAD;
    cfg.input_width = IRDET_SSD_RAW_SAMPLE_MODEL_WIDTH;
    cfg.input_height = IRDET_SSD_RAW_SAMPLE_MODEL_HEIGHT;
    cfg.score_threshold_x1000 = IRDET_SSD_RAW_SAMPLE_SCORE_THRESH_X1000;
    cfg.iou_threshold_x1000 = IRDET_SSD_RAW_SAMPLE_IOU_THRESH_X1000;

    rc = irdet_model_runner_init(&runner, &cfg);
    if (rc != 0) {
        fprintf(stderr, "runner init rc=%d\n", rc);
        return 1;
    }

    rc = irdet_model_runner_run(
        &runner,
        dummy_input,
        cfg.input_width,
        cfg.input_height,
        &pp_stats,
        detections,
        IRDET_MAX_DETECTIONS,
        &detection_count);
    if (rc != 0) {
        fprintf(stderr, "runner run rc=%d\n", rc);
        return 2;
    }

    if (assert_true(detection_count == IRDET_SSD_RAW_SAMPLE_EXPECTED_COUNT, "raw sample count mismatch") != 0) {
        return 3;
    }
    if (assert_true(detections[0].class_id == IRDET_SSD_RAW_SAMPLE_EXPECTED_CLASS_IDS[0], "first class mismatch") != 0) {
        return 4;
    }
    if (assert_true(detections[0].score_x1000 == IRDET_SSD_RAW_SAMPLE_EXPECTED_SCORE_X1000[0], "first score mismatch") != 0) {
        return 5;
    }

    printf("Runner raw sample OK: backend=%s count=%lu first=%s score=%u.%03u bbox=[%u,%u,%u,%u]\n",
           irdet_model_backend_name(cfg.backend),
           (unsigned long)detection_count,
           detections[0].class_name,
           (unsigned int)(detections[0].score_x1000 / 1000U),
           (unsigned int)(detections[0].score_x1000 % 1000U),
           (unsigned int)detections[0].x1,
           (unsigned int)detections[0].y1,
           (unsigned int)detections[0].x2,
           (unsigned int)detections[0].y2);
    return 0;
}
