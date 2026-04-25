#include "detector_app.h"

#include <fstream>
#include <iomanip>
#include <iostream>
#include <string>
#include <vector>

namespace irdet {

namespace {

bool try_get_file_size(const std::string& image_path, std::uintmax_t* out_size) {
    if (out_size == nullptr) {
        return false;
    }

    std::ifstream input(image_path, std::ios::binary | std::ios::ate);
    if (!input) {
        return false;
    }

    const std::streampos end_pos = input.tellg();
    if (end_pos < 0) {
        return false;
    }

    *out_size = static_cast<std::uintmax_t>(end_pos);
    return true;
}

BoundingBox make_stub_bbox(std::uintmax_t file_size) {
    const std::uint16_t offset = static_cast<std::uint16_t>(file_size % 24U);
    return BoundingBox{
        static_cast<std::uint16_t>(12U + offset),
        static_cast<std::uint16_t>(10U + (offset / 2U)),
        static_cast<std::uint16_t>(88U + offset),
        static_cast<std::uint16_t>(70U + offset),
    };
}

const char* choose_stub_class(std::uintmax_t file_size) {
    switch (file_size % 3U) {
        case 0U:
            return "person";
        case 1U:
            return "bicycle";
        default:
            return "car";
    }
}

}  // namespace

int run_detector(
    const std::string& image_path,
    const RuntimeConfig& cfg,
    std::vector<Detection>* out_detections) {
    if (out_detections == nullptr) {
        return -2;
    }

    out_detections->clear();

    std::uintmax_t file_size = 0U;
    if (!try_get_file_size(image_path, &file_size)) {
        return -1;
    }

    const float score = 0.55F + static_cast<float>(file_size % 20U) / 100.0F;
    if (score < cfg.score_threshold) {
        return 0;
    }

    Detection det{};
    det.class_id = static_cast<std::uint8_t>(file_size % 3U);
    det.class_name = choose_stub_class(file_size);
    det.score = score;
    det.bbox = make_stub_bbox(file_size);
    out_detections->push_back(det);
    return 0;
}

void print_detections(const std::vector<Detection>& detections) {
    if (detections.empty()) {
        std::cout << "No detections above threshold.\n";
        return;
    }

    for (const auto& det : detections) {
        std::cout << "class=" << det.class_name << " "
                  << "score=" << std::fixed << std::setprecision(4) << det.score << " "
                  << "bbox=[" << det.bbox.x1 << ", " << det.bbox.y1 << ", " << det.bbox.x2
                  << ", " << det.bbox.y2 << "]\n";
    }
}

}  // namespace irdet

int main(int argc, char* argv[]) {
    if (argc < 2) {
        std::cerr << "Usage: ps_stub <image_path> [model_path]\n";
        return 1;
    }

    irdet::RuntimeConfig cfg{};
    if (argc >= 3) {
        cfg.model_path = argv[2];
    }

    std::vector<irdet::Detection> detections;
    const int rc = irdet::run_detector(argv[1], cfg, &detections);
    if (rc == -1) {
        std::cerr << "Input image not found: " << argv[1] << "\n";
        return 2;
    }
    if (rc != 0) {
        std::cerr << "Detector failed, rc=" << rc << "\n";
        return 3;
    }

    std::cout << "[stub] model_path=" << (cfg.model_path.empty() ? "<unset>" : cfg.model_path) << "\n";
    irdet::print_detections(detections);
    return 0;
}
