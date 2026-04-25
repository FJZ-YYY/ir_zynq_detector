#include <stdio.h>
#include <string.h>

#include "ir_ssd_postprocess.h"

static int assert_true(int condition, const char* message) {
    if (!condition) {
        fprintf(stderr, "ASSERT FAILED: %s\n", message);
        return -1;
    }
    return 0;
}

int main(void) {
    static const float bbox_regression[3U * IRDET_SSD_BOX_VALUES] = {
        0.0f, 0.0f, 0.0f, 0.0f,
        0.0f, 0.0f, 0.0f, 0.0f,
        0.0f, 0.0f, 0.0f, 0.0f,
    };
    static const float cls_logits[3U * IRDET_SSD_NUM_CLASSES_WITH_BG] = {
        0.0f, 5.0f, 1.0f, -1.0f,
        0.0f, 3.2f, 0.2f, -1.0f,
        0.0f, -1.0f, 0.2f, 5.4f,
    };
    static const float anchors_xyxy[3U * IRDET_SSD_BOX_VALUES] = {
        10.0f, 10.0f, 30.0f, 30.0f,
        12.0f, 12.0f, 32.0f, 32.0f,
        50.0f, 40.0f, 90.0f, 80.0f,
    };
    irdet_ssd_raw_head_tensors_t tensors;
    irdet_ssd_postprocess_config_t cfg;
    irdet_preprocess_stats_t pp_stats;
    irdet_detection_t detections[IRDET_MAX_DETECTIONS];
    uint32_t detection_count = 0U;
    int found_person = 0;
    int found_car = 0;
    uint32_t idx;
    int rc;

    memset(&pp_stats, 0, sizeof(pp_stats));
    pp_stats.src_width = 320U;
    pp_stats.src_height = 256U;
    pp_stats.dst_width = 160U;
    pp_stats.dst_height = 128U;

    irdet_ssd_postprocess_get_default_config(&cfg);
    cfg.score_threshold_x1000 = 350U;
    cfg.iou_threshold_x1000 = 450U;

    tensors.bbox_regression = bbox_regression;
    tensors.cls_logits = cls_logits;
    tensors.anchors_xyxy = anchors_xyxy;
    tensors.num_anchors = 3U;
    tensors.num_classes_with_bg = IRDET_SSD_NUM_CLASSES_WITH_BG;

    rc = irdet_ssd_postprocess_run(&tensors, &cfg, &pp_stats, detections, IRDET_MAX_DETECTIONS, &detection_count);
    if (rc != 0) {
        fprintf(stderr, "postprocess rc=%d\n", rc);
        return 1;
    }

    if (assert_true(detection_count == 2U, "expected 2 detections after class-wise NMS") != 0) {
        return 2;
    }

    for (idx = 0U; idx < detection_count; ++idx) {
        if (detections[idx].class_id == 0U) {
            found_person = 1;
            if (assert_true(
                    detections[idx].x1 == 20U && detections[idx].y1 == 20U &&
                    detections[idx].x2 == 60U && detections[idx].y2 == 60U,
                    "person box should scale to source space") != 0) {
                return 3;
            }
        } else if (detections[idx].class_id == 2U) {
            found_car = 1;
            if (assert_true(
                    detections[idx].x1 == 100U && detections[idx].y1 == 80U &&
                    detections[idx].x2 == 180U && detections[idx].y2 == 160U,
                    "car box should scale to source space") != 0) {
                return 4;
            }
        }
    }

    if (assert_true(found_person != 0, "expected one person detection") != 0) {
        return 5;
    }
    if (assert_true(found_car != 0, "expected one car detection") != 0) {
        return 6;
    }

    printf("Smoke OK: count=%lu\n", (unsigned long)detection_count);
    printf(
        "det0 class=%s score=%u.%03u bbox=[%u,%u,%u,%u]\n",
        detections[0].class_name,
        (unsigned int)(detections[0].score_x1000 / 1000U),
        (unsigned int)(detections[0].score_x1000 % 1000U),
        (unsigned int)detections[0].x1,
        (unsigned int)detections[0].y1,
        (unsigned int)detections[0].x2,
        (unsigned int)detections[0].y2);
    printf(
        "det1 class=%s score=%u.%03u bbox=[%u,%u,%u,%u]\n",
        detections[1].class_name,
        (unsigned int)(detections[1].score_x1000 / 1000U),
        (unsigned int)(detections[1].score_x1000 % 1000U),
        (unsigned int)detections[1].x1,
        (unsigned int)detections[1].y1,
        (unsigned int)detections[1].x2,
        (unsigned int)detections[1].y2);
    return 0;
}
