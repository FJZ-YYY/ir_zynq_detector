#!/usr/bin/env python3
"""Export raw gray8 + tensor + anchors assets for the Linux ncnn demo app."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from pc.models.flir_ir_dataset import FlirCocoDetectionDataset
from pc.scripts.smoke_runtime_onnx import (
    build_runtime_input_from_dataset,
    get_runtime_anchors_from_model,
    load_json,
    load_model,
    pick_providers,
    require_onnxruntime,
    summarize_detections,
)
from pc.scripts.verify_ssd_raw_postprocess import require_torch_stack


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export Linux ncnn demo assets from a FLIR sample.")
    parser.add_argument(
        "--onnx",
        type=Path,
        default=Path("build/model/irdet_ssdlite_ir_runtime_fixed_v2_tracer_op13_ncnn.onnx"),
    )
    parser.add_argument(
        "--metadata",
        type=Path,
        default=Path("build/model/irdet_ssdlite_ir_runtime_fixed_v2_tracer_op13_ncnn.json"),
    )
    parser.add_argument(
        "--checkpoint",
        type=Path,
        default=Path("build/train_ssdlite_ir_fixed_v2/best.pt"),
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("build/flir_thermal_3cls_fixed_v2_keepempty/dataset_manifest.json"),
    )
    parser.add_argument("--split", choices=("train", "val"), default="val")
    parser.add_argument("--index", type=int, default=0)
    parser.add_argument("--provider", choices=("cpu", "cuda", "auto"), default="cpu")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("build/linux_ncnn_demo"),
    )
    return parser.parse_args()


def write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as fp:
        fp.write(data)


def write_float32(path: Path, array: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    array.astype(np.float32).tofile(path)


def canonical_output_name(name: str) -> str:
    if name.startswith("anchors_xyxy"):
        return "anchors_xyxy"
    return name


def main() -> int:
    args = parse_args()
    ort = require_onnxruntime()
    torch, batched_nms = require_torch_stack()
    metadata = load_json(args.metadata)

    model, class_names, cfg = load_model(torch, args.checkpoint)
    dataset = FlirCocoDetectionDataset(
        manifest_path=args.manifest,
        split=args.split,
        training=False,
    )
    image_tensor, target = dataset[int(args.index)]
    image_id = int(target["image_id"][0].item())
    image_info = dataset.images[int(args.index)]
    image = dataset._load_image(str(image_info["file_name"]))
    src_width, src_height = image.size
    raw_gray8 = image.tobytes()

    runtime_input, image_meta = build_runtime_input_from_dataset(
        torch=torch,
        model=model,
        manifest=args.manifest,
        split=args.split,
        index=int(args.index),
    )

    providers = pick_providers(ort, args.provider)
    session = ort.InferenceSession(str(args.onnx), providers=providers)
    input_name = session.get_inputs()[0].name
    output_names = [output.name for output in session.get_outputs()]
    start = time.perf_counter()
    output_values = session.run(output_names, {input_name: runtime_input})
    elapsed_ms = (time.perf_counter() - start) * 1000.0
    outputs = {
        canonical_output_name(name): value.astype(np.float32)
        for name, value in zip(output_names, output_values)
    }
    if "anchors_xyxy" not in outputs:
        outputs["anchors_xyxy"] = get_runtime_anchors_from_model(torch, model, runtime_input)

    detections = summarize_detections(
        torch=torch,
        batched_nms=batched_nms,
        outputs=outputs,
        cfg=cfg,
        image_meta=image_meta,
        class_names=class_names,
        score_thresh=float(metadata["postprocess"]["score_threshold"]),
        nms_thresh=float(metadata["postprocess"]["nms_iou_threshold"]),
        topk_candidates=100,
        detections_per_img=4,
    )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    gray8_path = args.output_dir / f"sample_gray8_{src_width}x{src_height}.bin"
    tensor_path = args.output_dir / "sample_runtime_input_f32.bin"
    anchors_path = args.output_dir / "anchors_xyxy_f32.bin"
    write_bytes(gray8_path, raw_gray8)
    write_float32(tensor_path, runtime_input)
    write_float32(anchors_path, outputs["anchors_xyxy"])

    manifest = {
        "format": "irdet_linux_ncnn_demo_assets_fixed_v2",
        "image_id": image_id,
        "sample_kind": "flir_gray8",
        "source_image": str(dataset.image_root / Path(str(image_info["file_name"]))),
        "gray8_file": str(gray8_path),
        "gray8_width": int(src_width),
        "gray8_height": int(src_height),
        "runtime_input_file": str(tensor_path),
        "runtime_input_shape": list(runtime_input.shape),
        "anchors_file": str(anchors_path),
        "anchors_shape": list(outputs["anchors_xyxy"].shape),
        "model_param": str(REPO_ROOT / "build/ncnn_runtime_fixed_v2_tracer_op13_ncnn/irdet_ssdlite_ir_runtime_fixed_v2.param"),
        "model_bin": str(REPO_ROOT / "build/ncnn_runtime_fixed_v2_tracer_op13_ncnn/irdet_ssdlite_ir_runtime_fixed_v2.bin"),
        "runtime_width": int(metadata["runtime_input_tensor"]["width"]),
        "runtime_height": int(metadata["runtime_input_tensor"]["height"]),
        "preprocess": {
            "input_scale": 1.0 / 255.0,
            "mean": 0.5,
            "stddev": 0.5,
        },
        "postprocess": metadata["postprocess"],
        "detections": detections,
        "providers": providers,
        "elapsed_ms": elapsed_ms,
    }
    manifest_path = args.output_dir / "linux_ncnn_demo_assets.json"
    with manifest_path.open("w", encoding="utf-8") as fp:
        json.dump(manifest, fp, indent=2, ensure_ascii=False)
        fp.write("\n")

    print(f"Exported Linux ncnn demo assets: {manifest_path}")
    print(f"gray8={gray8_path} size={src_width}x{src_height}")
    print(f"runtime_input={tensor_path} shape={tuple(runtime_input.shape)}")
    print(f"anchors={anchors_path} shape={tuple(outputs['anchors_xyxy'].shape)}")
    print(f"Detections count={len(detections)} elapsed_ms={elapsed_ms:.3f}")
    for idx, det in enumerate(detections):
        print(f"det{idx} class={det['class_name']} score={det['score']:.3f} bbox={det['bbox_xyxy']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
