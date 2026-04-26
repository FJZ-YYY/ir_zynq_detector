# 当前验证快照

这份文档记录当前仓库对应的“已验证状态”，方便在 GitHub 上直接查看。

它不是未来规划，而是“到现在为止已经完成什么”。

## 平台与契约

- 平台：AC880 / Zynq-7020
- PS：Linux + ncnn detector
- PL：depthwise 3x3 full-channel scheduler
- 模型输入契约固定为：
  - `NCHW = 1x1x128x160`
  - 日志里的 `runtime_in=160x128` 表示 `width x height`

## 已经稳定的关键模式

### 1. `gray8`

路径：

```text
gray8 -> preprocess -> full ncnn detector -> SSD postprocess -> bbox
```

作用：

- 作为完整 detector 的 CPU / ncnn 基线模式

### 2. `runtime_dw_pl_compare`

路径：

```text
runtime blob extract -> channel=11 -> CPU reference vs PL compare
```

已经验证：

- 运行时真实中间 blob 可以从 ncnn 中拿出来
- 可以送入现有 PL full scheduler
- CPU / PL 结果对齐

典型通过输出：

```text
runtime_dw_pl_compare rc=0
channel=11
shape=40x32
count=1280
max_abs_acc_err=0
```

### 3. `inpath_dw_cpu_full`

路径：

```text
prefix -> CPU full depthwise -> suffix -> bbox
```

已经验证：

- 目标层切点正确
- suffix reinject blob 正确
- 不需要拆成两个 ncnn 模型文件

典型通过输出：

```text
inpath_dw_cpu_full rc=0
backend=cpu_depthwise
shape=144x40x32
det_count=4
```

### 4. `inpath_dw_pl_full`

路径：

```text
prefix -> PL loop all 144 channels -> ReLU6 -> suffix -> bbox
```

这是当前阶段最重要的真机成果。

已经验证：

- PL full scheduler 循环所有 channel 可行
- 拼回完整 depthwise 输出 tensor 可行
- 输出 reinject 到 suffix 后，detector 仍正常输出 bbox

典型通过输出：

```text
inpath_dw_pl_full rc=0
backend=pl_depthwise_loop_all_channels
channels=144
pl_calls=144
max_abs_acc_err=0
det_count=4
```

## 当前确定的关键 blob / layer

- 目标层名：
  - `backbone.features.0.3.conv.1.0`
- target input blob：
  - `/inner/backbone/features.0/features.0.3/conv/conv.0/conv.0.2/Clip_output_0`
- target output blob：
  - `/inner/backbone/features.0/features.0.3/conv/conv.1/conv.1.2/Clip_output_0`

## 当前确定的 PL 侧关键信息

- full scheduler AXI base：
  - `0x43c10000`
- old single-window IP base：
  - `0x43c00000`
- 当前 RTL 宽高契约：
  - `MAX_W=40`
  - `MAX_H=32`

这个宽高修正非常关键，因为之前的卡死根因就是：

```text
旧 RTL 用了 MAX_W=32, MAX_H=40，
而真实层导出 shape 是 W=40, H=32。
```

## 当前 PC 可视化 demo 状态

现在仓库里已经有：

- [pc/tools/board_visual_infer.py](../pc/tools/board_visual_infer.py)
- [pc/tools/board_visual_demo_gui.py](../pc/tools/board_visual_demo_gui.py)
- [docs/visual_demo.md](./visual_demo.md)

已具备能力：

- 在 PC 端选择一张 FLIR thermal 图片
- 转成 `gray8 raw`
- 上传到板子
- 调用 `gray8 / inpath_dw_cpu_full / inpath_dw_pl_full`
- 解析 `det_count / detN class / score / bbox`
- 在原图上画框并保存结果图

## 板子断电后的当前处理方式

当前项目仍然坚持：

- 不做 boot 持久化
- 不改 SD 卡默认 boot 分区

所以断电后要区分两件事：

1. Linux 文件系统里的 `/home/root/irdet_demo` 可能还在
2. 当前 PL bitstream 配置不会保留

因此：

- `gray8` / `inpath_dw_cpu_full` 往往只要 Linux + SSH 恢复即可
- `inpath_dw_pl_full` 一般要先重新 program 当前 bitstream

仓库现在已经提供：

- CLI：`--recover-pl`
- GUI：`Recover PL` 按钮与 `Auto Recover PL`

## 当前不做的事情

下面这些事情当前都明确没有进入本阶段：

- 不重训模型
- 不改输入契约
- 不做 boot 持久化
- 不上 DMA
- 不重写 PL full scheduler
- 不写 ncnn custom layer

## 一句话总结当前阶段

当前仓库最核心的结论是：

```text
PL depthwise 输出已经不再只是旁路 compare，
而是已经真实进入板端 detector 推理路径，并产出正常 bbox。
```
