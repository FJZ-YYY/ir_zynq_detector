#include "irdet_linux_dw3x3_case.h"

#include <algorithm>
#include <chrono>
#include <fstream>
#include <stdexcept>
#include <string>
#include <string.h>
#include <unordered_map>
#include <vector>

namespace {

constexpr const char* kDefaultCaseDir = "./data/pl_real_layer_case";

std::vector<uint8_t> read_binary_file(const std::string& path) {
    std::ifstream stream(path.c_str(), std::ios::binary);
    if (!stream) {
        throw std::runtime_error("failed to open file: " + path);
    }
    stream.seekg(0, std::ios::end);
    const std::streamoff bytes = stream.tellg();
    stream.seekg(0, std::ios::beg);
    if (bytes < 0) {
        throw std::runtime_error("failed to measure file: " + path);
    }
    std::vector<uint8_t> data((size_t)bytes);
    if (!data.empty()) {
        stream.read(reinterpret_cast<char*>(data.data()), bytes);
        if (!stream) {
            throw std::runtime_error("failed to read file: " + path);
        }
    }
    return data;
}

std::vector<float> read_float_file(const std::string& path) {
    std::vector<uint8_t> bytes = read_binary_file(path);
    std::vector<float> values;
    if ((bytes.size() % sizeof(float)) != 0U) {
        throw std::runtime_error("float32 file size mismatch: " + path);
    }
    values.resize(bytes.size() / sizeof(float));
    if (!values.empty()) {
        memcpy(values.data(), bytes.data(), bytes.size());
    }
    return values;
}

std::string trim_copy(const std::string& value) {
    const char* whitespace = " \t\r\n";
    const size_t start = value.find_first_not_of(whitespace);
    if (start == std::string::npos) {
        return std::string();
    }
    const size_t end = value.find_last_not_of(whitespace);
    return value.substr(start, end - start + 1U);
}

std::unordered_map<std::string, std::string> read_key_value_file(const std::string& path) {
    std::ifstream stream(path.c_str());
    std::string line;
    std::unordered_map<std::string, std::string> values;
    if (!stream) {
        throw std::runtime_error("failed to open text file: " + path);
    }

    while (std::getline(stream, line)) {
        const std::string trimmed = trim_copy(line);
        const size_t eq = trimmed.find('=');
        if (trimmed.empty() || eq == std::string::npos) {
            continue;
        }
        values.emplace(trim_copy(trimmed.substr(0, eq)), trim_copy(trimmed.substr(eq + 1U)));
    }
    return values;
}

int get_required_int(
    const std::unordered_map<std::string, std::string>& kv,
    const char* key,
    int* out_value) {
    const auto it = kv.find(std::string(key));
    if (it == kv.end()) {
        return -1;
    }
    *out_value = std::stoi(it->second);
    return 0;
}

float clip_relu6(float value) {
    if (value < 0.0f) {
        return 0.0f;
    }
    if (value > 6.0f) {
        return 6.0f;
    }
    return value;
}

}  // namespace

void irdet_linux_dw3x3_case_get_default_config(irdet_linux_dw3x3_case_config_t* cfg) {
    if (cfg == nullptr) {
        return;
    }
    cfg->case_dir = kDefaultCaseDir;
    cfg->apply_relu6 = true;
}

int irdet_linux_dw3x3_case_run_cpu_full(
    const irdet_linux_dw3x3_case_config_t* cfg,
    const float* input_blob_values,
    int blob_dims,
    int blob_w,
    int blob_h,
    int blob_c,
    irdet_linux_dw3x3_case_result_t* out_result) {
    if (cfg == nullptr || cfg->case_dir == nullptr || input_blob_values == nullptr || out_result == nullptr) {
        return -1;
    }

    *out_result = {};

    try {
        const std::string case_dir(cfg->case_dir);
        int width = blob_w;
        int height = blob_h;
        int count = (blob_w > 0 && blob_h > 0) ? (blob_w * blob_h) : 0;
        std::vector<float> weight_fused_f32;
        std::vector<float> bias_fused_f32;
        uint32_t channel = 0U;
        std::ifstream depthwise_txt_stream((case_dir + "/depthwise_full_channel.txt").c_str());

        if (depthwise_txt_stream.good()) {
            const auto depthwise_txt = read_key_value_file(case_dir + "/depthwise_full_channel.txt");
            if (get_required_int(depthwise_txt, "width", &width) != 0 ||
                get_required_int(depthwise_txt, "height", &height) != 0 ||
                get_required_int(depthwise_txt, "count", &count) != 0) {
                return -2;
            }
            if (width <= 0 || height <= 0 || count != (width * height)) {
                return -3;
            }
        }
        if (blob_dims != 3 || blob_w != width || blob_h != height || blob_c <= 0) {
            return -4;
        }

        weight_fused_f32 = read_float_file(case_dir + "/weight_fused.bin");
        bias_fused_f32 = read_float_file(case_dir + "/bias_fused.bin");
        if (bias_fused_f32.empty()) {
            return -5;
        }
        const size_t channel_count = bias_fused_f32.size();
        if ((size_t)blob_c != channel_count || weight_fused_f32.size() != channel_count * 9U) {
            return -6;
        }

        out_result->channels = (uint32_t)channel_count;
        out_result->width = (uint16_t)width;
        out_result->height = (uint16_t)height;
        out_result->count_per_channel = (uint32_t)count;
        out_result->total_count = (uint32_t)(channel_count * (size_t)count);
        out_result->output_values.resize(out_result->total_count);

        const auto t0 = std::chrono::steady_clock::now();
        for (channel = 0U; channel < out_result->channels; ++channel) {
            const size_t channel_offset = (size_t)channel * (size_t)count;
            const float* channel_input = input_blob_values + channel_offset;
            const float* channel_weight = weight_fused_f32.data() + (size_t)channel * 9U;
            const float channel_bias = bias_fused_f32[(size_t)channel];
            int y_pos;
            int x_pos;

            for (y_pos = 0; y_pos < height; ++y_pos) {
                for (x_pos = 0; x_pos < width; ++x_pos) {
                    float acc = channel_bias;
                    uint32_t tap = 0U;
                    int ky;
                    int kx;

                    for (ky = -1; ky <= 1; ++ky) {
                        for (kx = -1; kx <= 1; ++kx) {
                            const int src_y = y_pos + ky;
                            const int src_x = x_pos + kx;
                            if (src_y >= 0 && src_y < height && src_x >= 0 && src_x < width) {
                                acc += channel_input[(size_t)src_y * (size_t)width + (size_t)src_x] * channel_weight[tap];
                            }
                            ++tap;
                        }
                    }

                    if (cfg->apply_relu6) {
                        acc = clip_relu6(acc);
                    }
                    out_result->output_values[channel_offset + (size_t)y_pos * (size_t)width + (size_t)x_pos] = acc;
                }
            }
        }
        const auto t1 = std::chrono::steady_clock::now();

        out_result->cpu_us =
            (uint32_t)std::chrono::duration_cast<std::chrono::microseconds>(t1 - t0).count();
        if (!out_result->output_values.empty()) {
            out_result->first_value = out_result->output_values.front();
            out_result->last_value = out_result->output_values.back();
        }
        return 0;
    } catch (const std::exception&) {
        *out_result = {};
        return -100;
    }
}
