#include <stdint.h>

#include <cstdlib>
#include <cstdio>
#include <fstream>
#include <stdexcept>
#include <string>
#include <vector>

#include "irdet_linux_ncnn_detector.h"
#include "irdet_linux_pl_dw3x3_probe.h"

namespace {

struct cli_args_t {
    std::string param_path;
    std::string bin_path;
    std::string anchors_path;
    std::string gray8_path;
    std::string tensor_path;
    std::string pl_real_layer_dir;
    std::string dump_blob_name;
    std::string dump_blob_out_prefix;
    uint16_t src_width = 0U;
    uint16_t src_height = 0U;
    bool run_pl_probe_full = false;
    bool run_pl_real_layer = false;
    bool blob_only = false;
    irdet_linux_runtime_config_t cfg;
    irdet_linux_pl_dw3x3_full_probe_config_t pl_probe_cfg;
    irdet_linux_pl_dw3x3_real_layer_case_config_t pl_real_layer_cfg;
};

void print_usage() {
    std::fputs(
        "Usage:\n"
        "  irdet_linux_ncnn_app --param <model.param> --bin <model.bin> --anchors <anchors.bin>\n"
        "                       [--gray8 <image_gray8.bin> --src-width <w> --src-height <h>]\n"
        "                       [--tensor-f32 <input_f32.bin> --src-width <w> --src-height <h>]\n"
        "                       [--runtime-width 160 --runtime-height 128 --mean 0.5 --std 0.5]\n"
        "                       [--pl-probe-full --pl-full-base 0x43C10000]\n"
        "                       [--pl-real-layer-dir <case_dir>]\n"
        "                       [--dump-blob <name> --dump-blob-out <prefix> [--blob-only]]\n",
        stdout);
    std::fflush(stdout);
}

std::vector<uint8_t> read_u8_file(const std::string& path) {
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
    }
    return data;
}

std::vector<float> read_f32_file(const std::string& path) {
    std::ifstream stream(path.c_str(), std::ios::binary);
    if (!stream) {
        throw std::runtime_error("failed to open file: " + path);
    }
    stream.seekg(0, std::ios::end);
    const std::streamoff bytes = stream.tellg();
    stream.seekg(0, std::ios::beg);
    if (bytes < 0 || (bytes % (std::streamoff)sizeof(float)) != 0) {
        throw std::runtime_error("invalid float32 file: " + path);
    }
    std::vector<float> data((size_t)bytes / sizeof(float));
    if (!data.empty()) {
        stream.read(reinterpret_cast<char*>(data.data()), bytes);
    }
    return data;
}

void write_f32_file(const std::string& path, const std::vector<float>& data) {
    std::ofstream stream(path.c_str(), std::ios::binary);
    if (!stream) {
        throw std::runtime_error("failed to open output file: " + path);
    }
    if (!data.empty()) {
        stream.write(reinterpret_cast<const char*>(data.data()), (std::streamsize)(data.size() * sizeof(float)));
        if (!stream) {
            throw std::runtime_error("failed to write output file: " + path);
        }
    }
}

std::string json_escape(const std::string& input) {
    std::string out;
    size_t i;
    out.reserve(input.size() + 8U);
    for (i = 0U; i < input.size(); ++i) {
        const char ch = input[i];
        switch (ch) {
        case '\\':
            out += "\\\\";
            break;
        case '"':
            out += "\\\"";
            break;
        case '\n':
            out += "\\n";
            break;
        case '\r':
            out += "\\r";
            break;
        case '\t':
            out += "\\t";
            break;
        default:
            out += ch;
            break;
        }
    }
    return out;
}

void write_blob_metadata_json(
    const std::string& path,
    const std::string& blob_name,
    const irdet_linux_blob_tensor_t& blob,
    const irdet_preprocess_stats_t& stats) {
    std::ofstream stream(path.c_str(), std::ios::binary);
    if (!stream) {
        throw std::runtime_error("failed to open metadata file: " + path);
    }
    stream
        << "{\n"
        << "  \"blob_name\": \"" << json_escape(blob_name) << "\",\n"
        << "  \"dims\": " << blob.dims << ",\n"
        << "  \"w\": " << blob.w << ",\n"
        << "  \"h\": " << blob.h << ",\n"
        << "  \"c\": " << blob.c << ",\n"
        << "  \"num_values\": " << blob.values.size() << ",\n"
        << "  \"src_width\": " << stats.src_width << ",\n"
        << "  \"src_height\": " << stats.src_height << ",\n"
        << "  \"runtime_width\": " << stats.dst_width << ",\n"
        << "  \"runtime_height\": " << stats.dst_height << "\n"
        << "}\n";
    if (!stream) {
        throw std::runtime_error("failed to write metadata file: " + path);
    }
}

