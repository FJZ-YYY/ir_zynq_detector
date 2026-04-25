#include <errno.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>

#include <chrono>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

extern "C" {
#include "ir_pl_dw3x3.h"
#include "ir_pl_dw3x3_full.h"
#include "ir_pl_dw3x3_full_channel_data.h"
#include "ir_pl_dw3x3_realcase_batch_data.h"
#include "ir_pl_dw3x3_realcase_channel_data.h"
#include "ir_pl_dw3x3_realcase_data.h"
}

namespace {

constexpr uintptr_t kDefaultDw3x3Base = 0x43C00000u;
constexpr uintptr_t kDefaultDw3x3FullBase = 0x43C10000u;
constexpr uintptr_t kDefaultAxiGpioBase = 0x41200000u;

constexpr uint32_t kAxiGpioDataOffset = 0x00u;
constexpr uint32_t kAxiGpioTriOffset = 0x04u;
constexpr uint32_t kAxiGpioPattern = 0xA5A55A5Au;

struct cli_args_t {
    uintptr_t dw3x3_base = kDefaultDw3x3Base;
    uintptr_t full_base = kDefaultDw3x3FullBase;
    uintptr_t axi_gpio_base = kDefaultAxiGpioBase;
    bool skip_gpio = false;
    bool run_single_window = false;
    bool run_realcase = false;
    bool run_batch = false;
    bool run_channel = false;
    bool run_full = false;
};

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
        if (region == nullptr) {
            std::cerr << "MMIO read outside mapped range addr=0x" << to_hex(addr) << std::endl;
            return 0U;
        }
        const size_t offset = region->page_offset + (size_t)(addr - region->request_base);
        return *(volatile uint32_t*)(region->mapped + offset);
    }

    void write32(uintptr_t addr, uint32_t value) const {
        const mapped_region_t* region = find_region(addr);
        if (region == nullptr) {
            std::cerr << "MMIO write outside mapped range addr=0x" << to_hex(addr) << std::endl;
            return;
        }
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
        return nullptr;
    }

    int fd_ = -1;
    size_t page_size_ = 4096U;
    std::vector<mapped_region_t> regions_;
};

static uint32_t linux_mmio_read32(void* ctx, uintptr_t addr) {
    if (ctx == nullptr) {
        return 0U;
    }
    return static_cast<linux_mmio_t*>(ctx)->read32(addr);
}

static void linux_mmio_write32(void* ctx, uintptr_t addr, uint32_t value) {
    if (ctx == nullptr) {
        return;
    }
    static_cast<linux_mmio_t*>(ctx)->write32(addr, value);
}

static int32_t cpu_ref_q(const int16_t* window, const int16_t* weights, int32_t bias_q) {
    int32_t acc = bias_q;
    uint32_t idx;
    for (idx = 0U; idx < IRDET_DW3X3_WINDOW_TAPS; ++idx) {
        acc += (int32_t)window[idx] * (int32_t)weights[idx];
    }
    return acc;
}

static uint32_t elapsed_us(
    const std::chrono::steady_clock::time_point& start_time,
    const std::chrono::steady_clock::time_point& end_time) {
    return (uint32_t)std::chrono::duration_cast<std::chrono::microseconds>(end_time - start_time).count();
}

static void print_usage() {
    std::cout
        << "Usage: irdet_linux_pl_dw3x3_tool [--all] [--single-window] [--realcase] [--batch] [--channel] [--full]\n"
        << "                                  [--dw3x3-base 0x43C00000] [--full-base 0x43C10000]\n"
        << "                                  [--axi-gpio-base 0x41200000] [--skip-gpio]\n";
}

static bool parse_uintptr(const std::string& text, uintptr_t* out_value) {
    char* end_ptr = nullptr;
    const unsigned long long parsed = std::strtoull(text.c_str(), &end_ptr, 0);
    if (end_ptr == nullptr || *end_ptr != '\0') {
        return false;
    }
    *out_value = (uintptr_t)parsed;
    return true;
}

