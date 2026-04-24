# IR Zynq Detector

基于 Zynq-7020 的离线红外目标检测部署系统骨架工程。

当前优先目标不是追求模型精度，而是先把工程链路跑通：

1. PC 端读取一张红外图片。
2. 通过 UART 把图像数据送到 Zynq 板端。
3. 板端先完成收图、校验和串口打印。
4. 后续再逐步接入真实模型推理、后处理和 PL 加速。

## 当前架构

- PC 端：数据集整理、训练、模型导出、量化、串口发图
- Zynq PS 端：收图、预处理主控、推理、后处理、UART 输出
- Zynq PL 端：后续加入 resize、normalize、DMA、buffer 等固定功能

当前明确不做：

- 不做整网纯 HDL 重写
- 不做实时红外相机采集
- 第一版不让板端自己解析 `jpg/png`

## 当前确认路线

- 主机系统：Windows
- 工具链：Vivado 2020.2 + Vitis 2020.2
- 数据集：FLIR_ADAS_v2
- 首批类别：`person`、`bicycle`、`car`
- 首版输入链路：PC 解码图片文件，UART 发送灰度像素流
- 板端运行：先裸机，真实模型过难时再考虑 Linux

## 目录结构

```text
ir_zynq_detector/
├─ configs/            # 工程配置
├─ docs/               # 阶段计划、协议、联调文档
├─ hw/vivado/          # Vivado Tcl 脚本
├─ pc/                 # PC 端脚本与工具
├─ vitis/              # Vitis / XSCT 脚本
├─ zynq_pl/            # PL 端 RTL 与 testbench
└─ zynq_ps/            # PS 端 C/C++ 源码
```

## 当前可运行内容

### 1. 占位检测器

- [mock_ir_detector.py](/G:/FPGA/ir_zynq_detector/pc/tools/mock_ir_detector.py)

作用：

- 读取一张图片
- 生成一个占位检测框
- 输出 `class + score + bbox`

这一步用于先打通 “输入图片 -> 输出检测结果” 的格式。

### 2. UART 发图脚本

- [send_uart_image.py](/G:/FPGA/ir_zynq_detector/pc/tools/send_uart_image.py)

作用：

- 读取一张图片文件
- 转成灰度像素流
- 组装 `IRDT` 协议帧
- 通过串口发给板子

协议说明见 [uart_image_protocol.md](/G:/FPGA/ir_zynq_detector/docs/uart_image_protocol.md)。

现在也支持从数据集目录直接选图：

```powershell
python pc\tools\send_uart_image.py --dataset-root D:\datasets\FLIR_ADAS_v2 --index 0 --port COM3 --baud 921600 --wait-ack
```

或者按文件名关键字筛选：

```powershell
python pc\tools\send_uart_image.py --dataset-root D:\datasets\FLIR_ADAS_v2 --match thermal --index 0 --port COM3 --baud 921600 --wait-ack
```

### 3. PS 裸机收图骨架

- [uart_image_receiver_baremetal.c](/G:/FPGA/ir_zynq_detector/zynq_ps/src/uart_image_receiver_baremetal.c)
- [uart_image_proto.c](/G:/FPGA/ir_zynq_detector/zynq_ps/src/uart_image_proto.c)
- [uart_image_proto.h](/G:/FPGA/ir_zynq_detector/zynq_ps/include/uart_image_proto.h)
- [ir_image_preprocess.c](/G:/FPGA/ir_zynq_detector/zynq_ps/src/ir_image_preprocess.c)
- [ir_image_preprocess.h](/G:/FPGA/ir_zynq_detector/zynq_ps/include/ir_image_preprocess.h)

当前目标：

- 接收一帧图像
- 打印宽高、帧大小和校验值
- 在板端完成 `160x128` 的 resize + normalize

### 4. Vivado 硬件平台脚本

- [create_project.tcl](/G:/FPGA/ir_zynq_detector/hw/vivado/create_project.tcl)
- [create_zynq_ps_uart_bd.tcl](/G:/FPGA/ir_zynq_detector/hw/vivado/bd/create_zynq_ps_uart_bd.tcl)

当前硬件平台是最小版本：

- Zynq PS
- DDR
- FIXED_IO
- PS UART1

### 5. Vitis 工程脚本

- [create_baremetal_app.tcl](/G:/FPGA/ir_zynq_detector/vitis/create_baremetal_app.tcl)

作用：

- 根据 Vivado 导出的 XSA 创建 platform
- 创建裸机应用工程
- 导入当前 `zynq_ps` 下的源文件

## 快速开始

### 安装 Python 依赖

```powershell
cd G:\FPGA\ir_zynq_detector
python -m pip install -r pc\requirements.txt
```

### 测试 UART 帧打包

```powershell
python pc\tools\send_uart_image.py --image path\to\test.png --dump-frame build\test_uart.bin
```

### 创建 Vivado 工程并导出 XSA

```powershell
F:\Xilinx\Vivado\2020.2\bin\vivado.bat -mode batch -source hw\vivado\create_project.tcl
```

### 创建 Vitis 裸机应用

```powershell
F:\Xilinx\Vitis\2020.2\bin\xsct.bat vitis\create_baremetal_app.tcl
```

## 文档入口

- 阶段拆解：[stage_plan.md](/G:/FPGA/ir_zynq_detector/docs/stage_plan.md)
- UART 协议：[uart_image_protocol.md](/G:/FPGA/ir_zynq_detector/docs/uart_image_protocol.md)
- 板级联调：[board_bringup_uart.md](/G:/FPGA/ir_zynq_detector/docs/board_bringup_uart.md)

## 当前假设

下面这些假设已经写进当前脚本：

1. 器件型号暂按 `xc7z020clg400-1`
2. 板载串口走 `PS UART1 (MIO 48..49)`
3. 第一阶段先不要求 bitstream，可先导出 XSA 跑裸机

如果其中任意一条和你的板子不一致，把实际日志或现象发回来，我会直接替你改脚本。