std::string blob_bin_path_from_prefix(const std::string& prefix) {
    if (prefix.size() >= 4U && prefix.substr(prefix.size() - 4U) == ".bin") {
        return prefix;
    }
    return prefix + ".bin";
}

std::string blob_json_path_from_prefix(const std::string& prefix) {
    if (prefix.size() >= 4U && prefix.substr(prefix.size() - 4U) == ".bin") {
        return prefix.substr(0U, prefix.size() - 4U) + ".json";
    }
    return prefix + ".json";
}

bool consume_value(int argc, char** argv, int& i, std::string* out) {
    if ((i + 1) >= argc) {
        return false;
    }
    ++i;
    *out = argv[i];
    return true;
}

template <typename T>
bool parse_value(const std::string& text, T* out);

template <>
bool parse_value<uint16_t>(const std::string& text, uint16_t* out) {
    const int value = std::stoi(text);
    if (value < 0 || value > 65535) {
        return false;
    }
    *out = (uint16_t)value;
    return true;
}

template <>
bool parse_value<float>(const std::string& text, float* out) {
    *out = std::stof(text);
    return true;
}

template <typename T>
bool consume_numeric(int argc, char** argv, int& i, T* out) {
    std::string text;
    if (!consume_value(argc, argv, i, &text)) {
        return false;
    }
    return parse_value<T>(text, out);
}

bool parse_args(int argc, char** argv, cli_args_t* args) {
    int i;

    irdet_linux_runtime_get_default_config(&args->cfg);
    irdet_linux_pl_dw3x3_full_probe_get_default_config(&args->pl_probe_cfg);
    irdet_linux_pl_dw3x3_real_layer_case_get_default_config(&args->pl_real_layer_cfg);
    for (i = 1; i < argc; ++i) {
        const std::string opt(argv[i]);
        if (opt == "--param") {
            if (!consume_value(argc, argv, i, &args->param_path)) {
                return false;
            }
        } else if (opt == "--bin") {
            if (!consume_value(argc, argv, i, &args->bin_path)) {
                return false;
            }
        } else if (opt == "--anchors") {
            if (!consume_value(argc, argv, i, &args->anchors_path)) {
                return false;
            }
        } else if (opt == "--gray8") {
            if (!consume_value(argc, argv, i, &args->gray8_path)) {
                return false;
            }
        } else if (opt == "--tensor-f32") {
            if (!consume_value(argc, argv, i, &args->tensor_path)) {
                return false;
            }
        } else if (opt == "--src-width") {
            if (!consume_numeric(argc, argv, i, &args->src_width)) {
                return false;
            }
        } else if (opt == "--src-height") {
            if (!consume_numeric(argc, argv, i, &args->src_height)) {
                return false;
            }
        } else if (opt == "--runtime-width") {
            if (!consume_numeric(argc, argv, i, &args->cfg.runtime_input_width)) {
                return false;
            }
        } else if (opt == "--runtime-height") {
            if (!consume_numeric(argc, argv, i, &args->cfg.runtime_input_height)) {
                return false;
            }
        } else if (opt == "--score-thresh-x1000") {
            if (!consume_numeric(argc, argv, i, &args->cfg.score_threshold_x1000)) {
                return false;
            }
        } else if (opt == "--iou-thresh-x1000") {
            if (!consume_numeric(argc, argv, i, &args->cfg.iou_threshold_x1000)) {
                return false;
            }
        } else if (opt == "--mean") {
            if (!consume_numeric(argc, argv, i, &args->cfg.mean)) {
                return false;
            }
        } else if (opt == "--std") {
            if (!consume_numeric(argc, argv, i, &args->cfg.stddev)) {
                return false;
            }
        } else if (opt == "--input-scale") {
            if (!consume_numeric(argc, argv, i, &args->cfg.input_scale)) {
                return false;
            }
        } else if (opt == "--pl-probe-full") {
            args->run_pl_probe_full = true;
        } else if (opt == "--pl-real-layer-dir") {
            if (!consume_value(argc, argv, i, &args->pl_real_layer_dir)) {
                return false;
            }
            args->run_pl_real_layer = true;
        } else if (opt == "--dump-blob") {
            if (!consume_value(argc, argv, i, &args->dump_blob_name)) {
                return false;
            }
        } else if (opt == "--dump-blob-out") {
            if (!consume_value(argc, argv, i, &args->dump_blob_out_prefix)) {
                return false;
            }
        } else if (opt == "--blob-only") {
            args->blob_only = true;
        } else if (opt == "--pl-full-base") {
            std::string text;
            char* end_ptr = NULL;
            if (!consume_value(argc, argv, i, &text)) {
                return false;
            }
            args->pl_probe_cfg.full_base = (uintptr_t)std::strtoull(text.c_str(), &end_ptr, 0);
            args->pl_real_layer_cfg.full_base = args->pl_probe_cfg.full_base;
            if (end_ptr == NULL || *end_ptr != '\0') {
                return false;
            }
        } else if (opt == "--help" || opt == "-h") {
            print_usage();
            return false;
        } else {
            std::fprintf(stderr, "Unknown option: %s\n", opt.c_str());
            std::fflush(stderr);
            return false;
        }
    }

    if (args->param_path.empty() || args->bin_path.empty() || args->anchors_path.empty()) {
        return false;
    }
    if (args->gray8_path.empty() == args->tensor_path.empty()) {
        return false;
    }
    if (args->src_width == 0U || args->src_height == 0U) {
        return false;
    }
    if (args->dump_blob_name.empty() != args->dump_blob_out_prefix.empty()) {
        return false;
    }
    return true;
}

