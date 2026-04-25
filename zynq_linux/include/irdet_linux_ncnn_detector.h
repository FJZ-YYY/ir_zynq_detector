#pragma once

#include <stdint.h>

#include <vector>

#include "ir_model_runner.h"

struct irdet_linux_runtime_config_t {
    uint16_t runtime_input_width;
    uint16_t runtime_input_height;
    uint16_t score_threshold_x1000;
    uint16_t iou_threshold_x1000;
    uint16_t max_detections;
    float input_scale;
    float mean;
    float stddev;
};

struct irdet_linux_blob_tensor_t {
    std::vector<float> values;
    int dims;
    int w;
    int h;
    int c;
};

class irdet_linux_ncnn_detector {
public:
    irdet_linux_ncnn_detector();
    ~irdet_linux_ncnn_detector();

    int load(
        const char* param_path,
        const char* bin_path,
        const char* anchors_path,
        const irdet_linux_runtime_config_t* cfg);

    int run_from_gray8(
        const uint8_t* gray8,
        uint16_t src_width,
        uint16_t src_height,
        irdet_detection_t* out_detections,
        uint32_t max_detections,
        uint32_t* out_count,
        irdet_preprocess_stats_t* out_stats);

    int run_from_gray8_with_blob_override(
        const uint8_t* gray8,
        uint16_t src_width,
        uint16_t src_height,
        const char* override_blob_name,
        const irdet_linux_blob_tensor_t* override_blob,
        irdet_detection_t* out_detections,
        uint32_t max_detections,
        uint32_t* out_count,
        irdet_preprocess_stats_t* out_stats);

    int run_from_runtime_tensor(
        const float* runtime_input,
        uint16_t src_width,
        uint16_t src_height,
        irdet_detection_t* out_detections,
        uint32_t max_detections,
        uint32_t* out_count,
        irdet_preprocess_stats_t* out_stats);

    int run_from_runtime_tensor_with_blob_override(
        const float* runtime_input,
        uint16_t src_width,
        uint16_t src_height,
        const char* override_blob_name,
        const irdet_linux_blob_tensor_t* override_blob,
        irdet_detection_t* out_detections,
        uint32_t max_detections,
        uint32_t* out_count,
        irdet_preprocess_stats_t* out_stats);

    int extract_blob_from_gray8(
        const uint8_t* gray8,
        uint16_t src_width,
        uint16_t src_height,
        const char* blob_name,
        irdet_linux_blob_tensor_t* out_blob,
        irdet_preprocess_stats_t* out_stats);

    int extract_blob_from_runtime_tensor(
        const float* runtime_input,
        uint16_t src_width,
        uint16_t src_height,
        const char* blob_name,
        irdet_linux_blob_tensor_t* out_blob,
        irdet_preprocess_stats_t* out_stats);

    const irdet_linux_runtime_config_t& config() const;
    uint32_t num_anchors() const;
    int last_ncnn_status() const;
    int last_postprocess_status() const;

private:
    class impl;
    impl* p_;
};

void irdet_linux_runtime_get_default_config(irdet_linux_runtime_config_t* cfg);
