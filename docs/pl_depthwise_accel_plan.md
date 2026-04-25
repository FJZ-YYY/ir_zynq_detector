# PL Depthwise Accel Plan

## 当前定位

本项目当前采用：

- PC 端完成训练、评估、模型导出
- Zynq PS 端负责图像接收、预处理主流程、推理控制、检测后处理
- Zynq PL 端负责关键算子级加速验证，而不是整网硬件化

当前已经确定的 PL 加速路线是：

- 选择 `MobileNetV2` 中一个代表性的 `depthwise 3x3` 卷积层
- 先做单层算子级验证
- 后续再扩展到更完整的 block 或更多层

## 推荐目标层

第一版默认目标层：

- `backbone.features.0.3.conv.1.0`

选择原因：

- 属于 `MobileNetV2` backbone 的真实 `depthwise 3x3` 卷积
- `stride=1`
- 通道数中等：`144`
- 特征图尺寸仍有代表性，适合展示行缓冲和滑窗结构
- 比后段的超大通道层更容易在 Zynq-7020 上先完成

对应相邻层：

- BN: `backbone.features.0.3.conv.1.1`
- ReLU6: `backbone.features.0.3.conv.1.2`

## 当前已完成

- 真实模型训练完成，部署候选模型为 `best.pt`
- 真实 ONNX 已导出
- 当前导出格式为 raw-head：
  - `bbox_regression`
  - `cls_logits`
  - `anchors_xyxy`
- 已新增 PC 端评估脚本
- 已新增目标 depthwise 层导出脚本

## 接下来的实施顺序

### 第 1 步：PC 端正式评估

目标：

- 计算 `mAP50`
- 计算 `mAP50_95`
- 输出三类目标的 AP
- 保存验证图可视化结果

对应脚本：

- `pc/scripts/eval_ssdlite_ir.py`

### 第 2 步：导出 PL 层验证数据

目标：

- 从真实模型中导出目标 depthwise 层的：
  - 输入特征图
  - BN 融合后的权重
  - BN 融合后的 bias
  - BN 后 golden 输出
  - ReLU6 后 golden 输出

对应脚本：

- `pc/scripts/export_depthwise_layer_case.py`

### 第 3 步：PL 端实现 depthwise 3x3 加速模块

目标：

- 建立稳定的单层加速 RTL 模块
- 支持后续 testbench 和 PS/PL 联调

第一版建议接口：

- 时钟、复位
- 输入特征图流
- 权重加载接口
- 输出特征图流

### 第 4 步：testbench 验证

目标：

- 使用导出的 golden 数据比对 RTL 输出
- 验证：
  - 维度正确
  - 数值正确
  - 边界和 padding 正确

### 第 5 步：PS + PL 联调

目标：

- PS 向 PL 发送目标层输入特征图
- PL 完成 depthwise 3x3 计算
- PS 接收输出并与 golden 结果比对

## 工程目标边界

本阶段不做：

- 整个检测网络全部硬件化
- 一开始就做多个层级联
- 第一版就做 depthwise + pointwise 完整 bottleneck

本阶段重点是：

- 证明模型中的关键推理算子可以由 PL 加速
- 证明 PS + PL 协同链路成立
- 形成完整、可答辩、可扩展的工程闭环
