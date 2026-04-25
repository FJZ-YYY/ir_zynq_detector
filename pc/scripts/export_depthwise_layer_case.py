#!/usr/bin/env python3
"""Export a representative MobileNetV2 depthwise layer case for PL-side acceleration validation."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from pc.models.flir_ir_dataset import FlirCocoDetectionDataset
from pc.models.ssdlite_mobilenetv2_ir import LEGACY_BRIDGE_INPUT_CONTRACT, build_ssdlite_mobilenetv2_ir


DEFAULT_LAYER_NAME = "backbone.features.0.3.conv.1.0"


def require_torch() -> Any:
    try:
        import torch
    except ImportError as exc:  # pragma: no cover - runtime dependency
        raise RuntimeError("PyTorch is required for layer export.") from exc
    return torch


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export one depthwise 3x3 layer case for PL validation.")
    parser.add_argument(
        "--checkpoint",
        type=Path,
        default=Path("build/train_ssdlite_ir_formal/best.pt"),
        help="Path to the trained checkpoint.",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("build/flir_thermal_3cls/dataset_manifest.json"),
        help="Prepared FLIR manifest path.",
    )
    parser.add_argument("--split", choices=("train", "val"), default="val", help="Dataset split for case selection.")
    parser.add_argument("--index", type=int, default=0, help="Image index within the selected split.")
    parser.add_argument(
        "--layer-name",
        type=str,
        default=DEFAULT_LAYER_NAME,
        help="Depthwise conv module name inside the detector.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("build/pl_layer_case_depthwise"),
        help="Directory for exported tensors and metadata.",
    )
    parser.add_argument("--device", type=str, default="auto", help="auto, cpu, or cuda.")
    return parser.parse_args()


def pick_device(torch: Any, requested: str) -> Any:
    if requested != "auto":
        return torch.device(requested)
    if torch.cuda.is_available():
        return torch.device("cuda")
    return torch.device("cpu")


def load_model(args: argparse.Namespace, device: Any) -> tuple[Any, dict[str, Any], list[str]]:
    torch = require_torch()
    checkpoint = torch.load(args.checkpoint, map_location="cpu")
    cfg = checkpoint["config"]
    class_names = list(checkpoint["class_names"])

    model = build_ssdlite_mobilenetv2_ir(
        num_classes_with_background=int(cfg["num_classes_with_background"]),
        input_width=int(cfg["input_width"]),
        input_height=int(cfg["input_height"]),
        width_mult=float(cfg["width_mult"]),
        input_contract=str(cfg.get("input_contract", LEGACY_BRIDGE_INPUT_CONTRACT)),
        pretrained_backbone=False,
        score_thresh=float(cfg["score_thresh"]),
        nms_thresh=float(cfg["nms_thresh"]),
    )
    model.load_state_dict(checkpoint["model_state_dict"])
    model.to(device)
    model.eval()
    return model, cfg, class_names


def get_module_by_name(model: Any, name: str) -> Any:
    modules = dict(model.named_modules())
    if name not in modules:
        raise KeyError(f"Module not found: {name}")
    return modules[name]


def infer_sibling_name(conv_name: str, leaf_index: str) -> str:
    parts = conv_name.split(".")
    parts[-1] = leaf_index
    return ".".join(parts)


def fuse_conv_bn(conv: Any, bn: Any) -> tuple[np.ndarray, np.ndarray]:
    torch = require_torch()
    weight = conv.weight.detach().cpu().float()
    if conv.bias is None:
        bias = torch.zeros((conv.out_channels,), dtype=torch.float32)
    else:
        bias = conv.bias.detach().cpu().float()

    gamma = bn.weight.detach().cpu().float()
    beta = bn.bias.detach().cpu().float()
    mean = bn.running_mean.detach().cpu().float()
    var = bn.running_var.detach().cpu().float()
    eps = float(bn.eps)
    scale = gamma / torch.sqrt(var + eps)

    fused_weight = weight * scale.view(-1, 1, 1, 1)
    fused_bias = beta + (bias - mean) * scale
    return fused_weight.numpy(), fused_bias.numpy()


def write_array_pair(path_prefix: Path, array: np.ndarray) -> dict[str, Any]:
    array = np.ascontiguousarray(array.astype(np.float32))
    npy_path = path_prefix.with_suffix(".npy")
    bin_path = path_prefix.with_suffix(".bin")
    np.save(npy_path, array)
    array.tofile(bin_path)
    return {
        "npy": npy_path.name,
        "bin": bin_path.name,
        "shape": list(array.shape),
        "dtype": "float32",
    }


def main() -> int:
    args = parse_args()
    torch = require_torch()
    device = pick_device(torch, args.device)
    model, cfg, class_names = load_model(args, device)

    dataset = FlirCocoDetectionDataset(
        manifest_path=args.manifest,
        split=args.split,
        training=False,
    )
    if not 0 <= args.index < len(dataset):
        raise IndexError(f"Index {args.index} out of range for split '{args.split}' with {len(dataset)} images.")

    conv_module = get_module_by_name(model, args.layer_name)
    if not isinstance(conv_module, torch.nn.Conv2d):
        raise TypeError(f"Target module is not Conv2d: {args.layer_name}")
    if conv_module.kernel_size != (3, 3) or conv_module.groups != conv_module.in_channels:
        raise ValueError("Target module is not a depthwise 3x3 convolution.")

    bn_name = infer_sibling_name(args.layer_name, "1")
    relu_name = infer_sibling_name(args.layer_name, "2")
    bn_module = get_module_by_name(model, bn_name)
    relu_module = get_module_by_name(model, relu_name)

    image_tensor, target = dataset[args.index]
    image_info = dataset.images[args.index]
    image_id = int(image_info["id"])

    captured: dict[str, Any] = {}

    def capture_tensor(name: str):
        def hook(_module: Any, inputs: tuple[Any, ...], output: Any) -> None:
            captured[name] = {
                "input": inputs[0].detach().cpu().float().numpy(),
                "output": output.detach().cpu().float().numpy(),
            }

        return hook

    handles = [
        conv_module.register_forward_hook(capture_tensor("conv")),
        bn_module.register_forward_hook(capture_tensor("bn")),
        relu_module.register_forward_hook(capture_tensor("relu")),
    ]

    try:
        with torch.no_grad():
            batched_image = image_tensor.to(device)
            transformed_images, _ = model.transform([batched_image], None)
            detector_input = transformed_images.tensors[0].detach().cpu().float().numpy()
            _ = model.backbone(transformed_images.tensors)
    finally:
        for handle in handles:
            handle.remove()

    fused_weight, fused_bias = fuse_conv_bn(conv_module, bn_module)

    conv_input = np.ascontiguousarray(captured["conv"]["input"])
    bn_output = np.ascontiguousarray(captured["bn"]["output"])
    relu_output = np.ascontiguousarray(captured["relu"]["output"])
    detector_input = np.ascontiguousarray(detector_input)

    with torch.no_grad():
        fused_output = torch.nn.functional.conv2d(
            torch.from_numpy(conv_input),
            torch.from_numpy(fused_weight),
            bias=torch.from_numpy(fused_bias),
            stride=conv_module.stride,
            padding=conv_module.padding,
            dilation=conv_module.dilation,
            groups=conv_module.groups,
        ).numpy()

    fuse_max_abs_err = float(np.max(np.abs(fused_output - bn_output)))
    fuse_mean_abs_err = float(np.mean(np.abs(fused_output - bn_output)))

    args.output_dir.mkdir(parents=True, exist_ok=True)
    artifact_map = {
        "detector_input": write_array_pair(args.output_dir / "detector_input", detector_input),
        "layer_input": write_array_pair(args.output_dir / "layer_input", conv_input),
        "weight_fused": write_array_pair(args.output_dir / "weight_fused", fused_weight),
        "bias_fused": write_array_pair(args.output_dir / "bias_fused", fused_bias),
        "golden_bn_out": write_array_pair(args.output_dir / "golden_bn_out", bn_output),
        "golden_relu6_out": write_array_pair(args.output_dir / "golden_relu6_out", relu_output),
    }

    manifest = {
        "case_version": 1,
        "checkpoint": str(args.checkpoint),
        "manifest_path": str(args.manifest),
        "split": args.split,
        "image_index": args.index,
        "image_id": image_id,
        "image_file": str(image_info["file_name"]),
        "class_names": class_names,
        "detector_config": cfg,
        "target_layer": {
            "name": args.layer_name,
            "type": "depthwise_conv3x3",
            "recommended_reason": (
                "Selected as the default PL validation layer because it is a stride-1 MobileNetV2 depthwise 3x3 "
                "operator with medium spatial size and moderate channel count."
            ),
            "in_channels": int(conv_module.in_channels),
            "out_channels": int(conv_module.out_channels),
            "kernel_size": list(conv_module.kernel_size),
            "stride": list(conv_module.stride),
            "padding": list(conv_module.padding),
            "groups": int(conv_module.groups),
            "bn_name": bn_name,
            "relu_name": relu_name,
        },
        "tensor_contract": {
            "layout": "NCHW",
            "dtype": "float32",
            "notes": [
                "weight_fused and bias_fused already include BatchNorm folding.",
                "golden_bn_out matches fused depthwise conv output before ReLU6.",
                "golden_relu6_out matches the inference output after ReLU6.",
            ],
        },
        "fuse_check": {
            "max_abs_error": fuse_max_abs_err,
            "mean_abs_error": fuse_mean_abs_err,
        },
        "artifacts": artifact_map,
        "sample_target": {
            "boxes": target["boxes"].cpu().numpy().astype(np.float32).tolist(),
            "labels": target["labels"].cpu().numpy().astype(np.int64).tolist(),
        },
    }

    manifest_path = args.output_dir / "layer_manifest.json"
    with manifest_path.open("w", encoding="utf-8") as fp:
        json.dump(manifest, fp, indent=2, ensure_ascii=False)
        fp.write("\n")

    summary_lines = [
        f"layer={args.layer_name}",
        f"image_id={image_id}",
        f"image_file={image_info['file_name']}",
        f"input_shape={list(conv_input.shape)}",
        f"weight_shape={list(fused_weight.shape)}",
        f"bn_output_shape={list(bn_output.shape)}",
        f"relu6_output_shape={list(relu_output.shape)}",
        f"fuse_max_abs_error={fuse_max_abs_err:.8f}",
        f"fuse_mean_abs_error={fuse_mean_abs_err:.8f}",
        "status=pl_depthwise_case_ready",
    ]
    (args.output_dir / "layer_summary.txt").write_text("\n".join(summary_lines) + "\n", encoding="utf-8")

    print(f"Exported PL layer case: {args.output_dir}")
    print(f"Layer: {args.layer_name}")
    print(f"Image: id={image_id} file={image_info['file_name']}")
    print(
        "Shapes: "
        f"layer_input={tuple(conv_input.shape)} weight_fused={tuple(fused_weight.shape)} "
        f"golden_bn_out={tuple(bn_output.shape)} golden_relu6_out={tuple(relu_output.shape)}"
    )
    print(f"BN fusion check: max_abs_error={fuse_max_abs_err:.8f} mean_abs_error={fuse_mean_abs_err:.8f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