static bool parse_args(int argc, char** argv, cli_args_t* args) {
    bool any_selected = false;
    for (int i = 1; i < argc; ++i) {
        const std::string opt(argv[i]);
        if (opt == "--all") {
            args->run_single_window = true;
            args->run_realcase = true;
            args->run_batch = true;
            args->run_channel = true;
            args->run_full = true;
            any_selected = true;
        } else if (opt == "--single-window") {
            args->run_single_window = true;
            any_selected = true;
        } else if (opt == "--realcase") {
            args->run_realcase = true;
            any_selected = true;
        } else if (opt == "--batch") {
            args->run_batch = true;
            any_selected = true;
        } else if (opt == "--channel") {
            args->run_channel = true;
            any_selected = true;
        } else if (opt == "--full") {
            args->run_full = true;
            any_selected = true;
        } else if (opt == "--dw3x3-base") {
            if ((i + 1) >= argc || !parse_uintptr(argv[++i], &args->dw3x3_base)) {
                return false;
            }
        } else if (opt == "--full-base") {
            if ((i + 1) >= argc || !parse_uintptr(argv[++i], &args->full_base)) {
                return false;
            }
        } else if (opt == "--axi-gpio-base") {
            if ((i + 1) >= argc || !parse_uintptr(argv[++i], &args->axi_gpio_base)) {
                return false;
            }
        } else if (opt == "--skip-gpio") {
            args->skip_gpio = true;
        } else if (opt == "--help" || opt == "-h") {
            return false;
        } else {
            std::cerr << "Unknown option: " << opt << std::endl;
            return false;
        }
    }

    if (!any_selected) {
        args->run_single_window = true;
        args->run_realcase = true;
        args->run_batch = true;
        args->run_channel = true;
        args->run_full = true;
    }
    return true;
}

static int run_axi_gpio_probe(const cli_args_t& args, linux_mmio_t* mmio) {
    if (args.skip_gpio) {
        return 0;
    }
    std::cout << "AXI GPIO probe base=0x" << linux_mmio_t::to_hex(args.axi_gpio_base) << " writing TRI..." << std::endl;
    mmio->write32(args.axi_gpio_base + kAxiGpioTriOffset, 0x00000000U);
    std::cout << "AXI GPIO probe writing DATA=0x" << linux_mmio_t::to_hex(kAxiGpioPattern) << "..." << std::endl;
    mmio->write32(args.axi_gpio_base + kAxiGpioDataOffset, kAxiGpioPattern);
    std::cout << "AXI GPIO probe reading DATA..." << std::endl;
    const uint32_t readback = mmio->read32(args.axi_gpio_base + kAxiGpioDataOffset);
    std::cout << "AXI GPIO probe readback=0x" << linux_mmio_t::to_hex(readback) << std::endl;
    if (readback != kAxiGpioPattern) {
        std::cerr << "AXI GPIO probe mismatch expected=0x" << linux_mmio_t::to_hex(kAxiGpioPattern)
                  << " got=0x" << linux_mmio_t::to_hex(readback) << std::endl;
        return -1;
    }
    return 0;
}