void print_detections(const irdet_detection_t* detections, uint32_t count) {
    uint32_t i;
    std::fprintf(stdout, "det_count=%u\n", count);
    for (i = 0U; i < count; ++i) {
        const irdet_detection_t& det = detections[i];
        std::fprintf(
            stdout,
            "det%u class=%s score=%.3f bbox=[%u,%u,%u,%u]\n",
            i,
            (det.class_name != NULL ? det.class_name : "unknown"),
            (float)det.score_x1000 / 1000.0f,
            det.x1,
            det.y1,
            det.x2,
            det.y2);
    }
    std::fflush(stdout);
}

}  // namespace

int main(int argc, char** argv) {
    cli_args_t args;
    irdet_linux_ncnn_detector detector;
    irdet_detection_t detections[IRDET_MAX_DETECTIONS];
    irdet_preprocess_stats_t stats = {};
    irdet_linux_blob_tensor_t blob = {};
    irdet_linux_pl_dw3x3_full_probe_result_t pl_probe_result = {};
    irdet_linux_pl_dw3x3_real_layer_case_result_t pl_real_layer_result = {};
    uint32_t out_count = 0U;
    int rc;

    if (!parse_args(argc, argv, &args)) {
        print_usage();
        return 1;
    }

    rc = detector.load(
        args.param_path.c_str(),
        args.bin_path.c_str(),
        args.anchors_path.c_str(),
        &args.cfg);
    if (rc != 0) {
        std::fprintf(stderr, "load failed rc=%d\n", rc);
        std::fflush(stderr);
        return 2;
    }

    std::fprintf(
        stdout,
        "Model backend=ncnn runtime_in=%ux%u anchors=%u score_thresh=%u mean=%g std=%g\n",
        detector.config().runtime_input_width,
        detector.config().runtime_input_height,
        detector.num_anchors(),
        detector.config().score_threshold_x1000,
        detector.config().mean,
        detector.config().stddev);
    std::fprintf(
        stdout,
        "Runtime contract nchw=1x1x%ux%u width=%u height=%u\n",
        detector.config().runtime_input_height,
        detector.config().runtime_input_width,
        detector.config().runtime_input_width,
        detector.config().runtime_input_height);
    std::fflush(stdout);

    if (args.run_pl_probe_full) {
        rc = irdet_linux_pl_dw3x3_run_full_probe(&args.pl_probe_cfg, &pl_probe_result);
        if (rc != 0) {
            std::fprintf(stderr, "pl_probe_full failed rc=%d\n", rc);
            std::fflush(stderr);
            return 7;
        }
        std::fprintf(
            stdout,
            "pl_probe_full rc=0 base=0x%08lx info=0x%08x count=%u first_acc=%ld last_acc=%ld e2e_us=%u compute_us=%u\n",
            (unsigned long)args.pl_probe_cfg.full_base,
            pl_probe_result.full_info,
            pl_probe_result.output_count,
            (long)pl_probe_result.first_acc,
            (long)pl_probe_result.last_acc,
            pl_probe_result.e2e_us,
            pl_probe_result.compute_us);
        std::fflush(stdout);
    }

    if (args.run_pl_real_layer) {
        args.pl_real_layer_cfg.case_dir = args.pl_real_layer_dir.c_str();
        rc = irdet_linux_pl_dw3x3_run_real_layer_case(&args.pl_real_layer_cfg, &pl_real_layer_result);
        if (rc != 0) {
            std::fprintf(
                stderr,
                "pl_real_layer failed rc=%d dir=%s base=0x%08lx info=0x%08x channel=%u shape=%ux%u count=%u frac_bits=%u bias_q=%ld status_before=0x%08x status_after_start=0x%08x status_after_wait=0x%08x\n",
                rc,
                args.pl_real_layer_dir.c_str(),
                (unsigned long)args.pl_real_layer_cfg.full_base,
                pl_real_layer_result.full_info,
                pl_real_layer_result.channel,
                pl_real_layer_result.width,
                pl_real_layer_result.height,
                pl_real_layer_result.output_count,
                pl_real_layer_result.frac_bits,
                (long)pl_real_layer_result.bias_q,
                pl_real_layer_result.status_before_start,
                pl_real_layer_result.status_after_start,
                pl_real_layer_result.status_after_wait);
            std::fflush(stderr);
            return 8;
        }
        std::fprintf(
            stdout,
            "pl_real_layer rc=0 base=0x%08lx channel=%u shape=%ux%u count=%u frac_bits=%u bias_q=%ld first_acc=%ld last_acc=%ld max_abs_float_err=%.6f status_before=0x%08x status_after_start=0x%08x status_after_wait=0x%08x e2e_us=%u compute_us=%u\n",
            (unsigned long)args.pl_real_layer_cfg.full_base,
            pl_real_layer_result.channel,
            pl_real_layer_result.width,
            pl_real_layer_result.height,
            pl_real_layer_result.output_count,
            pl_real_layer_result.frac_bits,
            (long)pl_real_layer_result.bias_q,
            (long)pl_real_layer_result.first_acc,
            (long)pl_real_layer_result.last_acc,
            pl_real_layer_result.max_abs_float_error,
            pl_real_layer_result.status_before_start,
            pl_real_layer_result.status_after_start,
            pl_real_layer_result.status_after_wait,
            pl_real_layer_result.e2e_us,
            pl_real_layer_result.compute_us);
        std::fflush(stdout);
    }

    if (!args.dump_blob_name.empty()) {
        try {
            if (!args.gray8_path.empty()) {
                std::vector<uint8_t> gray8 = read_u8_file(args.gray8_path);
                const size_t expected = (size_t)args.src_width * (size_t)args.src_height;
                if (gray8.size() != expected) {
                    std::fprintf(stderr, "gray8 input size mismatch bytes=%zu expected=%zu\n", gray8.size(), expected);
                    std::fflush(stderr);
                    return 3;
                }
                rc = detector.extract_blob_from_gray8(
                    gray8.data(),
                    args.src_width,
                    args.src_height,
                    args.dump_blob_name.c_str(),
                    &blob,
                    &stats);
            } else {
                std::vector<float> tensor = read_f32_file(args.tensor_path);
                const size_t expected = (size_t)args.cfg.runtime_input_width * (size_t)args.cfg.runtime_input_height;
                if (tensor.size() != expected) {
                    std::fprintf(stderr, "tensor input size mismatch elems=%zu expected=%zu\n", tensor.size(), expected);
                    std::fflush(stderr);
                    return 4;
                }
                rc = detector.extract_blob_from_runtime_tensor(
                    tensor.data(),
                    args.src_width,
                    args.src_height,
                    args.dump_blob_name.c_str(),
                    &blob,
                    &stats);
            }
        } catch (const std::exception& exc) {
            std::fprintf(stderr, "blob input error: %s\n", exc.what());
            std::fflush(stderr);
            return 9;
        }

        if (rc != 0) {
            std::fprintf(
                stderr,
                "blob extract failed rc=%d blob=%s last_ncnn=%d\n",
                rc,
                args.dump_blob_name.c_str(),
                detector.last_ncnn_status());
            std::fflush(stderr);
            return 10;
        }

        try {
            const std::string blob_bin_path = blob_bin_path_from_prefix(args.dump_blob_out_prefix);
            const std::string blob_json_path = blob_json_path_from_prefix(args.dump_blob_out_prefix);
            write_f32_file(blob_bin_path, blob.values);
            write_blob_metadata_json(blob_json_path, args.dump_blob_name, blob, stats);
            std::fprintf(
                stdout,
                "blob_dump name=%s dims=%d shape=[c=%d,h=%d,w=%d] values=%zu bin=%s json=%s\n",
                args.dump_blob_name.c_str(),
                blob.dims,
                blob.c,
                blob.h,
                blob.w,
                blob.values.size(),
                blob_bin_path.c_str(),
                blob_json_path.c_str());
            std::fflush(stdout);
        } catch (const std::exception& exc) {
            std::fprintf(stderr, "blob write failed: %s\n", exc.what());
            std::fflush(stderr);
            return 11;
        }

        if (args.blob_only) {
            return 0;
        }
    }

    try {
        if (!args.gray8_path.empty()) {
            std::vector<uint8_t> gray8 = read_u8_file(args.gray8_path);
            const size_t expected = (size_t)args.src_width * (size_t)args.src_height;
            if (gray8.size() != expected) {
                std::fprintf(stderr, "gray8 input size mismatch bytes=%zu expected=%zu\n", gray8.size(), expected);
                std::fflush(stderr);
                return 3;
            }
            rc = detector.run_from_gray8(
                gray8.data(),
                args.src_width,
                args.src_height,
                detections,
                IRDET_MAX_DETECTIONS,
                &out_count,
                &stats);
        } else {
            std::vector<float> tensor = read_f32_file(args.tensor_path);
            const size_t expected = (size_t)args.cfg.runtime_input_width * (size_t)args.cfg.runtime_input_height;
            if (tensor.size() != expected) {
                std::fprintf(stderr, "tensor input size mismatch elems=%zu expected=%zu\n", tensor.size(), expected);
                std::fflush(stderr);
                return 4;
            }
            stats.src_width = args.src_width;
            stats.src_height = args.src_height;
            stats.dst_width = args.cfg.runtime_input_width;
            stats.dst_height = args.cfg.runtime_input_height;
            rc = detector.run_from_runtime_tensor(
                tensor.data(),
                args.src_width,
                args.src_height,
                detections,
                IRDET_MAX_DETECTIONS,
                &out_count,
                &stats);
        }
    } catch (const std::exception& exc) {
        std::fprintf(stderr, "input error: %s\n", exc.what());
        std::fflush(stderr);
        return 5;
    }

    if (rc != 0) {
        std::fprintf(
            stderr,
            "run failed rc=%d last_ncnn=%d last_post=%d\n",
            rc,
            detector.last_ncnn_status(),
            detector.last_postprocess_status());
        std::fflush(stderr);
        return 6;
    }

    std::fprintf(
        stdout,
        "pre_in=%ux%u pre_out=%ux%u min=%u max=%u mean_x1000=%ld\n",
        stats.src_width,
        stats.src_height,
        stats.dst_width,
        stats.dst_height,
        (uint32_t)stats.min_pixel,
        (uint32_t)stats.max_pixel,
        (long)stats.mean_x1000);
    std::fflush(stdout);
    print_detections(detections, out_count);
    return 0;
}
