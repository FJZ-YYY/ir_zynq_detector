#include "irdet_linux_ncnn_detector.h"

#include <stddef.h>
#include <stdint.h>

#include <fstream>
#include <memory>
#include <stdexcept>
#include <string>
#include <vector>

#include "ir_image_preprocess.h"
#include "ir_ssd_postprocess.h"
#include "net.h"

namespace {

std::vector<uint8_t> read_binary_file(const char* path) {
    std::ifstream stream(path, std::ios::binary);
    if (!stream) {
        throw std::runtime_error(std::string("failed to open file: ") + path);
    }
    stream.seekg(0, std::ios::end);
    const std::streamoff bytes = stream.tellg();
    stream.seekg(0, std::ios::beg);
    if (bytes < 0) {
        throw std::runtime_error(std::string("failed to measure file: ") + path);
    }
    std::vector<uint8_t> data(static_cast<size_t>(bytes));
    if (!data.empty()) {
        stream.read(reinterpret_cast<char*>(data.data()), bytes);
        if (!stream) {
            throw std::runtime_error(std::string("failed to read file: ") + path);
        }
    }
    return data;
}

std::vector<float> read_float_file(const char* path) {
    std::vector<uint8_t> bytes = read_binary_file(path);
    if ((bytes.size() % sizeof(float)) != 0U) {
        throw std::runtime_error(std::string("float32 file size mismatch: ") + path);
    }
    std::vector<float> values(bytes.size() / sizeof(float));
    if (!values.empty()) {
        memcpy(values.data(), bytes.data(), bytes.size());
    }
    return values;
}

std::vector<float> mat_to_float_vector(const ncnn::Mat& mat) {
    const size_t count = mat.total();
    const float* data = reinterpret_cast<const float*>(mat.data);
    if (data == NULL && count != 0U) {
        throw std::runtime_error("ncnn output tensor is empty");
    }
    return std::vector<float>(data, data + count);
}

irdet_linux_blob_tensor_t mat_to_blob_tensor(const ncnn::Mat& mat) {
    irdet_linux_blob_tensor_t blob;
    blob.values = mat_to_float_vector(mat);
    blob.dims = mat.dims;
    blob.w = mat.w;
    blob.h = mat.h;
    blob.c = mat.c;
    return blob;
}

}  // namespace

class irdet_linux_ncnn_detector::impl {
public:
    ncnn::Net net;
    irdet_linux_runtime_config_t cfg;
    std::vector<float> anchors_xyxy;
    std::vector<float> runtime_tensor;
    int last_ncnn_status = 0;
    int last_postprocess_status = 0;
    bool is_loaded = false;
};

void irdet_linux_runtime_get_default_config(irdet_linux_runtime_config_t* cfg) {
    if (cfg == NULL) {
        return;
    }

    cfg->runtime_input_width = 160U;
    cfg->runtime_input_height = 128U;
    cfg->score_threshold_x1000 = 200U;
    cfg->iou_threshold_x1000 = 450U;
    cfg->max_detections = IRDET_MAX_DETECTIONS;
    cfg->input_scale = 1.0f / 255.0f;
    cfg->mean = 0.5f;
    cfg->stddev = 0.5f;
}

irdet_linux_ncnn_detector::irdet_linux_ncnn_detector() : p_(new impl()) {
    irdet_linux_runtime_get_default_config(&p_->cfg);
}

irdet_linux_ncnn_detector::~irdet_linux_ncnn_detector() {
    delete p_;
}