static int run_single_window_test(const cli_args_t& args, linux_mmio_t* mmio) {
    static const int16_t k_window[IRDET_DW3X3_WINDOW_TAPS] = {1, 2, 3, 4, 5, 6, 7, 8, 9};
    static const int16_t k_weights[IRDET_DW3X3_WINDOW_TAPS] = {1, 1, 1, 1, 1, 1, 1, 1, 1};

    irdet_dw3x3_dev_t dev;
    int32_t out_value = 0;
    int rc;

    irdet_dw3x3_init(
        &dev,
        args.dw3x3_base,
        IRDET_DW3X3_WINDOW_W,
        IRDET_DW3X3_WINDOW_H,
        mmio,
        linux_mmio_read32,
        linux_mmio_write32);

    std::cout << "PL dw3x3 starting AXI MMIO single-window test..." << std::endl;
    rc = run_axi_gpio_probe(args, mmio);
    if (rc != 0) {
        return rc;
    }

    std::cout << "PL dw3x3 reading INFO register..." << std::endl;
    std::cout << "PL dw3x3 info=0x" << linux_mmio_t::to_hex(mmio->read32(args.dw3x3_base + IRDET_DW3X3_REG_INFO))
              << std::endl;
    std::cout << "PL dw3x3 configure window..." << std::endl;
    rc = irdet_dw3x3_configure(&dev, IRDET_DW3X3_WINDOW_W, IRDET_DW3X3_WINDOW_H, 0);
    if (rc != 0) {
        return -10;
    }
    std::cout << "PL dw3x3 write pixels..." << std::endl;
    rc = irdet_dw3x3_write_window_q(&dev, k_window);
    if (rc != 0) {
        return -11;
    }
    std::cout << "PL dw3x3 write weights..." << std::endl;
    rc = irdet_dw3x3_write_weights_q(&dev, k_weights);
    if (rc != 0) {
        return -12;
    }
    std::cout << "PL dw3x3 start core..." << std::endl;
    rc = irdet_dw3x3_start(&dev);
    if (rc != 0) {
        return -13;
    }
    std::cout << "PL dw3x3 wait done..." << std::endl;
    rc = irdet_dw3x3_wait_done(&dev, 1000000U);
    if (rc != 0) {
        std::cerr << "PL dw3x3 wait done failed rc=" << rc
                  << " status=0x" << linux_mmio_t::to_hex(irdet_dw3x3_read_status(&dev)) << std::endl;
        return -14;
    }
    std::cout << "PL dw3x3 read output..." << std::endl;
    rc = irdet_dw3x3_read_output_q(&dev, &out_value);
    if (rc != 0) {
        return -15;
    }
    if (out_value != 45) {
        std::cerr << "PL dw3x3 mismatch exp=45 got=" << out_value << std::endl;
        return -16;
    }

    std::cout << "PL dw3x3 selftest PASS base=0x" << linux_mmio_t::to_hex(args.dw3x3_base)
              << " mode=single_window result=" << out_value << std::endl;
    return 0;
}

static int run_realcase_window(const cli_args_t& args, linux_mmio_t* mmio) {
    irdet_dw3x3_dev_t dev;
    int32_t out_value = 0;
    int rc;
    const int32_t cpu_expected = cpu_ref_q(
        IRDET_DW3X3_REALCASE_WINDOW_Q,
        IRDET_DW3X3_REALCASE_WEIGHT_Q,
        IRDET_DW3X3_REALCASE_BIAS_Q);

    irdet_dw3x3_init(
        &dev,
        args.dw3x3_base,
        IRDET_DW3X3_WINDOW_W,
        IRDET_DW3X3_WINDOW_H,
        mmio,
        linux_mmio_read32,
        linux_mmio_write32);

    std::cout << "PL dw3x3 starting real MobileNetV2 window replay channel=" << IRDET_DW3X3_REALCASE_CHANNEL
              << " y=" << IRDET_DW3X3_REALCASE_Y
              << " x=" << IRDET_DW3X3_REALCASE_X << "..." << std::endl;

    if (cpu_expected != IRDET_DW3X3_REALCASE_EXPECTED_ACC) {
        std::cerr << "PL dw3x3 realcase CPU reference mismatch expected=" << IRDET_DW3X3_REALCASE_EXPECTED_ACC
                  << " cpu=" << cpu_expected << std::endl;
        return -20;
    }

    rc = irdet_dw3x3_run_window_q(
        &dev,
        IRDET_DW3X3_REALCASE_WINDOW_Q,
        IRDET_DW3X3_REALCASE_WEIGHT_Q,
        IRDET_DW3X3_REALCASE_BIAS_Q,
        &out_value,
        1000000U);
    if (rc != 0) {
        std::cerr << "PL dw3x3 realcase run failed rc=" << rc << std::endl;
        return -21;
    }
    if (out_value != IRDET_DW3X3_REALCASE_EXPECTED_ACC) {
        std::cerr << "PL dw3x3 realcase mismatch expected_acc=" << IRDET_DW3X3_REALCASE_EXPECTED_ACC
                  << " pl_acc=" << out_value << " scale=" << IRDET_DW3X3_REALCASE_ACC_SCALE << std::endl;
        return -22;
    }

    std::cout << "PL dw3x3 realcase PASS channel=" << IRDET_DW3X3_REALCASE_CHANNEL
              << " y=" << IRDET_DW3X3_REALCASE_Y
              << " x=" << IRDET_DW3X3_REALCASE_X
              << " expected_acc=" << IRDET_DW3X3_REALCASE_EXPECTED_ACC
              << " pl_acc=" << out_value
              << " scale=" << IRDET_DW3X3_REALCASE_ACC_SCALE << std::endl;
    return 0;
}

