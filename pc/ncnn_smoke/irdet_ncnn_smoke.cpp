#include <algorithm>
#include <cmath>
#include <cstdlib>
#include <cstdint>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

#include "net.h"

namespace {

struct TensorStats {
    float max_abs_diff = 0.0f;
    float mean_abs_diff = 0.0f;
    std::size_t compared = 0;
};

std::vector<float> read_f32_file(const std::string& path) {
    std::ifstream stream(path.c_str(), std::ios::binary);
    if (!stream) {
        throw std::runtime_error("failed to open file: " + path);
    }
    stream.seekg(0, std::ios::end);
    const std::streamoff bytes = stream.tellg();
    if (bytes < 0 || (bytes % static_cast<std::streamoff>(sizeof(float))) != 0) {
        throw std::runtime_error("file size is not float32 aligned: " + path);
    }
    stream.seekg(0, std::ios::beg);
    std::vector<float> values(static_cast<std::size_t>(bytes) / sizeof(float));
    if (!values.empty()) {
        stream.read(reinterpret_cast<char*>(values.data()), bytes);
        if (!stream) {
            throw std::runtime_error("failed to read file: " + path);
        }
    }
    return values;
}

std::vector<float> mat_to_vector(const ncnn::Mat& mat) {
    const std::size_t count = mat.total();
    const float* data = reinterpret_cast<const float*>(mat.data);
    if (data == nullptr && count != 0) {
        throw std::runtime_error("ncnn output mat has null data");
    }
    return std::vector<float>(data, data + count);
}

TensorStats compare_tensors(const std::vector<float>& actual, const std::vector<float>& expected) {
    TensorStats stats;
    stats.compared = std::min(actual.size(), expected.size());
    if (actual.size() != expected.size()) {
        throw std::runtime_error(
            "tensor size mismatch actual=" + std::to_string(actual.size()) +
            " expected=" + std::to_string(expected.size()));
    }

    double abs_sum = 0.0;
    for (std::size_t i = 0; i < stats.compared; ++i) {
        const float diff = std::fabs(actual[i] - expected[i]);
        stats.max_abs_diff = std::max(stats.max_abs_diff, diff);
        abs_sum += diff;
    }
    stats.mean_abs_diff = stats.compared == 0 ? 0.0f : static_cast<float>(abs_sum / stats.compared);
    return stats;
}

void print_mat_shape(const char* name, const ncnn::Mat& mat) {
    std::cout << name
              << " dims=" << mat.dims
              << " w=" << mat.w
              << " h=" << mat.h
              << " d=" << mat.d
              << " c=" << mat.c
              << " elempack=" << mat.elempack
              << " total=" << mat.total()
              << std::endl;
}

std::string join_path(const std::string& dir, const std::string& leaf) {
    if (dir.empty()) {
        return leaf;
    }
    const char last = dir[dir.size() - 1];
    if (last == '\\' || last == '/') {
        return dir + leaf;
    }
    return dir + "\\" + leaf;
}

}  // namespace

int main(int argc, char** argv) {
    const std::string default_repo = "G:\\FPGA\\ir_zynq_detector";
    const std::string repo_root = argc > 1 ? argv[1] : default_repo;
    const float tolerance = argc > 2 ? static_cast<float>(std::atof(argv[2])) : 2.0e-3f;

    const std::string param_path = join_path(
        repo_root,
        "build\\ncnn_runtime_fixed_v2_tracer_op13_ncnn\\irdet_ssdlite_ir_runtime_fixed_v2.param");
    const std::string bin_path = join_path(
        repo_root,
        "build\\ncnn_runtime_fixed_v2_tracer_op13_ncnn\\irdet_ssdlite_ir_runtime_fixed_v2.bin");
    const std::string vector_dir = join_path(repo_root, "build\\ncnn_smoke");
    const std::string input_path = join_path(vector_dir, "input_f32.bin");
    const std::string bbox_ref_path = join_path(vector_dir, "bbox_regression_f32.bin");
    const std::string cls_ref_path = join_path(vector_dir, "cls_logits_f32.bin");

    try {
        std::cout << "IR detector ncnn C++ smoke test" << std::endl;
        std::cout << "repo_root=" << repo_root << std::endl;
        std::cout << "param=" << param_path << std::endl;
        std::cout << "bin=" << bin_path << std::endl;
        std::cout << "vectors=" << vector_dir << std::endl;

        std::vector<float> input_data = read_f32_file(input_path);
        std::vector<float> bbox_ref = read_f32_file(bbox_ref_path);
        std::vector<float> cls_ref = read_f32_file(cls_ref_path);
        if (input_data.size() != 1u * 1u * 128u * 160u) {
            throw std::runtime_error("expected input size 1x1x128x160, got " + std::to_string(input_data.size()));
        }

        ncnn::Net net;
        net.opt.lightmode = true;
        net.opt.num_threads = 1;
        net.opt.use_packing_layout = false;
#if NCNN_VULKAN
        net.opt.use_vulkan_compute = false;
#endif

        int ret = net.load_param(param_path.c_str());
        if (ret != 0) {
            throw std::runtime_error("net.load_param failed ret=" + std::to_string(ret));
        }
        ret = net.load_model(bin_path.c_str());
        if (ret != 0) {
            throw std::runtime_error("net.load_model failed ret=" + std::to_string(ret));
        }

        ncnn::Mat input(160, 128, 1, input_data.data(), static_cast<size_t>(4u));
        ncnn::Extractor extractor = net.create_extractor();
        extractor.set_light_mode(true);
        ret = extractor.input("input_0", input);
        if (ret != 0) {
            throw std::runtime_error("extractor.input failed ret=" + std::to_string(ret));
        }

        ncnn::Mat bbox_out;
        ncnn::Mat cls_out;
        ret = extractor.extract("bbox_regression", bbox_out);
        if (ret != 0) {
            throw std::runtime_error("extract bbox_regression failed ret=" + std::to_string(ret));
        }
        ret = extractor.extract("cls_logits", cls_out);
        if (ret != 0) {
            throw std::runtime_error("extract cls_logits failed ret=" + std::to_string(ret));
        }

        print_mat_shape("bbox_regression", bbox_out);
        print_mat_shape("cls_logits", cls_out);

        const TensorStats bbox_stats = compare_tensors(mat_to_vector(bbox_out), bbox_ref);
        const TensorStats cls_stats = compare_tensors(mat_to_vector(cls_out), cls_ref);

        std::cout << "Compare bbox_regression compared=" << bbox_stats.compared
                  << " max_abs_diff=" << bbox_stats.max_abs_diff
                  << " mean_abs_diff=" << bbox_stats.mean_abs_diff
                  << std::endl;
        std::cout << "Compare cls_logits compared=" << cls_stats.compared
                  << " max_abs_diff=" << cls_stats.max_abs_diff
                  << " mean_abs_diff=" << cls_stats.mean_abs_diff
                  << std::endl;

        const bool pass = bbox_stats.max_abs_diff <= tolerance && cls_stats.max_abs_diff <= tolerance;
        std::cout << "NCNN_SMOKE_" << (pass ? "PASS" : "FAIL")
                  << " tolerance=" << tolerance << std::endl;
        return pass ? 0 : 2;
    } catch (const std::exception& exc) {
        std::cerr << "NCNN_SMOKE_ERROR: " << exc.what() << std::endl;
        return 1;
    }
}