int irdet_linux_ncnn_detector::load(
    const char* param_path,
    const char* bin_path,
    const char* anchors_path,
    const irdet_linux_runtime_config_t* cfg) {
    if (param_path == NULL || bin_path == NULL || anchors_path == NULL || cfg == NULL) {
        return -1;
    }

    try {
        p_->cfg = *cfg;
        p_->anchors_xyxy = read_float_file(anchors_path);
        if ((p_->anchors_xyxy.size() % IRDET_SSD_BOX_VALUES) != 0U) {
            return -2;
        }

        p_->net.clear();
        p_->net.opt.lightmode = true;
        p_->net.opt.num_threads = 1;
        p_->net.opt.use_packing_layout = false;
#if NCNN_VULKAN
        p_->net.opt.use_vulkan_compute = false;
#endif
        p_->last_ncnn_status = p_->net.load_param(param_path);
        if (p_->last_ncnn_status != 0) {
            return -3;
        }
        p_->last_ncnn_status = p_->net.load_model(bin_path);
        if (p_->last_ncnn_status != 0) {
            return -4;
        }

        p_->runtime_tensor.resize(
            (size_t)p_->cfg.runtime_input_width * (size_t)p_->cfg.runtime_input_height);
        p_->last_postprocess_status = 0;
        p_->is_loaded = true;
        return 0;
    } catch (const std::exception&) {
        p_->is_loaded = false;
        return -5;
    }
}

int irdet_linux_ncnn_detector::run_from_gray8(
    const uint8_t* gray8,
    uint16_t src_width,
    uint16_t src_height,
    irdet_detection_t* out_detections,
    uint32_t max_detections,
    uint32_t* out_count,
    irdet_preprocess_stats_t* out_stats) {
    irdet_preprocess_config_t pp_cfg;
    int rc;

    if (!p_->is_loaded || gray8 == NULL || out_detections == NULL || out_count == NULL || out_stats == NULL) {
        return -1;
    }

    pp_cfg.input_scale = p_->cfg.input_scale;
    pp_cfg.mean = p_->cfg.mean;
    pp_cfg.stddev = p_->cfg.stddev;
    rc = irdet_preprocess_gray8_image(
        gray8,
        src_width,
        src_height,
        &pp_cfg,
        p_->runtime_tensor.data(),
        p_->cfg.runtime_input_width,
        p_->cfg.runtime_input_height,
        out_stats);
    if (rc != 0) {
        return -2;
    }

    return run_from_runtime_tensor(
        p_->runtime_tensor.data(),
        src_width,
        src_height,
        out_detections,
        max_detections,
        out_count,
        out_stats);
}

int irdet_linux_ncnn_detector::run_from_runtime_tensor(
    const float* runtime_input,
    uint16_t src_width,
    uint16_t src_height,
    irdet_detection_t* out_detections,
    uint32_t max_detections,
    uint32_t* out_count,
    irdet_preprocess_stats_t* out_stats) {
    ncnn::Mat input;
    ncnn::Mat bbox_out;
    ncnn::Mat cls_out;
    std::vector<float> bbox_values;
    std::vector<float> cls_values;
    irdet_ssd_postprocess_config_t pp_cfg;
    irdet_ssd_raw_head_tensors_t tensors;

    if (!p_->is_loaded || runtime_input == NULL || out_detections == NULL || out_count == NULL || out_stats == NULL) {
        return -1;
    }

    out_stats->src_width = src_width;
    out_stats->src_height = src_height;
    out_stats->dst_width = p_->cfg.runtime_input_width;
    out_stats->dst_height = p_->cfg.runtime_input_height;

    input = ncnn::Mat(
        p_->cfg.runtime_input_width,
        p_->cfg.runtime_input_height,
        1,
        const_cast<float*>(runtime_input),
        (size_t)sizeof(float));
    ncnn::Extractor extractor = p_->net.create_extractor();
    extractor.set_light_mode(true);

    p_->last_ncnn_status = extractor.input("input_0", input);
    if (p_->last_ncnn_status != 0) {
        return -2;
    }
    p_->last_ncnn_status = extractor.extract("bbox_regression", bbox_out);
    if (p_->last_ncnn_status != 0) {
        return -3;
    }
    p_->last_ncnn_status = extractor.extract("cls_logits", cls_out);
    if (p_->last_ncnn_status != 0) {
        return -4;
    }

    try {
        bbox_values = mat_to_float_vector(bbox_out);
        cls_values = mat_to_float_vector(cls_out);
    } catch (const std::exception&) {
        return -5;
    }

    irdet_ssd_postprocess_get_default_config(&pp_cfg);
    pp_cfg.input_width = p_->cfg.runtime_input_width;
    pp_cfg.input_height = p_->cfg.runtime_input_height;
    pp_cfg.score_threshold_x1000 = p_->cfg.score_threshold_x1000;
    pp_cfg.iou_threshold_x1000 = p_->cfg.iou_threshold_x1000;

    tensors.bbox_regression = bbox_values.data();
    tensors.cls_logits = cls_values.data();
    tensors.anchors_xyxy = p_->anchors_xyxy.data();
    tensors.num_anchors = (uint32_t)(p_->anchors_xyxy.size() / IRDET_SSD_BOX_VALUES);
    tensors.num_classes_with_bg = IRDET_SSD_NUM_CLASSES_WITH_BG;

    p_->last_postprocess_status = irdet_ssd_postprocess_run(
        &tensors,
        &pp_cfg,
        out_stats,
        out_detections,
        max_detections,
        out_count);
    if (p_->last_postprocess_status != 0) {
        return -6;
    }

    return 0;
}