static int replay_windows_timed(
    const char* name,
    uintptr_t base_addr,
    linux_mmio_t* mmio,
    uint32_t channel,
    uint32_t count,
    uint32_t patch_h,
    uint32_t patch_w,
    const int16_t windows[][IRDET_DW3X3_WINDOW_TAPS],
    const uint16_t* ys,
    const uint16_t* xs,
    const int16_t* weights,
    int32_t bias_q,
    const int32_t* expected_acc,
    uint32_t acc_scale) {
    irdet_dw3x3_dev_t dev;
    auto t0 = std::chrono::steady_clock::now();
    auto t1 = t0;
    int32_t first_acc = 0;
    int32_t last_acc = 0;
    uint32_t idx;
    int rc;

    std::cout << "PL dw3x3 starting real MobileNetV2 " << name
              << " replay channel=" << channel
              << " count=" << count
              << " patch=" << patch_h << "x" << patch_w << "..." << std::endl;

    for (idx = 0U; idx < count; ++idx) {
        const int32_t cpu_expected = cpu_ref_q(windows[idx], weights, bias_q);
        if (cpu_expected != expected_acc[idx]) {
            std::cerr << "PL dw3x3 " << name << " CPU mismatch idx=" << idx
                      << " y=" << ys[idx] << " x=" << xs[idx]
                      << " expected=" << expected_acc[idx]
                      << " cpu=" << cpu_expected << std::endl;
            return -30;
        }
    }
    t1 = std::chrono::steady_clock::now();
    const uint32_t cpu_us = elapsed_us(t0, t1);

    irdet_dw3x3_init(
        &dev,
        base_addr,
        IRDET_DW3X3_WINDOW_W,
        IRDET_DW3X3_WINDOW_H,
        mmio,
        linux_mmio_read32,
        linux_mmio_write32);

    t0 = std::chrono::steady_clock::now();
    rc = irdet_dw3x3_configure(&dev, IRDET_DW3X3_WINDOW_W, IRDET_DW3X3_WINDOW_H, bias_q);
    if (rc != 0) {
        std::cerr << "PL dw3x3 " << name << " configure failed rc=" << rc << std::endl;
        return -31;
    }
    rc = irdet_dw3x3_write_weights_q(&dev, weights);
    if (rc != 0) {
        std::cerr << "PL dw3x3 " << name << " write weights failed rc=" << rc << std::endl;
        return -32;
    }

    for (idx = 0U; idx < count; ++idx) {
        int32_t out_value = 0;
        rc = irdet_dw3x3_write_window_q(&dev, windows[idx]);
        if (rc != 0) {
            std::cerr << "PL dw3x3 " << name << " write window failed idx=" << idx
                      << " y=" << ys[idx] << " x=" << xs[idx] << " rc=" << rc << std::endl;
            return -33;
        }
        rc = irdet_dw3x3_start(&dev);
        if (rc != 0) {
            std::cerr << "PL dw3x3 " << name << " start failed idx=" << idx
                      << " y=" << ys[idx] << " x=" << xs[idx] << " rc=" << rc << std::endl;
            return -34;
        }
        rc = irdet_dw3x3_wait_done(&dev, 1000000U);
        if (rc != 0) {
            std::cerr << "PL dw3x3 " << name << " wait failed idx=" << idx
                      << " y=" << ys[idx] << " x=" << xs[idx]
                      << " rc=" << rc
                      << " status=0x" << linux_mmio_t::to_hex(irdet_dw3x3_read_status(&dev)) << std::endl;
            return -35;
        }
        rc = irdet_dw3x3_read_output_q(&dev, &out_value);
        if (rc != 0) {
            std::cerr << "PL dw3x3 " << name << " read failed idx=" << idx
                      << " y=" << ys[idx] << " x=" << xs[idx] << " rc=" << rc << std::endl;
            return -36;
        }
        if (out_value != expected_acc[idx]) {
            std::cerr << "PL dw3x3 " << name << " mismatch idx=" << idx
                      << " y=" << ys[idx] << " x=" << xs[idx]
                      << " expected_acc=" << expected_acc[idx]
                      << " pl_acc=" << out_value << std::endl;
            return -37;
        }
        if (idx == 0U) {
            first_acc = out_value;
        }
        last_acc = out_value;
    }
    t1 = std::chrono::steady_clock::now();
    const uint32_t pl_us = elapsed_us(t0, t1);

    std::cout << "PL dw3x3 " << name
              << " PASS channel=" << channel
              << " count=" << count
              << " first_acc=" << first_acc
              << " last_acc=" << last_acc
              << " scale=" << acc_scale
              << " cpu_us=" << cpu_us
              << " pl_us=" << pl_us
              << " pl_per_window_us_x1000=" << ((uint64_t)pl_us * 1000ULL) / (uint64_t)count
              << std::endl;
    return 0;
}

