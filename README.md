# IR Zynq Detector

基于 Zynq-7020 的离线红外目标检测部署工程，目标是把 FLIR_ADAS_v2 上训练得到的轻量模型部署到 Zynq 板端，并验证 PS 推理链路与 PL 关键算子加速。

当前工程重点不是追求最终精度，而是把下面这条真实部署链路跑通：

1. PC 端整理 FLIR_ADAS_v2、训练轻量检测模型并导出 ONNX / NCNN。
2. PC 端读取热红外图片，发送灰度图或通过 Linux 网络部署包下发到板端。
3. Zynq PS/Linux 端完成预处理、推理、后处理并输出 `class / score / bbox`。
4. Zynq PL 端验证 depthwise 3x3 卷积加速，并逐步接入真实推理路径。

## 当前状态

- 已完成 UART 收图闭环与裸机收图骨架。
- 已完成 SSDLite + MobileNetV2 三类训练、导出、ONNX、NCNN 运行时链路。
- 已统一固定输入契约为 `NCHW = 1x1x128x160`。
- 已在 AC880 出厂 Linux 上跑通 NCNN 检测 demo。
- 已在板上完成 PL `dw3x3` depthwise 加速器 selftest、full scheduler 验证与真实层回放验证。
- 当前采用“每次上电后通过 U-Boot 临时加载 bitstream + DTB”的方式运行，不改动出厂启动分区。

## 项目结构

```text
ir_zynq_detector/
├─ configs/      # 部署契约和工程配置
├─ docs/         # 方案说明、阶段计划、联调记录、demo 文档
├─ hw/           # Vivado Tcl 和 block design 脚本
├─ pc/           # 训练、导出、评估、打包、上板部署脚本
├─ vitis/        # XSCT / Vitis 工程脚本
├─ zynq_linux/   # Linux 端 NCNN detector 与 PL tool
├─ zynq_pl/      # PL RTL、testbench、AXI MMIO 接口实现
└─ zynq_ps/      # PS 裸机侧预处理、协议、后处理代码
```

## 当前主线

### 1. 训练与导出

- 训练脚本：`pc/scripts/train_ssdlite_ir.py`
- 固定契约训练入口：`pc/scripts/run_formal_train_ssdlite_ir_fixed_v2.ps1`
- ONNX 导出：`pc/scripts/export_ssdlite_ir_runtime_onnx.py`
- NCNN 转换：`pc/scripts/convert_runtime_onnx_to_ncnn.ps1`

当前 active 路线是 `fixed_v2`，对应统一后的模型输入契约：

- `height = 128`
- `width = 160`
- `tensor = 1x1x128x160`

### 2. 裸机 UART 图像链路

- PC 发图：`pc/tools/send_uart_image.py`
- 协议说明：[`docs/uart_image_protocol.md`](docs/uart_image_protocol.md)
- PS 裸机收图：`zynq_ps/src/uart_image_receiver_baremetal.c`
- 预处理：`zynq_ps/src/ir_image_preprocess.c`

UART 传输的是“原始灰度图像流 + 宽高头”，不是模型张量本身；固定张量 `1x1x128x160` 在 PS / Linux 端预处理后生成。

### 3. Linux 真机推理

- Linux detector：`zynq_linux/src/irdet_linux_main.cpp`
- NCNN detector 实现：`zynq_linux/src/irdet_linux_ncnn_detector.cpp`
- demo 打包：`pc/scripts/package_zynq_linux_demo.ps1`
- 板端部署与运行：`pc/scripts/run_ac880_linux_demo.ps1`
- 选 FLIR 图片上板推理：`pc/scripts/run_ac880_linux_image_infer.ps1`

### 4. PL depthwise 3x3 加速验证

- RTL：`zynq_pl/rtl/mobilenet_dw3x3_accel.sv`
- full scheduler：`zynq_pl/rtl/mobilenet_dw3x3_channel_full_axi.sv`
- bare-metal selftest：`vitis/run_dw3x3_selftest_on_board.tcl`
- Linux tool：`zynq_linux/src/irdet_linux_pl_dw3x3_tool.cpp`
- demo 文档：[`docs/pl_dw3x3_full_scheduler_demo.md`](docs/pl_dw3x3_full_scheduler_demo.md)

## 推荐使用方式

### Windows 端准备

- Vivado 2020.2
- Vitis 2020.2
- Python 3.x
- FLIR_ADAS_v2 数据集

安装 Python 依赖：

```powershell
cd G:\FPGA\ir_zynq_detector
python -m pip install -r pc\requirements.txt
```

### 训练固定契约模型

```powershell
powershell -ExecutionPolicy Bypass -File .\pc\scripts\run_formal_train_ssdlite_ir_fixed_v2.ps1 -DatasetRoot "G:\chormxiazai\FLIR_ADAS_v2"
```

### 导出 fixed_v2 运行时模型

```powershell
powershell -ExecutionPolicy Bypass -File .\pc\scripts\run_export_ssdlite_ir_fixed_v2.ps1
```

### 板端 Linux demo

如果板子已上电并走临时 U-Boot 启动流程，可运行：

```powershell
powershell -ExecutionPolicy Bypass -File .\pc\scripts\run_ac880_temp_uboot_demo.ps1 -RepoRoot G:\FPGA\ir_zynq_detector -ComPort COM3 -BaudRate 115200 -Mode gray8_pl_real_layer
```

### 从 FLIR 数据集选图并在板端推理

```powershell
powershell -ExecutionPolicy Bypass -File .\pc\scripts\run_ac880_linux_image_infer.ps1 -DatasetRoot "G:\chormxiazai\FLIR_ADAS_v2" -Match "images_thermal_val\data" -Index 0 -Pick first -RefreshBundle
```

## 关键文档

- 阶段计划：[`docs/stage_plan.md`](docs/stage_plan.md)
- GitHub 学习导图：[`docs/github_learning_guide.md`](docs/github_learning_guide.md)
- 当前验证快照：[`docs/current_verified_snapshot.md`](docs/current_verified_snapshot.md)
- UART 协议：[`docs/uart_image_protocol.md`](docs/uart_image_protocol.md)
- 板端带起：[`docs/board_bringup_uart.md`](docs/board_bringup_uart.md)
- 部署契约：[`docs/deployment_contract.md`](docs/deployment_contract.md)
- 模型评估与导出：[`docs/model_eval_and_export.md`](docs/model_eval_and_export.md)
- 真部署路线：[`docs/true_inference_runtime_plan.md`](docs/true_inference_runtime_plan.md)
- AC880 U-Boot 临时启动：[`docs/ac880_boot_pl_preload.md`](docs/ac880_boot_pl_preload.md)

## 当前未提交到仓库的内容

为了保持仓库干净，下面这些内容默认不进 Git：

- 虚拟环境、Vivado / Xilinx 缓存
- `build/` 下的生成产物
- 下载的第三方工具与模型二进制
- 各类日志、仿真缓存、bitstream、xsa、elf

这些内容都可以通过仓库内脚本在本地重新生成或重新打包。
