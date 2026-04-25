#include "irdet_linux_pl_dw3x3_probe.h"

#include "irdet_linux_dw3x3_case.h"

#include <algorithm>
#include <cmath>
#include <errno.h>
#include <fcntl.h>
#include <fstream>
#include <limits>
#include <sstream>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>

#include <chrono>
#include <cstdio>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <vector>

extern "C" {
#include "ir_pl_dw3x3_full.h"
#include "ir_pl_dw3x3_full_channel_data.h"
}

namespace {

constexpr uintptr_t kDefaultDw3x3FullBase = 0x43C10000u;
constexpr const char* kDefaultRealLayerCaseDir = "./data/pl_real_layer_case";

struct mapped_region_t {
    uintptr_t request_base = 0U;
    uintptr_t page_base = 0U;
    size_t span = 0U;
    size_t map_size = 0U;
    size_t page_offset = 0U;
    volatile uint8_t* mapped = nullptr;
};

class linux_mmio_t {
public:
    linux_mmio_t() {
        fd_ = ::open("/dev/mem", O_RDWR | O_SYNC);
        if (fd_ < 0) {
            throw std::runtime_error("failed to open /dev/mem: " + std::string(::strerror(errno)));
        }
        page_size_ = (size_t)::sysconf(_SC_PAGESIZE);
        if (page_size_ == 0U) {
            page_size_ = 4096U;
        }
    }

    ~linux_mmio_t() {
        for (size_t i = 0; i < regions_.size(); ++i) {
            if (regions_[i].mapped != nullptr) {
                ::munmap((void*)regions_[i].mapped, regions_[i].map_size);
            }
        }
        if (fd_ >= 0) {
            ::close(fd_);
        }
    }

    void ensure_region(uintptr_t base_addr, size_t span) {
        for (size_t i = 0; i < regions_.size(); ++i) {
            if (regions_[i].request_base == base_addr) {
                return;
            }
        }

        mapped_region_t region;
        const uintptr_t page_mask = (uintptr_t)(page_size_ - 1U);
        region.request_base = base_addr;
        region.page_base = base_addr & ~page_mask;
        region.page_offset = (size_t)(base_addr - region.page_base);
        region.span = span;
        region.map_size = ((region.page_offset + span + page_size_ - 1U) / page_size_) * page_size_;
        region.mapped = (volatile uint8_t*)::mmap(
            nullptr,
            region.map_size,
            PROT_READ | PROT_WRITE,
            MAP_SHARED,
            fd_,
            (off_t)region.page_base);
        if (region.mapped == MAP_FAILED) {
            throw std::runtime_error(
                "mmap failed for base 0x" + to_hex(base_addr) + ": " + std::string(::strerror(errno)));
        }
        regions_.push_back(region);
    }

    uint32_t read32(uintptr_t addr) const {
        const mapped_region_t* region = find_region(addr);
        const size_t offset = region->page_offset + (size_t)(addr - region->request_base);
        return *(volatile uint32_t*)(region->mapped + offset);
    }

    void write32(uintptr_t addr, uint32_t value) const {
        const mapped_region_t* region = find_region(addr);
        const size_t offset = region->page_offset + (size_t)(addr - region->request_base);
        *(volatile uint32_t*)(region->mapped + offset) = value;
        __sync_synchronize();
    }

    static std::string to_hex(uintptr_t value) {
        char buffer[32];
        std::snprintf(buffer, sizeof(buffer), "%08lx", (unsigned long)value);
        return std::string(buffer);
    }

private:
    const mapped_region_t* find_region(uintptr_t addr) const {
        for (size_t i = 0; i < regions_.size(); ++i) {
            const mapped_region_t& region = regions_[i];
            if (addr >= region.request_base && addr < (region.request_base + region.span)) {
                return &region;
            }
        }
        throw std::runtime_error("MMIO access outside mapped range addr=0x" + to_hex(addr));
    }