static int run_full_scheduler(const cli_args_t& args, linux_mmio_t* mmio) {
    irdet_dw3x3_full_dev_t dev;
    uint32_t idx;
    int32_t first_acc = 0;
    int32_t last_acc = 0;
    int rc;

    irdet_dw3x3_full_init(
        &dev,
        args.full_base,
        IRDET_DW3X3_FULL_CH_WIDTH,
        IRDET_DW3X3_FULL_CH_HEIGHT,
        mmio,
        linux_mmio_read32,
        linux_mmio_write32);

    std::cout << "PL dw3x3 full scheduler present at 0x" << linux_mmio_t::to_hex(args.full_base)
              << " info=0x" << linux_mmio_t::to_hex(mmio->read32(args.full_base + IRDET_DW3X3_FULL_REG_INFO))
              << std::endl;
    std::cout << "PL dw3x3 starting full-channel scheduler channel=" << IRDET_DW3X3_FULL_CH_CHANNEL
              << " count=" << IRDET_DW3X3_FULL_CH_COUNT
              << " shape=" << IRDET_DW3X3_FULL_CH_HEIGHT << "x" << IRDET_DW3X3_FULL_CH_WIDTH
              << "..." << std::endl;

    const auto t0 = std::chrono::steady_clock::now();
    rc = irdet_dw3x3_full_configure(
        &dev,
        IRDET_DW3X3_FULL_CH_WIDTH,
        IRDET_DW3X3_FULL_CH_HEIGHT,
        IRDET_DW3X3_FULL_CH_BIAS_Q);
    if (rc != 0) {
        std::cerr << "PL dw3x3 full configure failed rc=" << rc << std::endl;
        return -40;
    }
    rc = irdet_dw3x3_full_write_feature_q(&dev, IRDET_DW3X3_FULL_CH_INPUT_Q, IRDET_DW3X3_FULL_CH_COUNT);
    if (rc != 0) {
        std::cerr << "PL dw3x3 full write feature failed rc=" << rc << std::endl;
        return -41;
    }
    rc = irdet_dw3x3_full_write_weights_q(&dev, IRDET_DW3X3_FULL_CH_WEIGHT_Q);
    if (rc != 0) {
        std::cerr << "PL dw3x3 full write weights failed rc=" << rc << std::endl;
        return -42;
    }

    const auto t_compute0 = std::chrono::steady_clock::now();
    rc = irdet_dw3x3_full_start(&dev);
    if (rc != 0) {
        std::cerr << "PL dw3x3 full start failed rc=" << rc << std::endl;
        return -43;
    }
    rc = irdet_dw3x3_full_wait_done(&dev, 10000000U);
    const auto t_compute1 = std::chrono::steady_clock::now();
    if (rc != 0) {
        std::cerr << "PL dw3x3 full wait failed rc=" << rc
                  << " status=0x" << linux_mmio_t::to_hex(irdet_dw3x3_full_read_status(&dev)) << std::endl;
        return -44;
    }

    for (idx = 0U; idx < IRDET_DW3X3_FULL_CH_COUNT; ++idx) {
        int32_t out_value = 0;
        rc = irdet_dw3x3_full_read_output_q(&dev, idx, &out_value);
        if (rc != 0) {
            std::cerr << "PL dw3x3 full read output failed idx=" << idx << " rc=" << rc << std::endl;
            return -45;
        }
        if (out_value != IRDET_DW3X3_FULL_CH_EXPECTED_ACC[idx]) {
            std::cerr << "PL dw3x3 full mismatch idx=" << idx
                      << " expected_acc=" << IRDET_DW3X3_FULL_CH_EXPECTED_ACC[idx]
                      << " pl_acc=" << out_value << std::endl;
            return -46;
        }
        if (idx == 0U) {
            first_acc = out_value;
        }
        last_acc = out_value;
    }

    const auto t1 = std::chrono::steady_clock::now();
    const uint32_t e2e_us = elapsed_us(t0, t1);
    const uint32_t compute_us = elapsed_us(t_compute0, t_compute1);
    std::cout << "PL dw3x3 full scheduler PASS channel=" << IRDET_DW3X3_FULL_CH_CHANNEL
              << " count=" << IRDET_DW3X3_FULL_CH_COUNT
              << " first_acc=" << first_acc
              << " last_acc=" << last_acc
              << " e2e_us=" << e2e_us
              << " compute_us=" << compute_us
              << " e2e_per_output_us_x1000=" << ((uint64_t)e2e_us * 1000ULL) / (uint64_t)IRDET_DW3X3_FULL_CH_COUNT
              << std::endl;
    return 0;
}

}  // namespace

