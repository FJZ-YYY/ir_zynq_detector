#pragma once

#include <cstdint>
#include <string>
#include <vector>

namespace irdet {

struct BoundingBox {
    std::uint16_t x1;
    std::uint16_t y1;
    std::uint16_t x2;
    std::uint16_t y2;
};

struct Detection {
    std::uint8_t class_id;
    std::string class_name;
    float score;
    BoundingBox bbox;
};

struct RuntimeConfig {
    std::uint32_t input_width = 160;
    std::uint32_t input_height = 128;
    float score_threshold = 0.35F;
    std::string model_path;
};

int run_detector(
    const std::string& image_path,
    const RuntimeConfig& cfg,
    std::vector<Detection>* out_detections);

void print_detections(const std::vector<Detection>& detections);

}  // namespace irdet