int irdet_linux_ncnn_detector::extract_blob_from_gray8(
    const uint8_t* gray8,
    uint16_t src_width,
    uint16_t src_height,
    const char* blob_name,
    irdet_linux_blob_tensor_t* out_blob,
    irdet_preprocess_stats_t* out_stats) {
    irdet_preprocess_config_t pp_cfg;
    int rc;

    if (!p_->is_loaded || gray8 == NULL || blob_name == NULL || out_blob == NULL || out_stats == NULL) {
        return -1;
    }

    pp_cfg.input_scale = p_->cfg.input_scale;
    pp_cfg.mean = p_->cfg.mean;
    pp_cfg.stddev = p_->cfg.stddev;
    rc = irdet_preprocess_gray8_image(
        gray8,
        src_width,
        src_height,
        &pp_cfg,
        p_->runtime_tensor.data(),
        p_->cfg.runtime_input_width,
        p_->cfg.runtime_input_height,
        out_stats);
    if (rc != 0) {
        return -2;
    }

    return extract_blob_from_runtime_tensor(
        p_->runtime_tensor.data(),
        src_width,
        src_height,
        blob_name,
        out_blob,
        out_stats);
}

int irdet_linux_ncnn_detector::extract_blob_from_runtime_tensor(
    const float* runtime_input,
    uint16_t src_width,
    uint16_t src_height,
    const char* blob_name,
    irdet_linux_blob_tensor_t* out_blob,
    irdet_preprocess_stats_t* out_stats) {
    ncnn::Mat input;
    ncnn::Mat blob_out;

    if (!p_->is_loaded || runtime_input == NULL || blob_name == NULL || out_blob == NULL || out_stats == NULL) {
        return -1;
    }

    out_stats->src_width = src_width;
    out_stats->src_height = src_height;
    out_stats->dst_width = p_->cfg.runtime_input_width;
    out_stats->dst_height = p_->cfg.runtime_input_height;

    input = ncnn::Mat(
        p_->cfg.runtime_input_width,
        p_->cfg.runtime_input_height,
        1,
        const_cast<float*>(runtime_input),
        (size_t)sizeof(float));
    ncnn::Extractor extractor = p_->net.create_extractor();
    extractor.set_light_mode(true);

    p_->last_ncnn_status = extractor.input("input_0", input);
    if (p_->last_ncnn_status != 0) {
        return -2;
    }
    p_->last_ncnn_status = extractor.extract(blob_name, blob_out);
    if (p_->last_ncnn_status != 0) {
        return -3;
    }

    try {
        *out_blob = mat_to_blob_tensor(blob_out);
    } catch (const std::exception&) {
        return -4;
    }

    return 0;
}

const irdet_linux_runtime_config_t& irdet_linux_ncnn_detector::config() const {
    return p_->cfg;
}

uint32_t irdet_linux_ncnn_detector::num_anchors() const {
    return (uint32_t)(p_->anchors_xyxy.size() / IRDET_SSD_BOX_VALUES);
}

int irdet_linux_ncnn_detector::last_ncnn_status() const {
    return p_->last_ncnn_status;
}

int irdet_linux_ncnn_detector::last_postprocess_status() const {
    return p_->last_postprocess_status;
}
