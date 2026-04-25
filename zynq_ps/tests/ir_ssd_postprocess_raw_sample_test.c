#include <stdio.h>
#include <string.h>

#include "ir_ssd_postprocess.h"
#include "ir_ssd_raw_sample_data.h"

static int abs_i32(int value) {
    return value < 0 ? -value : value;
}

static int assert_true(int condition, const char* message) {
    if (!condition) {
        fprintf(stderr, "ASSERT FAILED: %s\n", message);
        return -1;
    }
    return 0;
}

static int compare_detection(
    const irdet_detection_t* det,
    uint32_t index) {
    const uint8_t expected_class = IRDET_SSD_RAW_SAMPLE_EXPECTED_CLASS_IDS[index];
    const uint16_t expected_score = IRDET_SSD_RAW_SAMPLE_EXPECTED_SCORE_X1000[index];
    const uint16_t* expected_box = &IRDET_SSD_RAW_SAMPLE_EXPECTED_BBOX_XYXY[index * IRDET_SSD_BOX_VALUES];

    if (assert_true(det->class_id == expected_class, "class id mismatch") != 0) {
        return -1;
    }
    if (assert_true(abs_i32((int)det->score_x1000 - (int)expected_score) <= 1, "score mismatch") != 0) {
        return -2;
    }
    if (assert_true(abs_i32((int)det->x1 - (int)expected_box[0]) <= 1, "x1 mismatch") != 0) {
        return -3;
    }
    if (assert_true(abs_i32((int)det->y1 - (int)expected_box[1]) <= 1, "y1 mismatch") != 0) {
        return -4;
    }
    if (assert_true(abs_i32((int)det->x2 - (int)expected_box[2]) <= 1, "x2 mismatch") != 0) {
        return -5;
    }
    if (assert_true(abs_i32((int)det->y2 - (int)expected_box[3]) <= 1, "y2 mismatch") != 0) {
        return -6;
    }
    return 0;
}

int main(void) {
    irdet_ssd_raw_head_tensors_t tensors;
    irdet_ssd_postprocess_config_t cfg;
    irdet_preprocess_stats_t pp_stats;
    irdet_detection_t detections[IRDET_MAX_DETECTIONS];
    uint32_t detection_count = 0U;
    uint32_t idx;
    int rc;

    memset(&pp_stats, 0, sizeof(pp_stats));
    pp_stats.src_width = IRDET_SSD_RAW_SAMPLE_SOURCE_WIDTH;
    pp_stats.src_height = IRDET_SSD_RAW_SAMPLE_SOURCE_HEIGHT;
    pp_stats.dst_width = IRDET_SSD_RAW_SAMPLE_MODEL_WIDTH;
    pp_stats.dst_height = IRDET_SSD_RAW_SAMPLE_MODEL_HEIGHT;

    irdet_ssd_postprocess_get_default_config(&cfg);
    cfg.input_width = IRDET_SSD_RAW_SAMPLE_MODEL_WIDTH;
    cfg.input_height = IRDET_SSD_RAW_SAMPLE_MODEL_HEIGHT;
    cfg.score_threshold_x1000 = IRDET_SSD_RAW_SAMPLE_SCORE_THRESH_X1000;
    cfg.iou_threshold_x1000 = IRDET_SSD_RAW_SAMPLE_IOU_THRESH_X1000;

    tensors.bbox_regression = IRDET_SSD_RAW_SAMPLE_BBOX_REGRESSION;
    tensors.cls_logits = IRDET_SSD_RAW_SAMPLE_CLS_LOGITS;
    tensors.anchors_xyxy = IRDET_SSD_RAW_SAMPLE_ANCHORS_XYXY;
    tensors.num_anchors = IRDET_SSD_RAW_SAMPLE_NUM_ANCHORS;
    tensors.num_classes_with_bg = IRDET_SSD_RAW_SAMPLE_NUM_CLASSES_WITH_BG;

    rc = irdet_ssd_postprocess_run(
        &tensors,
        &cfg,
        &pp_stats,
        detections,
        IRDET_MAX_DETECTIONS,
        &detection_count);
    if (rc != 0) {
        fprintf(stderr, "postprocess rc=%d\n", rc);
        return 1;
    }

    if (assert_true(detection_count == IRDET_SSD_RAW_SAMPLE_EXPECTED_COUNT, "detection count mismatch") != 0) {
        fprintf(stderr, "actual_count=%lu expected_count=%lu\n",
                (unsigned long)detection_count,
                (unsigned long)IRDET_SSD_RAW_SAMPLE_EXPECTED_COUNT);
        return 2;
    }

    for (idx = 0U; idx < detection_count; ++idx) {
        rc = compare_detection(&detections[idx], idx);
        if (rc != 0) {
            fprintf(stderr, "compare detection %lu rc=%d\n", (unsigned long)idx, rc);
            fprintf(
                stderr,
                "actual class=%u score=%u bbox=[%u,%u,%u,%u]\n",
                (unsigned int)detections[idx].class_id,
                (unsigned int)detections[idx].score_x1000,
                (unsigned int)detections[idx].x1,
                (unsigned int)detections[idx].y1,
                (unsigned int)detections[idx].x2,
                (unsigned int)detections[idx].y2);
            return 3;
        }
    }

    printf("Raw sample OK: image_id=%u count=%lu\n",
           (unsigned int)IRDET_SSD_RAW_SAMPLE_IMAGE_ID,
           (unsigned long)detection_count);
    for (idx = 0U; idx < detection_count; ++idx) {
        printf(
            "det%lu class=%s score=%u.%03u bbox=[%u,%u,%u,%u]\n",
            (unsigned long)idx,
            detections[idx].class_name,
            (unsigned int)(detections[idx].score_x1000 / 1000U),
            (unsigned int)(detections[idx].score_x1000 % 1000U),
            (unsigned int)detections[idx].x1,
            (unsigned int)detections[idx].y1,
            (unsigned int)detections[idx].x2,
            (unsigned int)detections[idx].y2);
    }
    return 0;
}