    int fd_ = -1;
    size_t page_size_ = 4096U;
    std::vector<mapped_region_t> regions_;
};

static uint32_t linux_mmio_read32(void* ctx, uintptr_t addr) {
    return static_cast<linux_mmio_t*>(ctx)->read32(addr);
}

static void linux_mmio_write32(void* ctx, uintptr_t addr, uint32_t value) {
    static_cast<linux_mmio_t*>(ctx)->write32(addr, value);
}

static uint32_t elapsed_us(
    const std::chrono::steady_clock::time_point& start_time,
    const std::chrono::steady_clock::time_point& end_time) {
    return (uint32_t)std::chrono::duration_cast<std::chrono::microseconds>(end_time - start_time).count();
}

static std::vector<uint8_t> read_binary_file(const std::string& path) {
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

static std::vector<float> read_float_file(const std::string& path) {
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

static std::string trim_copy(const std::string& value) {
    const char* whitespace = " \t\r\n";
    const size_t start = value.find_first_not_of(whitespace);
    if (start == std::string::npos) {
        return std::string();
    }
    const size_t end = value.find_last_not_of(whitespace);
    return value.substr(start, end - start + 1U);
}

static std::unordered_map<std::string, std::string> read_key_value_file(const std::string& path) {
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

static int get_required_int(
    const std::unordered_map<std::string, std::string>& kv,
    const char* key,
    int* out_value) {
    auto it = kv.find(std::string(key));
    if (it == kv.end()) {
        return -1;
    }
    *out_value = std::stoi(it->second);
    return 0;
}

static int16_t quantize_to_i16(float value, int scale) {
    const long scaled = std::lround((double)value * (double)scale);
    const long clamped = std::max<long>(std::numeric_limits<int16_t>::min(), std::min<long>(std::numeric_limits<int16_t>::max(), scaled));
    return (int16_t)clamped;
}

static int32_t expected_at(
    const int16_t* input_q,
    uint16_t width,
    uint16_t height,
    const int16_t* weight_q,
    int32_t bias_q,
    uint16_t y_pos,
    uint16_t x_pos) {
    uint32_t tap = 0U;
    int32_t acc = bias_q;
    int ky;
    int kx;

    for (ky = -1; ky <= 1; ++ky) {
        for (kx = -1; kx <= 1; ++kx) {
            const int src_y = (int)y_pos + ky;
            const int src_x = (int)x_pos + kx;
            if (src_y >= 0 && src_y < (int)height && src_x >= 0 && src_x < (int)width) {
                acc += (int32_t)input_q[(size_t)src_y * (size_t)width + (size_t)src_x] * (int32_t)weight_q[tap];
            }
            ++tap;
        }
    }
    return acc;
}

static float clip_relu6(float value) {
    if (value < 0.0f) {
        return 0.0f;
    }
    if (value > 6.0f) {
        return 6.0f;
    }
    return value;
}

}  // namespace

void irdet_linux_pl_dw3x3_full_probe_get_default_config(
    irdet_linux_pl_dw3x3_full_probe_config_t* cfg) {
    if (cfg == nullptr) {
        return;
    }
    cfg->full_base = kDefaultDw3x3FullBase;
}

int irdet_linux_pl_dw3x3_run_full_probe(
    const irdet_linux_pl_dw3x3_full_probe_config_t* cfg,
    irdet_linux_pl_dw3x3_full_probe_result_t* out_result) {
    if (cfg == nullptr || out_result == nullptr) {
        return -1;
    }

    try {
        linux_mmio_t mmio;
        irdet_dw3x3_full_dev_t dev;
        uint32_t idx;
        int32_t first_acc = 0;
        int32_t last_acc = 0;
        int rc;

        mmio.ensure_region(cfg->full_base, 0x1000U);
        out_result->full_info = mmio.read32(cfg->full_base + IRDET_DW3X3_FULL_REG_INFO);
        out_result->output_count = IRDET_DW3X3_FULL_CH_COUNT;
        out_result->first_acc = 0;
        out_result->last_acc = 0;
        out_result->e2e_us = 0U;
        out_result->compute_us = 0U;

        irdet_dw3x3_full_init(
            &dev,
            cfg->full_base,
            IRDET_DW3X3_FULL_CH_WIDTH,
            IRDET_DW3X3_FULL_CH_HEIGHT,
            &mmio,
            linux_mmio_read32,
            linux_mmio_write32);

        const auto t0 = std::chrono::steady_clock::now();
        rc = irdet_dw3x3_full_configure(
            &dev,
            IRDET_DW3X3_FULL_CH_WIDTH,
            IRDET_DW3X3_FULL_CH_HEIGHT,
            IRDET_DW3X3_FULL_CH_BIAS_Q);
        if (rc != 0) {
            return -2;
        }
        rc = irdet_dw3x3_full_write_feature_q(&dev, IRDET_DW3X3_FULL_CH_INPUT_Q, IRDET_DW3X3_FULL_CH_COUNT);
        if (rc != 0) {
            return -3;
        }
        rc = irdet_dw3x3_full_write_weights_q(&dev, IRDET_DW3X3_FULL_CH_WEIGHT_Q);
        if (rc != 0) {
            return -4;
        }

        const auto t_compute0 = std::chrono::steady_clock::now();
        rc = irdet_dw3x3_full_start(&dev);
        if (rc != 0) {
            return -5;
        }
        rc = irdet_dw3x3_full_wait_done(&dev, 10000000U);
        const auto t_compute1 = std::chrono::steady_clock::now();
        if (rc != 0) {
            return -6;
        }

        for (idx = 0U; idx < IRDET_DW3X3_FULL_CH_COUNT; ++idx) {
            int32_t out_value = 0;
            rc = irdet_dw3x3_full_read_output_q(&dev, idx, &out_value);
            if (rc != 0) {
                return -7;
            }
            if (out_value != IRDET_DW3X3_FULL_CH_EXPECTED_ACC[idx]) {
                return -8;
            }
            if (idx == 0U) {
                first_acc = out_value;
            }
            last_acc = out_value;
        }

        const auto t1 = std::chrono::steady_clock::now();
        out_result->first_acc = first_acc;
        out_result->last_acc = last_acc;
        out_result->e2e_us = elapsed_us(t0, t1);
        out_result->compute_us = elapsed_us(t_compute0, t_compute1);
        return 0;
    } catch (const std::exception&) {
        return -100;
    }
}

void irdet_linux_pl_dw3x3_real_layer_case_get_default_config(
    irdet_linux_pl_dw3x3_real_layer_case_config_t* cfg) {
    if (cfg == nullptr) {
        return;
    }
    cfg->full_base = kDefaultDw3x3FullBase;
    cfg->case_dir = kDefaultRealLayerCaseDir;
}

int irdet_linux_pl_dw3x3_run_real_layer_case(
    const irdet_linux_pl_dw3x3_real_layer_case_config_t* cfg,
    irdet_linux_pl_dw3x3_real_layer_case_result_t* out_result) {
    if (cfg == nullptr || out_result == nullptr || cfg->case_dir == nullptr) {
        return -1;
    }

    try {
        const std::string case_dir(cfg->case_dir);
        const auto depthwise_txt = read_key_value_file(case_dir + "/depthwise_full_channel.txt");
        int channel = 0;
        int width = 0;
        int height = 0;
        int count = 0;
        int frac_bits = 0;
        std::vector<float> layer_input_f32;
        std::vector<float> weight_fused_f32;
        std::vector<float> bias_fused_f32;
        std::vector<float> golden_bn_out_f32;
        std::vector<int16_t> input_q;
        int16_t weight_q[9];
        int32_t bias_q = 0;
        uint32_t idx = 0U;
        uint32_t output_count = 0U;
        int32_t first_acc = 0;
        int32_t last_acc = 0;
        float max_abs_float_error = 0.0f;
        int rc;
        linux_mmio_t mmio;
        irdet_dw3x3_full_dev_t dev;

        if (get_required_int(depthwise_txt, "channel", &channel) != 0 ||
            get_required_int(depthwise_txt, "width", &width) != 0 ||
            get_required_int(depthwise_txt, "height", &height) != 0 ||
            get_required_int(depthwise_txt, "count", &count) != 0 ||
            get_required_int(depthwise_txt, "frac_bits", &frac_bits) != 0) {
            return -2;
        }
        if (channel < 0 || width <= 0 || height <= 0 || count != (width * height) || frac_bits < 0 || frac_bits > 12) {
            return -3;
        }

        layer_input_f32 = read_float_file(case_dir + "/layer_input.bin");
        weight_fused_f32 = read_float_file(case_dir + "/weight_fused.bin");
        bias_fused_f32 = read_float_file(case_dir + "/bias_fused.bin");
        golden_bn_out_f32 = read_float_file(case_dir + "/golden_bn_out.bin");

        if (bias_fused_f32.empty()) {
            return -4;
        }
        const size_t channel_count = bias_fused_f32.size();
        if ((size_t)channel >= channel_count) {
            return -5;
        }
        if (layer_input_f32.size() != channel_count * (size_t)count ||
            golden_bn_out_f32.size() != channel_count * (size_t)count ||
            weight_fused_f32.size() != channel_count * 9U) {
            return -6;
        }

        const int input_scale = 1 << frac_bits;
        const int acc_scale = input_scale * input_scale;
        const size_t channel_offset = (size_t)channel * (size_t)count;
        const size_t weight_offset = (size_t)channel * 9U;
        input_q.resize((size_t)count);
        for (idx = 0U; idx < (uint32_t)count; ++idx) {
            input_q[idx] = quantize_to_i16(layer_input_f32[channel_offset + idx], input_scale);
        }
        for (idx = 0U; idx < 9U; ++idx) {
            weight_q[idx] = quantize_to_i16(weight_fused_f32[weight_offset + idx], input_scale);
        }
        bias_q = (int32_t)std::lround((double)bias_fused_f32[(size_t)channel] * (double)acc_scale);

        mmio.ensure_region(cfg->full_base, 0x1000U);
        out_result->full_info = mmio.read32(cfg->full_base + IRDET_DW3X3_FULL_REG_INFO);
        out_result->channel = (uint32_t)channel;
        out_result->width = (uint16_t)width;
        out_result->height = (uint16_t)height;
        out_result->output_count = (uint32_t)count;
        out_result->frac_bits = (uint32_t)frac_bits;
        out_result->bias_q = bias_q;
        out_result->first_acc = 0;
        out_result->last_acc = 0;
        out_result->max_abs_float_error = 0.0f;
        out_result->status_before_start = 0U;
        out_result->status_after_start = 0U;
        out_result->status_after_wait = 0U;
        out_result->e2e_us = 0U;
        out_result->compute_us = 0U;

        irdet_dw3x3_full_init(
            &dev,
            cfg->full_base,
            (uint16_t)width,
            (uint16_t)height,
            &mmio,
            linux_mmio_read32,
            linux_mmio_write32);

        const auto t0 = std::chrono::steady_clock::now();
        rc = irdet_dw3x3_full_configure(&dev, (uint16_t)width, (uint16_t)height, bias_q);
        if (rc != 0) {
            return -7;
        }
        rc = irdet_dw3x3_full_write_feature_q(&dev, input_q.data(), (uint32_t)count);
        if (rc != 0) {
            return -8;
        }
        rc = irdet_dw3x3_full_write_weights_q(&dev, weight_q);
        if (rc != 0) {
            return -9;
        }
        out_result->status_before_start = irdet_dw3x3_full_read_status(&dev);

        const auto t_compute0 = std::chrono::steady_clock::now();
        rc = irdet_dw3x3_full_start(&dev);
        if (rc != 0) {
            return -10;
        }
        out_result->status_after_start = irdet_dw3x3_full_read_status(&dev);
        rc = irdet_dw3x3_full_wait_done(&dev, 10000000U);
        const auto t_compute1 = std::chrono::steady_clock::now();
        out_result->status_after_wait = irdet_dw3x3_full_read_status(&dev);
        if (rc != 0) {
            return -11;
        }

        output_count = (uint32_t)count;
        for (idx = 0U; idx < output_count; ++idx) {
            int32_t pl_acc = 0;
            const uint16_t y_pos = (uint16_t)(idx / (uint32_t)width);
            const uint16_t x_pos = (uint16_t)(idx % (uint32_t)width);
            const int32_t expected_acc = expected_at(
                input_q.data(),
                (uint16_t)width,
                (uint16_t)height,
                weight_q,
                bias_q,
                y_pos,
                x_pos);
            const float golden = golden_bn_out_f32[channel_offset + idx];
            float dequant;
            float abs_err;

            rc = irdet_dw3x3_full_read_output_q(&dev, idx, &pl_acc);
            if (rc != 0) {
                return -12;
            }
            if (pl_acc != expected_acc) {
                return -13;
            }
            if (idx == 0U) {
                first_acc = pl_acc;
            }
            last_acc = pl_acc;
            dequant = (float)pl_acc / (float)acc_scale;
            abs_err = std::fabs(dequant - golden);
            if (abs_err > max_abs_float_error) {
                max_abs_float_error = abs_err;
            }
        }

        const auto t1 = std::chrono::steady_clock::now();
        out_result->first_acc = first_acc;
        out_result->last_acc = last_acc;
        out_result->max_abs_float_error = max_abs_float_error;
        out_result->e2e_us = elapsed_us(t0, t1);
        out_result->compute_us = elapsed_us(t_compute0, t_compute1);
        return 0;
    } catch (const std::exception&) {
        return -100;
    }
}

void irdet_linux_pl_dw3x3_runtime_blob_compare_get_default_config(
    irdet_linux_pl_dw3x3_runtime_blob_compare_config_t* cfg) {
    if (cfg == nullptr) {
        return;
    }
    cfg->full_base = kDefaultDw3x3FullBase;
    cfg->case_dir = kDefaultRealLayerCaseDir;
    cfg->channel = 11U;
}

int irdet_linux_pl_dw3x3_run_runtime_blob_compare(
    const irdet_linux_pl_dw3x3_runtime_blob_compare_config_t* cfg,
    const float* blob_values,
    int blob_dims,
    int blob_w,
    int blob_h,
    int blob_c,
    irdet_linux_pl_dw3x3_runtime_blob_compare_result_t* out_result) {
    if (cfg == nullptr || out_result == nullptr || cfg->case_dir == nullptr || blob_values == nullptr) {
        return -1;
    }

    *out_result = {};
    out_result->channel = cfg->channel;
    out_result->blob_dims = (blob_dims >= 0) ? (uint32_t)blob_dims : 0U;
    out_result->blob_width = (blob_w >= 0 && blob_w <= 65535) ? (uint16_t)blob_w : 0U;
    out_result->blob_height = (blob_h >= 0 && blob_h <= 65535) ? (uint16_t)blob_h : 0U;
    out_result->blob_channels = (blob_c >= 0) ? (uint32_t)blob_c : 0U;

    try {
        const std::string case_dir(cfg->case_dir);
        const auto depthwise_txt = read_key_value_file(case_dir + "/depthwise_full_channel.txt");
        int case_channel = 0;
        int width = 0;
        int height = 0;
        int count = 0;
        int frac_bits = 0;
        std::vector<float> weight_fused_f32;
        std::vector<float> bias_fused_f32;
        std::vector<int16_t> input_q;
        std::vector<int32_t> cpu_acc;
        int16_t weight_q[9];
        int32_t bias_q = 0;
        uint32_t idx = 0U;
        int32_t first_cpu_acc = 0;
        int32_t first_pl_acc = 0;
        int32_t last_cpu_acc = 0;
        int32_t last_pl_acc = 0;
        int32_t max_abs_acc_error = 0;
        float max_abs_float_error = 0.0f;
        double abs_float_error_sum = 0.0;
        int rc;
        linux_mmio_t mmio;
        irdet_dw3x3_full_dev_t dev;

        if (get_required_int(depthwise_txt, "channel", &case_channel) != 0 ||
            get_required_int(depthwise_txt, "width", &width) != 0 ||
            get_required_int(depthwise_txt, "height", &height) != 0 ||
            get_required_int(depthwise_txt, "count", &count) != 0 ||
            get_required_int(depthwise_txt, "frac_bits", &frac_bits) != 0) {
            return -2;
        }
        if (case_channel < 0 || width <= 0 || height <= 0 || count != (width * height) || frac_bits < 0 || frac_bits > 12) {
            return -3;
        }
        if (cfg->channel != (uint32_t)case_channel) {
            return -4;
        }

        weight_fused_f32 = read_float_file(case_dir + "/weight_fused.bin");
        bias_fused_f32 = read_float_file(case_dir + "/bias_fused.bin");
        if (bias_fused_f32.empty()) {
            return -5;
        }

        const size_t channel_count = bias_fused_f32.size();
        if ((size_t)case_channel >= channel_count || weight_fused_f32.size() != channel_count * 9U) {
            return -6;
        }

        out_result->width = (uint16_t)width;
        out_result->height = (uint16_t)height;
        out_result->output_count = (uint32_t)count;
        out_result->frac_bits = (uint32_t)frac_bits;

        if (blob_dims != 3) {
            return -7;
        }
        if (blob_w != width || blob_h != height || blob_c <= case_channel) {
            return -8;
        }
        if ((size_t)blob_c != channel_count) {
            return -9;
        }

        const int input_scale = 1 << frac_bits;
        const int acc_scale = input_scale * input_scale;
        const size_t channel_offset = (size_t)case_channel * (size_t)count;
        const size_t weight_offset = (size_t)case_channel * 9U;
        input_q.resize((size_t)count);
        cpu_acc.resize((size_t)count);
        for (idx = 0U; idx < (uint32_t)count; ++idx) {
            input_q[idx] = quantize_to_i16(blob_values[channel_offset + idx], input_scale);
        }
        for (idx = 0U; idx < 9U; ++idx) {
            weight_q[idx] = quantize_to_i16(weight_fused_f32[weight_offset + idx], input_scale);
        }
        bias_q = (int32_t)std::lround((double)bias_fused_f32[(size_t)case_channel] * (double)acc_scale);

        const auto t_cpu0 = std::chrono::steady_clock::now();
        for (idx = 0U; idx < (uint32_t)count; ++idx) {
            const uint16_t y_pos = (uint16_t)(idx / (uint32_t)width);
            const uint16_t x_pos = (uint16_t)(idx % (uint32_t)width);
            cpu_acc[idx] = expected_at(
                input_q.data(),
                (uint16_t)width,
                (uint16_t)height,
                weight_q,
                bias_q,
                y_pos,
                x_pos);
        }
        const auto t_cpu1 = std::chrono::steady_clock::now();

        mmio.ensure_region(cfg->full_base, 0x1000U);
        out_result->full_info = mmio.read32(cfg->full_base + IRDET_DW3X3_FULL_REG_INFO);
        out_result->bias_q = bias_q;

        irdet_dw3x3_full_init(
            &dev,
            cfg->full_base,
            (uint16_t)width,
            (uint16_t)height,
            &mmio,
            linux_mmio_read32,
            linux_mmio_write32);

        const auto t0 = std::chrono::steady_clock::now();
        rc = irdet_dw3x3_full_configure(&dev, (uint16_t)width, (uint16_t)height, bias_q);
        if (rc != 0) {
            return -10;
        }
        rc = irdet_dw3x3_full_write_feature_q(&dev, input_q.data(), (uint32_t)count);
        if (rc != 0) {
            return -11;
        }
        rc = irdet_dw3x3_full_write_weights_q(&dev, weight_q);
        if (rc != 0) {
            return -12;
        }
        out_result->status_before_start = irdet_dw3x3_full_read_status(&dev);

        const auto t_compute0 = std::chrono::steady_clock::now();
        rc = irdet_dw3x3_full_start(&dev);
        if (rc != 0) {
            return -13;
        }
        out_result->status_after_start = irdet_dw3x3_full_read_status(&dev);
        rc = irdet_dw3x3_full_wait_done(&dev, 10000000U);
        const auto t_compute1 = std::chrono::steady_clock::now();
        out_result->status_after_wait = irdet_dw3x3_full_read_status(&dev);
        if (rc != 0) {
            return -14;
        }

        for (idx = 0U; idx < (uint32_t)count; ++idx) {
            int32_t pl_acc = 0;
            const int32_t cpu_expected = cpu_acc[idx];
            int32_t abs_acc_error;
            float abs_float_error;

            rc = irdet_dw3x3_full_read_output_q(&dev, idx, &pl_acc);
            if (rc != 0) {
                return -15;
            }
            abs_acc_error = (int32_t)((pl_acc >= cpu_expected) ? (pl_acc - cpu_expected) : (cpu_expected - pl_acc));
            if (abs_acc_error > max_abs_acc_error) {
                max_abs_acc_error = abs_acc_error;
            }
            abs_float_error = std::fabs(
                ((float)pl_acc / (float)acc_scale) -
                ((float)cpu_expected / (float)acc_scale));
            abs_float_error_sum += abs_float_error;
            if (abs_float_error > max_abs_float_error) {
                max_abs_float_error = abs_float_error;
            }
            if (idx == 0U) {
                first_cpu_acc = cpu_expected;
                first_pl_acc = pl_acc;
            }
            last_cpu_acc = cpu_expected;
            last_pl_acc = pl_acc;
        }

        const auto t1 = std::chrono::steady_clock::now();
        out_result->first_cpu_acc = first_cpu_acc;
        out_result->first_pl_acc = first_pl_acc;
        out_result->last_cpu_acc = last_cpu_acc;
        out_result->last_pl_acc = last_pl_acc;
        out_result->max_abs_acc_error = max_abs_acc_error;
        out_result->max_abs_float_error = max_abs_float_error;
        out_result->mean_abs_float_error =
            (count > 0) ? (float)(abs_float_error_sum / (double)count) : 0.0f;
        out_result->cpu_us = elapsed_us(t_cpu0, t_cpu1);
        out_result->e2e_us = elapsed_us(t0, t1);
        out_result->compute_us = elapsed_us(t_compute0, t_compute1);

        if (max_abs_acc_error != 0) {
            return -16;
        }
        return 0;
    } catch (const std::exception&) {
        return -100;
    }
}

void irdet_linux_pl_dw3x3_runtime_blob_full_get_default_config(
    irdet_linux_pl_dw3x3_runtime_blob_full_config_t* cfg) {
    if (cfg == nullptr) {
        return;
    }
    cfg->full_base = kDefaultDw3x3FullBase;
    cfg->case_dir = kDefaultRealLayerCaseDir;
    cfg->apply_relu6 = true;
}

int irdet_linux_pl_dw3x3_run_runtime_blob_full(
    const irdet_linux_pl_dw3x3_runtime_blob_full_config_t* cfg,
    const float* blob_values,
    int blob_dims,
    int blob_w,
    int blob_h,
    int blob_c,
    std::vector<float>* out_output_values,
    irdet_linux_pl_dw3x3_runtime_blob_full_result_t* out_result) {
    if (cfg == nullptr || out_result == nullptr || cfg->case_dir == nullptr || blob_values == nullptr) {
        return -1;
    }

    *out_result = {};
    if (out_output_values != nullptr) {
        out_output_values->clear();
    }

    try {
        const std::string case_dir(cfg->case_dir);
        const auto depthwise_txt = read_key_value_file(case_dir + "/depthwise_full_channel.txt");
        int width = 0;
        int height = 0;
        int count = 0;
        int frac_bits = 0;
        std::vector<float> weight_fused_f32;
        std::vector<float> bias_fused_f32;
        std::vector<int32_t> cpu_acc;
        irdet_linux_dw3x3_case_config_t cpu_cfg;
        irdet_linux_dw3x3_case_result_t cpu_full_result = {};
        uint32_t channel = 0U;
        uint32_t idx = 0U;
        int32_t first_cpu_acc = 0;
        int32_t first_pl_acc = 0;
        int32_t last_cpu_acc = 0;
        int32_t last_pl_acc = 0;
        int32_t max_abs_acc_error = 0;
        float max_abs_float_error = 0.0f;
        double abs_float_error_sum = 0.0;
        uint32_t compute_us_total = 0U;
        int rc;
        linux_mmio_t mmio;
        irdet_dw3x3_full_dev_t dev;

        if (get_required_int(depthwise_txt, "width", &width) != 0 ||
            get_required_int(depthwise_txt, "height", &height) != 0 ||
            get_required_int(depthwise_txt, "count", &count) != 0 ||
            get_required_int(depthwise_txt, "frac_bits", &frac_bits) != 0) {
            return -2;
        }
        if (width <= 0 || height <= 0 || count != (width * height) || frac_bits < 0 || frac_bits > 12) {
            return -3;
        }
        if (blob_dims != 3) {
            return -7;
        }
        if (blob_w != width || blob_h != height || blob_c <= 0) {
            return -8;
        }

        weight_fused_f32 = read_float_file(case_dir + "/weight_fused.bin");
        bias_fused_f32 = read_float_file(case_dir + "/bias_fused.bin");
        if (bias_fused_f32.empty()) {
            return -4;
        }
        const size_t channel_count = bias_fused_f32.size();
        if ((size_t)blob_c != channel_count || weight_fused_f32.size() != channel_count * 9U) {
            return -5;
        }

        irdet_linux_dw3x3_case_get_default_config(&cpu_cfg);
        cpu_cfg.case_dir = cfg->case_dir;
        cpu_cfg.apply_relu6 = cfg->apply_relu6;
        rc = irdet_linux_dw3x3_case_run_cpu_full(
            &cpu_cfg,
            blob_values,
            blob_dims,
            blob_w,
            blob_h,
            blob_c,
            &cpu_full_result);
        if (rc != 0) {
            return -6;
        }

        out_result->width = (uint16_t)width;
        out_result->height = (uint16_t)height;
        out_result->channels = (uint32_t)channel_count;
        out_result->count_per_channel = (uint32_t)count;
        out_result->total_count = (uint32_t)(channel_count * (size_t)count);
        out_result->frac_bits = (uint32_t)frac_bits;
        out_result->pl_calls = (uint32_t)channel_count;
        out_result->failed_channel = 0xffffffffU;
        out_result->cpu_us = cpu_full_result.cpu_us;

        cpu_acc.resize(out_result->total_count);
        {
            const int input_scale = 1 << frac_bits;
            const int acc_scale = input_scale * input_scale;
            std::vector<int16_t> input_q((size_t)count);
            int16_t weight_q[9];
            for (channel = 0U; channel < out_result->channels; ++channel) {
                const size_t channel_offset = (size_t)channel * (size_t)count;
                const size_t weight_offset = (size_t)channel * 9U;
                const int32_t bias_q =
                    (int32_t)std::lround((double)bias_fused_f32[(size_t)channel] * (double)acc_scale);
                for (idx = 0U; idx < (uint32_t)count; ++idx) {
                    input_q[idx] = quantize_to_i16(blob_values[channel_offset + idx], input_scale);
                }
                for (idx = 0U; idx < 9U; ++idx) {
                    weight_q[idx] = quantize_to_i16(weight_fused_f32[weight_offset + idx], input_scale);
                }
                for (idx = 0U; idx < (uint32_t)count; ++idx) {
                    const uint16_t y_pos = (uint16_t)(idx / (uint32_t)width);
                    const uint16_t x_pos = (uint16_t)(idx % (uint32_t)width);
                    cpu_acc[channel_offset + idx] = expected_at(
                        input_q.data(),
                        (uint16_t)width,
                        (uint16_t)height,
                        weight_q,
                        bias_q,
                        y_pos,
                        x_pos);
                }
            }
        }

        if (out_output_values != nullptr) {
            *out_output_values = std::vector<float>(out_result->total_count, 0.0f);
        }

        mmio.ensure_region(cfg->full_base, 0x1000U);
        out_result->full_info = mmio.read32(cfg->full_base + IRDET_DW3X3_FULL_REG_INFO);
        irdet_dw3x3_full_init(
            &dev,
            cfg->full_base,
            (uint16_t)width,
            (uint16_t)height,
            &mmio,
            linux_mmio_read32,
            linux_mmio_write32);

        const auto t0 = std::chrono::steady_clock::now();
        for (channel = 0U; channel < out_result->channels; ++channel) {
            const int input_scale = 1 << frac_bits;
            const int acc_scale = input_scale * input_scale;
            const size_t channel_offset = (size_t)channel * (size_t)count;
            const size_t weight_offset = (size_t)channel * 9U;
            std::vector<int16_t> input_q((size_t)count);
            int16_t weight_q[9];
            const int32_t bias_q =
                (int32_t)std::lround((double)bias_fused_f32[(size_t)channel] * (double)acc_scale);

            out_result->failed_channel = channel;
            for (idx = 0U; idx < (uint32_t)count; ++idx) {
                input_q[idx] = quantize_to_i16(blob_values[channel_offset + idx], input_scale);
            }
            for (idx = 0U; idx < 9U; ++idx) {
                weight_q[idx] = quantize_to_i16(weight_fused_f32[weight_offset + idx], input_scale);
            }

            rc = irdet_dw3x3_full_configure(&dev, (uint16_t)width, (uint16_t)height, bias_q);
            if (rc != 0) {
                return -10;
            }
            rc = irdet_dw3x3_full_write_feature_q(&dev, input_q.data(), (uint32_t)count);
            if (rc != 0) {
                return -11;
            }
            rc = irdet_dw3x3_full_write_weights_q(&dev, weight_q);
            if (rc != 0) {
                return -12;
            }
            out_result->status_before_start = irdet_dw3x3_full_read_status(&dev);

            const auto t_compute0 = std::chrono::steady_clock::now();
            rc = irdet_dw3x3_full_start(&dev);
            if (rc != 0) {
                return -13;
            }
            out_result->status_after_start = irdet_dw3x3_full_read_status(&dev);
            rc = irdet_dw3x3_full_wait_done(&dev, 10000000U);
            const auto t_compute1 = std::chrono::steady_clock::now();
            out_result->status_after_wait = irdet_dw3x3_full_read_status(&dev);
            if (rc != 0) {
                return -14;
            }
            compute_us_total += elapsed_us(t_compute0, t_compute1);

            for (idx = 0U; idx < (uint32_t)count; ++idx) {
                int32_t pl_acc = 0;
                const int32_t cpu_expected = cpu_acc[channel_offset + idx];
                int32_t abs_acc_error = 0;
                float pl_out_value = 0.0f;
                float abs_float_error = 0.0f;

                rc = irdet_dw3x3_full_read_output_q(&dev, idx, &pl_acc);
                if (rc != 0) {
                    return -15;
                }
                abs_acc_error =
                    (int32_t)((pl_acc >= cpu_expected) ? (pl_acc - cpu_expected) : (cpu_expected - pl_acc));
                if (idx == 0U && channel == 0U) {
                    first_cpu_acc = cpu_expected;
                    first_pl_acc = pl_acc;
                }
                last_cpu_acc = cpu_expected;
                last_pl_acc = pl_acc;
                if (abs_acc_error > max_abs_acc_error) {
                    max_abs_acc_error = abs_acc_error;
                }

                pl_out_value = (float)pl_acc / (float)acc_scale;
                if (cfg->apply_relu6) {
                    pl_out_value = clip_relu6(pl_out_value);
                }
                if (out_output_values != nullptr) {
                    (*out_output_values)[channel_offset + idx] = pl_out_value;
                }
                abs_float_error = std::fabs(pl_out_value - cpu_full_result.output_values[channel_offset + idx]);
                abs_float_error_sum += abs_float_error;
                if (abs_float_error > max_abs_float_error) {
                    max_abs_float_error = abs_float_error;
                }
            }
        }
        const auto t1 = std::chrono::steady_clock::now();

        out_result->failed_channel = 0xffffffffU;
        out_result->first_cpu_acc = first_cpu_acc;
        out_result->first_pl_acc = first_pl_acc;
        out_result->last_cpu_acc = last_cpu_acc;
        out_result->last_pl_acc = last_pl_acc;
        out_result->max_abs_acc_error = max_abs_acc_error;
        out_result->max_abs_float_error = max_abs_float_error;
        out_result->mean_abs_float_error =
            (out_result->total_count > 0U) ? (float)(abs_float_error_sum / (double)out_result->total_count) : 0.0f;
        out_result->e2e_us = elapsed_us(t0, t1);
        out_result->compute_us_total = compute_us_total;

        if (max_abs_acc_error != 0) {
            return -16;
        }
        return 0;
    } catch (const std::exception&) {
        if (out_output_values != nullptr) {
            out_output_values->clear();
        }
        *out_result = {};
        return -100;
    }
}
