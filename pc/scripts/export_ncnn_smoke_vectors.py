#!/usr/bin/env python3
"""Export fixed input/output vectors for the ncnn C++ smoke test."""

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

from pc.scripts.smoke_runtime_onnx import (
    build_random_runtime_input,
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
    parser = argparse.ArgumentParser(description="Export ncnn smoke-test vectors from a runtime ONNX model.")
    parser.add_argument(
        "--onnx",
        type=Path,
        default=Path("build/model/irdet_ssdlite_ir_runtime_fixed_v2_tracer_op13_ncnn.onnx"),
        help="Runtime ONNX used as the numerical reference.",
    )
    parser.add_argument(
        "--metadata",
        type=Path,
        default=Path("build/model/irdet_ssdlite_ir_runtime_fixed_v2_tracer_op13_ncnn.json"),
        help="Runtime metadata JSON.",
    )
    parser.add_argument(
        "--checkpoint",
        type=Path,
        default=Path("build/train_ssdlite_ir_fixed_v2/best.pt"),
        help="Checkpoint used to build the real FLIR sample transform.",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("build/flir_thermal_3cls_fixed_v2_keepempty/dataset_manifest.json"),
        help="Filtered FLIR manifest. If omitted or missing, a deterministic random tensor is used.",
    )
    parser.add_argument("--split", choices=("train", "val"), default="val")
    parser.add_argument("--index", type=int, default=0)
    parser.add_argument("--provider", choices=("cpu", "cuda", "auto"), default="cpu")
    parser.add_argument("--score-thresh", type=float, default=None)
    parser.add_argument("--nms-thresh", type=float, default=None)
    parser.add_argument("--detections-per-img", type=int, default=4)
    parser.add_argument("--topk-candidates", type=int, default=100)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("build/ncnn_smoke"),
        help="Directory for input/reference binary files and JSON manifest.",
    )
    return parser.parse_args()


def write_float32(path: Path, array: np.ndarray) -> None:
    array.astype(np.float32).tofile(path)


def canonical_output_name(name: str) -> str:
    # The ncnn-friendly ONNX simplifier may rename the anchor constant output
    # from anchors_xyxy to anchors_xyxy.1. Keep generated metadata stable.
    if name.startswith("anchors_xyxy"):
        return "anchors_xyxy"
    return name


def main() -> int:
    args = parse_args()
    ort = require_onnxruntime()
    torch, batched_nms = require_torch_stack()
    metadata = load_json(args.metadata)

    model = None
    class_names = list(metadata.get("classes", {}).get("foreground_names", []))
    cfg: dict[str, Any] = {
        "score_thresh": metadata.get("postprocess", {}).get("score_threshold", 0.2),
        "nms_thresh": metadata.get("postprocess", {}).get("nms_iou_threshold", 0.45),
    }
    if args.checkpoint is not None and args.checkpoint.exists():
        model, class_names, cfg = load_model(torch, args.checkpoint)

    if model is not None and args.manifest is not None and args.manifest.exists():
        runtime_input, image_meta = build_runtime_input_from_dataset(
            torch=torch,
            model=model,
            manifest=args.manifest,
            split=args.split,
            index=int(args.index),
        )
        sample_kind = "flir"
    else:
        runtime_input, image_meta = build_random_runtime_input(metadata)
        sample_kind = "random"

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
    if "anchors_xyxy" not in outputs and model is not None:
        outputs["anchors_xyxy"] = get_runtime_anchors_from_model(torch, model, runtime_input)

    score_thresh = float(cfg["score_thresh"]) if args.score_thresh is None else float(args.score_thresh)
    nms_thresh = float(cfg["nms_thresh"]) if args.nms_thresh is None else float(args.nms_thresh)
    detections = []
    if {"bbox_regression", "cls_logits", "anchors_xyxy"}.issubset(outputs):
        detections = summarize_detections(
            torch=torch,
            batched_nms=batched_nms,
            outputs=outputs,
            cfg=cfg,
            image_meta=image_meta,
            class_names=class_names,
            score_thresh=score_thresh,
            nms_thresh=nms_thresh,
            topk_candidates=int(args.topk_candidates),
            detections_per_img=int(args.detections_per_img),
        )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    input_path = args.output_dir / "input_f32.bin"
    bbox_path = args.output_dir / "bbox_regression_f32.bin"
    cls_path = args.output_dir / "cls_logits_f32.bin"
    anchors_path = args.output_dir / "anchors_xyxy_f32.bin"
    write_float32(input_path, runtime_input)
    write_float32(bbox_path, outputs["bbox_regression"])
    write_float32(cls_path, outputs["cls_logits"])
    if "anchors_xyxy" in outputs:
        write_float32(anchors_path, outputs["anchors_xyxy"])

    manifest = {
        "format": "ir_ncnn_smoke_vectors_v1",
        "onnx": str(args.onnx),
        "metadata": str(args.metadata),
        "providers": providers,
        "sample_kind": sample_kind,
        "split": args.split,
        "index": int(args.index),
        "input_name": input_name,
        "output_names": output_names,
        "canonical_output_names": sorted(outputs.keys()),
        "input_shape": list(runtime_input.shape),
        "outputs": {
            "bbox_regression": {
                "shape": list(outputs["bbox_regression"].shape),
                "file": str(bbox_path),
            },
            "cls_logits": {
                "shape": list(outputs["cls_logits"].shape),
                "file": str(cls_path),
            },
        },
        "anchors": {
            "shape": list(outputs["anchors_xyxy"].shape) if "anchors_xyxy" in outputs else None,
            "file": str(anchors_path) if anchors_path.exists() else None,
        },
        "input_file": str(input_path),
        "image_meta": image_meta,
        "elapsed_ms": elapsed_ms,
        "postprocess": {
            "score_threshold": score_thresh,
            "nms_iou_threshold": nms_thresh,
            "topk_candidates": int(args.topk_candidates),
            "detections_per_img": int(args.detections_per_img),
        },
        "detections": detections,
    }
    manifest_path = args.output_dir / "ncnn_smoke_vectors.json"
    with manifest_path.open("w", encoding="utf-8") as fp:
        json.dump(manifest, fp, indent=2, ensure_ascii=False)
        fp.write("\n")

    print(f"Exported ncnn smoke vectors: {manifest_path}")
    print(f"Input {input_name} shape={tuple(runtime_input.shape)} file={input_path}")
    print(f"Reference bbox_regression shape={tuple(outputs['bbox_regression'].shape)} file={bbox_path}")
    print(f"Reference cls_logits shape={tuple(outputs['cls_logits'].shape)} file={cls_path}")
    if "anchors_xyxy" in outputs:
        print(f"Reference anchors_xyxy shape={tuple(outputs['anchors_xyxy'].shape)} file={anchors_path}")
    print(f"Detections count={len(detections)} elapsed_ms={elapsed_ms:.3f}")
    for idx, det in enumerate(detections):
        print(f"det{idx} class={det['class_name']} score={det['score']:.3f} bbox={det['bbox_xyxy']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