int main(int argc, char** argv) {
    cli_args_t args;

    if (!parse_args(argc, argv, &args)) {
        print_usage();
        return 1;
    }

    try {
        linux_mmio_t mmio;
        mmio.ensure_region(args.dw3x3_base, 0x1000U);
        if (!args.skip_gpio) {
            mmio.ensure_region(args.axi_gpio_base, 0x1000U);
        }
        if (args.run_full) {
            mmio.ensure_region(args.full_base, 0x1000U);
        }

        std::cout << "IR detector Linux PL dw3x3 tool" << std::endl;
        std::cout << "Using /dev/mem MMIO dw3x3=0x" << linux_mmio_t::to_hex(args.dw3x3_base)
                  << " full=0x" << linux_mmio_t::to_hex(args.full_base)
                  << " gpio=0x" << linux_mmio_t::to_hex(args.axi_gpio_base) << std::endl;

        if (args.run_single_window) {
            const int rc = run_single_window_test(args, &mmio);
            if (rc != 0) {
                return rc;
            }
        }
        if (args.run_realcase) {
            const int rc = run_realcase_window(args, &mmio);
            if (rc != 0) {
                return rc;
            }
        }
        if (args.run_batch) {
            const int rc = replay_windows_timed(
                "batch",
                args.dw3x3_base,
                &mmio,
                IRDET_DW3X3_BATCH_CHANNEL,
                IRDET_DW3X3_BATCH_COUNT,
                IRDET_DW3X3_BATCH_PATCH_H,
                IRDET_DW3X3_BATCH_PATCH_W,
                IRDET_DW3X3_BATCH_WINDOW_Q,
                IRDET_DW3X3_BATCH_Y,
                IRDET_DW3X3_BATCH_X,
                IRDET_DW3X3_BATCH_WEIGHT_Q,
                IRDET_DW3X3_BATCH_BIAS_Q,
                IRDET_DW3X3_BATCH_EXPECTED_ACC,
                IRDET_DW3X3_BATCH_ACC_SCALE);
            if (rc != 0) {
                return rc;
            }
        }
        if (args.run_channel) {
            const int rc = replay_windows_timed(
                "channel",
                args.dw3x3_base,
                &mmio,
                IRDET_DW3X3_CHANNEL_CHANNEL,
                IRDET_DW3X3_CHANNEL_COUNT,
                IRDET_DW3X3_CHANNEL_PATCH_H,
                IRDET_DW3X3_CHANNEL_PATCH_W,
                IRDET_DW3X3_CHANNEL_WINDOW_Q,
                IRDET_DW3X3_CHANNEL_Y,
                IRDET_DW3X3_CHANNEL_X,
                IRDET_DW3X3_CHANNEL_WEIGHT_Q,
                IRDET_DW3X3_CHANNEL_BIAS_Q,
                IRDET_DW3X3_CHANNEL_EXPECTED_ACC,
                IRDET_DW3X3_CHANNEL_ACC_SCALE);
            if (rc != 0) {
                return rc;
            }
        }
        if (args.run_full) {
            const int rc = run_full_scheduler(args, &mmio);
            if (rc != 0) {
                return rc;
            }
        }
    } catch (const std::exception& exc) {
        std::cerr << "fatal: " << exc.what() << std::endl;
        return 100;
    }

    std::cout << "PL dw3x3 linux tool rc=0" << std::endl;
    return 0;
}
