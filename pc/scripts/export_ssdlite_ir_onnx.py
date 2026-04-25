#!/usr/bin/env python3
"""Export the trained SSDLite-MobileNetV2 IR detector to ONNX."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from pc.models.ssdlite_mobilenetv2_ir import (
    Batch1RawHeadExportWrapper,
    LEGACY_BRIDGE_INPUT_CONTRACT,
    build_ssdlite_mobilenetv2_ir,
    is_future_fixed_input_contract,
    normalize_input_contract_name,
)


def require_torch() -> Any:
    try:
        import torch
    except ImportError as exc:  # pragma: no cover - runtime dependency
        raise RuntimeError("PyTorch is required for ONNX export.") from exc
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
        description="Export SSDLite-MobileNetV2 IR checkpoint to ONNX raw-head format."
    )
    parser.add_argument("--checkpoint", type=Path, required=True, help="Path to best.pt or last.pt checkpoint.")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("build/model/irdet_ssdlite_ir_fixed_v2.onnx"),
        help="ONNX output path.",
    )
    parser.add_argument("--opset", type=int, default=18, help="ONNX opset version.")
    parser.add_argument(
        "--metadata-output",
        type=Path,
        default=None,
        help="Optional JSON path for export metadata. Defaults to <output>.json.",
    )
    return parser.parse_args()


def write_metadata(
    path: Path,
    cfg: dict[str, Any],
    class_names: list[str],
    bbox_regression: Any,
    cls_logits: Any,
    anchors: Any,
    transformed_shape: list[int],
    transformed_image_size: list[int],
) -> None:
    input_contract = normalize_input_contract_name(cfg.get("input_contract", LEGACY_BRIDGE_INPUT_CONTRACT))
    input_shape = [1, 1, int(cfg["input_height"]), int(cfg["input_width"])]
    runtime_matches_fixed = transformed_shape == input_shape
    metadata = {
        "export_format": "ssdlite_raw_head_v1",
        "checkpoint_input_contract": input_contract,
        "input_tensor": {
            "name": "input_0",
            "shape": input_shape,
            "dtype": "float32",
            "layout": "NCHW",
            "pixel_meaning": "normalized_gray",
            "value_range_hint": [0.0, 1.0],
        },
        "torchvision_transform": {
            "internal_tensor_shape": transformed_shape,
            "internal_image_size_h_w": transformed_image_size,
            "note": "Current checkpoint keeps the torchvision SSD transform inside the exported graph.",
        },
        "contract_status": {
            "is_current_checkpoint_compatible": True,
            "is_future_fixed_contract": bool(is_future_fixed_input_contract(input_contract) and runtime_matches_fixed),
            "warning": (
                ""
                if bool(is_future_fixed_input_contract(input_contract) and runtime_matches_fixed)
                else "This export still depends on torchvision SSD transform behavior. Prefer the transform-free runtime export for deployment."
            ),
        },
        "output_tensors": [
            {
                "name": "bbox_regression",
                "shape": list(bbox_regression.shape),
                "dtype": "float32",
                "meaning": "SSD box deltas relative to anchors",
                "encoding": {
                    "box_coder_weights": [10.0, 10.0, 5.0, 5.0],
                    "formula": "decode rel_codes against anchors in xyxy pixels",
                },
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
                "meaning": "Anchor boxes in resized input pixel coordinates",
                "bbox_format": "xyxy",
            },
        ],
        "classes": {
            "background_index": 0,
            "foreground_names": class_names,
        },
        "notes": [
            "This ONNX export intentionally stops before decode/NMS.",
            "Board-side runtime should decode bbox_regression with anchors_xyxy, then apply score filtering and NMS.",
        ],
    }

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fp:
        json.dump(metadata, fp, indent=2, ensure_ascii=False)
        fp.write("\n")


def main() -> int:
    configure_console_encoding()
    args = parse_args()
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
    model.eval()

    wrapper = Batch1RawHeadExportWrapper(model).eval()
    dummy = torch.randn(1, 1, int(cfg["input_height"]), int(cfg["input_width"]), dtype=torch.float32)
    with torch.no_grad():
        transformed, _ = model.transform([dummy[0]], None)
        bbox_regression, cls_logits, anchors = wrapper(dummy)

    metadata_output = args.metadata_output
    if metadata_output is None:
        metadata_output = args.output.with_suffix(".json")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    torch.onnx.export(
        wrapper,
        dummy,
        args.output,
        opset_version=args.opset,
        input_names=["input_0"],
        output_names=["bbox_regression", "cls_logits", "anchors_xyxy"],
    )
    write_metadata(
        path=metadata_output,
        cfg=cfg,
        class_names=class_names,
        bbox_regression=bbox_regression,
        cls_logits=cls_logits,
        anchors=anchors,
        transformed_shape=list(transformed.tensors.shape),
        transformed_image_size=list(transformed.image_sizes[0]),
    )

    print(f"Exported ONNX: {args.output}")
    print(f"Export metadata: {metadata_output}")
    print(f"Classes: {', '.join(class_names)}")
    print(f"Input tensor: 1x1x{cfg['input_height']}x{cfg['input_width']}")
    print(f"Internal transform tensor: {tuple(transformed.tensors.shape)} image_size={tuple(transformed.image_sizes[0])}")
    print(
        "Outputs: "
        f"bbox_regression={tuple(bbox_regression.shape)} "
        f"cls_logits={tuple(cls_logits.shape)} "
        f"anchors_xyxy={tuple(anchors.shape)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
