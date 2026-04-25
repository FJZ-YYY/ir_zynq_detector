#!/usr/bin/env python3
"""Export a transform-free SSDLite raw-head ONNX for runtime integration."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from pc.models.flir_ir_dataset import FlirCocoDetectionDataset
from pc.models.ssdlite_mobilenetv2_ir import (
    LEGACY_BRIDGE_INPUT_CONTRACT,
    build_ssdlite_mobilenetv2_ir,
    build_transform_free_raw_head_export_wrapper,
    extract_raw_ssd_head_outputs,
    is_future_fixed_input_contract,
    normalize_input_contract_name,
)


def require_torch() -> Any:
    try:
        import torch
    except ImportError as exc:  # pragma: no cover - runtime dependency
        raise RuntimeError("PyTorch is required for runtime ONNX export.") from exc
    return torch


def configure_console_encoding() -> None:
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if stream is not None and hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except OSError:
                pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export a transform-free SSDLite raw-head ONNX for C/C++ runtime integration."
    )
    parser.add_argument("--checkpoint", type=Path, required=True, help="Path to best.pt or last.pt checkpoint.")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("build/model/irdet_ssdlite_ir_runtime_fixed_v2.onnx"),
        help="ONNX output path.",
    )
    parser.add_argument(
        "--metadata-output",
        type=Path,
        default=None,
        help="Optional JSON path for export metadata. Defaults to <output>.json.",
    )
    parser.add_argument("--opset", type=int, default=18, help="ONNX opset version.")
    parser.add_argument(
        "--legacy-exporter",
        action="store_true",
        help="Use the legacy torch.onnx tracer instead of the default torch.export-based exporter.",
    )
    parser.add_argument(
        "--single-file",
        action="store_true",
        help="Store all tensor data inside the ONNX file instead of writing an external .onnx.data file.",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=None,
        help="Optional dataset manifest for real-image verification.",
    )
    parser.add_argument("--split", choices=("train", "val"), default="val")
    parser.add_argument("--verify-images", type=int, default=0, help="Number of dataset images to verify.")
    parser.add_argument("--tolerance", type=float, default=1.0e-5, help="Maximum allowed tensor diff.")
    parser.add_argument(
        "--exclude-anchor-output",
        action="store_true",
        help="Do not expose anchors_xyxy as an ONNX graph output. Useful for ncnn conversion when anchors are loaded externally.",
    )
    return parser.parse_args()


def load_model(torch: Any, checkpoint_path: Path) -> tuple[Any, list[str], dict[str, Any]]:
    checkpoint = torch.load(checkpoint_path, map_location="cpu")
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
    model.eval()
    return model, class_names, cfg


def max_abs_diff(torch: Any, lhs: Any, rhs: Any) -> float:
    if lhs.numel() == 0 and rhs.numel() == 0:
        return 0.0
    return float((lhs.detach().cpu() - rhs.detach().cpu()).abs().max().item())


def verify_one_tensor(
    torch: Any,
    model: Any,
    wrapper: Any,
    image_0_1: Any,
) -> dict[str, Any]:
    with torch.no_grad():
        transformed, _ = model.transform([image_0_1], None)
        ref_bbox, ref_cls, ref_anchors = extract_raw_ssd_head_outputs(model, image_0_1.unsqueeze(0))
        got_bbox, got_cls, got_anchors = wrapper(transformed.tensors)

    return {
        "input_shape": list(image_0_1.shape),
        "runtime_shape": list(transformed.tensors.shape),
        "transformed_image_size_h_w": list(transformed.image_sizes[0]),
        "bbox_max_abs_diff": max_abs_diff(torch, ref_bbox, got_bbox),
        "cls_max_abs_diff": max_abs_diff(torch, ref_cls, got_cls),
        "anchors_max_abs_diff": max_abs_diff(torch, ref_anchors, got_anchors),
    }


def run_verification(
    torch: Any,
    model: Any,
    wrapper: Any,
    cfg: dict[str, Any],
    manifest: Path | None,
    split: str,
    verify_images: int,
) -> list[dict[str, Any]]:
    records = []
    dummy = torch.rand((1, int(cfg["input_height"]), int(cfg["input_width"])), dtype=torch.float32)
    records.append({"name": "random_dummy", **verify_one_tensor(torch, model, wrapper, dummy)})

    if manifest is None or verify_images <= 0:
        return records

    dataset = FlirCocoDetectionDataset(
        manifest_path=manifest,
        split=split,
        training=False,
        max_samples=verify_images,
    )
    for idx in range(len(dataset)):
        image, target = dataset[idx]
        records.append(
            {
                "name": f"{split}_{idx}",
                "image_id": int(target["image_id"][0].item()),
                **verify_one_tensor(torch, model, wrapper, image),
            }
        )
    return records


def verification_passed(records: list[dict[str, Any]], tolerance: float) -> bool:
    for record in records:
        if float(record["bbox_max_abs_diff"]) > tolerance:
            return False
        if float(record["cls_max_abs_diff"]) > tolerance:
            return False
        if float(record["anchors_max_abs_diff"]) > tolerance:
            return False
    return True


def write_metadata(
    path: Path,
    checkpoint_path: Path,
    cfg: dict[str, Any],
    class_names: list[str],
    runtime_shape: list[int],
    transformed_image_size_h_w: list[int],
    bbox_regression: Any,
    cls_logits: Any,
    anchors: Any,
    verification_records: list[dict[str, Any]],
    tolerance: float,
) -> None:
    runtime_height = int(runtime_shape[2])
    runtime_width = int(runtime_shape[3])
    checkpoint_height = int(cfg["input_height"])
    checkpoint_width = int(cfg["input_width"])
    checkpoint_input_contract = normalize_input_contract_name(
        cfg.get("input_contract", LEGACY_BRIDGE_INPUT_CONTRACT)
    )
    runtime_matches_fixed_contract = runtime_shape == [1, 1, checkpoint_height, checkpoint_width]
    is_future_fixed = bool(
        is_future_fixed_input_contract(checkpoint_input_contract) and runtime_matches_fixed_contract
    )
    metadata = {
        "export_format": "ssdlite_transform_free_raw_head_v2",
        "checkpoint": str(checkpoint_path),
        "checkpoint_input_contract": checkpoint_input_contract,
        "intent": "Runtime graph consumes an already-resized and already-normalized tensor, bypassing torchvision SSD transform.",
        "runtime_input_tensor": {
            "name": "input_0",
            "shape": runtime_shape,
            "dtype": "float32",
            "layout": "NCHW",
            "pixel_meaning": "already_resized_normalized_gray",
            "normalization": "(gray8 / 255.0 - 0.5) / 0.5",
            "width": runtime_width,
            "height": runtime_height,
        },
        "checkpoint_training_input_hint": {
            "shape": [1, 1, checkpoint_height, checkpoint_width],
            "width": checkpoint_width,
            "height": checkpoint_height,
            "pixel_meaning": "raw_gray_float_0_1_before_torchvision_transform",
        },
        "torchvision_transform_reference": {
            "internal_tensor_shape": runtime_shape,
            "internal_image_size_h_w": transformed_image_size_h_w,
            "removed_from_onnx": True,
        },
        "contract_status": {
            "is_current_checkpoint_compatible": True,
            "is_future_fixed_contract": is_future_fixed,
            "warning": (
                ""
                if is_future_fixed
                else "This export matches the current checkpoint runtime tensor space, but it is not yet the fixed 1x1x128x160 deployment contract."
            ),
        },
        "output_tensors": [
            {
                "name": "bbox_regression",
                "shape": list(bbox_regression.shape),
                "dtype": "float32",
                "meaning": "SSD box deltas relative to anchors",
            },
            {
                "name": "cls_logits",
                "shape": list(cls_logits.shape),
                "dtype": "float32",
                "meaning": "Raw class logits including background at index 0",
            },
            {
                "name": "anchors_xyxy",
                "shape": list(anchors.shape),
                "dtype": "float32",
                "meaning": "Static anchor boxes in runtime input pixel coordinates",
                "bbox_format": "xyxy",
            },
        ],
        "postprocess": {
            "score_threshold": float(cfg["score_thresh"]),
            "nms_iou_threshold": float(cfg["nms_thresh"]),
            "box_coder_weights": [10.0, 10.0, 5.0, 5.0],
        },
        "classes": {
            "background_index": 0,
            "foreground_names": class_names,
        },
        "verification": {
            "tolerance": tolerance,
            "passed": verification_passed(verification_records, tolerance),
            "records": verification_records,
        },
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fp:
        json.dump(metadata, fp, indent=2, ensure_ascii=False)
        fp.write("\n")


def main() -> int:
    configure_console_encoding()
    args = parse_args()
    torch = require_torch()
    model, class_names, cfg = load_model(torch, args.checkpoint)

    raw_dummy = torch.rand((1, 1, int(cfg["input_height"]), int(cfg["input_width"])), dtype=torch.float32)
    with torch.no_grad():
        transformed, _ = model.transform([raw_dummy[0]], None)
    runtime_shape = list(transformed.tensors.shape)
    runtime_height = int(runtime_shape[2])
    runtime_width = int(runtime_shape[3])

    wrapper = build_transform_free_raw_head_export_wrapper(
        detector=model,
        input_height=runtime_height,
        input_width=runtime_width,
    ).eval()
    verification_records = run_verification(
        torch=torch,
        model=model,
        wrapper=wrapper,
        cfg=cfg,
        manifest=args.manifest,
        split=args.split,
        verify_images=int(args.verify_images),
    )
    if not verification_passed(verification_records, float(args.tolerance)):
        for record in verification_records:
            print(
                "VERIFY_FAIL "
                f"name={record['name']} "
                f"bbox={record['bbox_max_abs_diff']:.8g} "
                f"cls={record['cls_max_abs_diff']:.8g} "
                f"anchors={record['anchors_max_abs_diff']:.8g}"
            )
        return 1

    runtime_dummy = torch.randn(tuple(runtime_shape), dtype=torch.float32)
    with torch.no_grad():
        bbox_regression, cls_logits, anchors = wrapper(runtime_dummy)

    export_wrapper = wrapper
    output_names = ["bbox_regression", "cls_logits", "anchors_xyxy"]
    if args.exclude_anchor_output:
        class TwoOutputWrapper(torch.nn.Module):
            def __init__(self, inner: Any) -> None:
                super().__init__()
                self.inner = inner

            def forward(self, x: Any) -> tuple[Any, Any]:
                bbox, cls, _anchors = self.inner(x)
                return bbox, cls

        export_wrapper = TwoOutputWrapper(wrapper).eval()
        output_names = ["bbox_regression", "cls_logits"]

    metadata_output = args.metadata_output
    if metadata_output is None:
        metadata_output = args.output.with_suffix(".json")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    torch.onnx.export(
        export_wrapper,
        runtime_dummy,
        args.output,
        opset_version=int(args.opset),
        input_names=["input_0"],
        output_names=output_names,
        dynamo=not bool(args.legacy_exporter),
        external_data=not bool(args.single_file),
    )
    write_metadata(
        path=metadata_output,
        checkpoint_path=args.checkpoint,
        cfg=cfg,
        class_names=class_names,
        runtime_shape=runtime_shape,
        transformed_image_size_h_w=list(transformed.image_sizes[0]),
        bbox_regression=bbox_regression,
        cls_logits=cls_logits,
        anchors=anchors,
        verification_records=verification_records,
        tolerance=float(args.tolerance),
    )

    print(f"Exported runtime ONNX: {args.output}")
    print(f"Export metadata: {metadata_output}")
    print(f"Runtime input tensor: 1x1x{runtime_height}x{runtime_width}")
    print(
        f"Checkpoint training hint: 1x1x{cfg['input_height']}x{cfg['input_width']} "
        "(pre-transform)"
    )
    print(
        "Outputs: "
        f"bbox_regression={tuple(bbox_regression.shape)} "
        f"cls_logits={tuple(cls_logits.shape)} "
        f"anchors_xyxy={tuple(anchors.shape)}"
    )
    print(f"Verification records={len(verification_records)} tolerance={float(args.tolerance):.1e} PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
