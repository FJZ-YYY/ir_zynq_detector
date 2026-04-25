#!/usr/bin/env python3
"""Verify the SSD raw-head postprocess contract against torchvision output."""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from pc.models.flir_ir_dataset import FlirCocoDetectionDataset
from pc.models.ssdlite_mobilenetv2_ir import LEGACY_BRIDGE_INPUT_CONTRACT, build_ssdlite_mobilenetv2_ir


def require_torch_stack() -> tuple[Any, Any]:
    try:
        import torch
        from torchvision.ops import batched_nms
    except ImportError as exc:  # pragma: no cover - runtime dependency
        raise RuntimeError("Torch and torchvision are required for raw-head verification.") from exc
    return torch, batched_nms


def configure_console_encoding() -> None:
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if stream is not None and hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except OSError:
                pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify SSD raw-head decode/NMS against model output.")
    parser.add_argument("--checkpoint", type=Path, default=Path("build/train_ssdlite_ir_formal/best.pt"))
    parser.add_argument("--manifest", type=Path, default=Path("build/flir_thermal_3cls/dataset_manifest.json"))
    parser.add_argument("--split", choices=("train", "val"), default="val")
    parser.add_argument("--output-dir", type=Path, default=Path("build/verify_ssd_raw_postprocess"))
    parser.add_argument("--device", type=str, default="auto")
    parser.add_argument("--max-images", type=int, default=16)
    parser.add_argument("--score-thresh", type=float, default=None)
    parser.add_argument("--nms-thresh", type=float, default=None)
    parser.add_argument("--detections-per-img", type=int, default=50)
    parser.add_argument("--topk-candidates", type=int, default=100)
    parser.add_argument("--tolerance", type=float, default=1.0e-4)
    return parser.parse_args()


def pick_device(torch: Any, requested: str) -> Any:
    if requested != "auto":
        return torch.device(requested)
    if torch.cuda.is_available():
        return torch.device("cuda")
    return torch.device("cpu")


def load_model(args: argparse.Namespace, device: Any) -> tuple[Any, list[str], dict[str, Any]]:
    torch, _ = require_torch_stack()
    checkpoint = torch.load(args.checkpoint, map_location="cpu")
    cfg = checkpoint["config"]
    class_names = list(checkpoint["class_names"])
    score_thresh = float(cfg["score_thresh"]) if args.score_thresh is None else float(args.score_thresh)
    nms_thresh = float(cfg["nms_thresh"]) if args.nms_thresh is None else float(args.nms_thresh)

    model = build_ssdlite_mobilenetv2_ir(
        num_classes_with_background=int(cfg["num_classes_with_background"]),
        input_width=int(cfg["input_width"]),
        input_height=int(cfg["input_height"]),
        width_mult=float(cfg["width_mult"]),
        input_contract=str(cfg.get("input_contract", LEGACY_BRIDGE_INPUT_CONTRACT)),
        pretrained_backbone=False,
        score_thresh=score_thresh,
        nms_thresh=nms_thresh,
        detections_per_img=int(args.detections_per_img),
    )
    model.load_state_dict(checkpoint["model_state_dict"])
    model.to(device)
    model.eval()
    return model, class_names, cfg


def decode_boxes(torch: Any, rel_codes: Any, anchors: Any) -> Any:
    weights = rel_codes.new_tensor([10.0, 10.0, 5.0, 5.0])
    widths = anchors[:, 2] - anchors[:, 0]
    heights = anchors[:, 3] - anchors[:, 1]
    ctr_x = anchors[:, 0] + 0.5 * widths
    ctr_y = anchors[:, 1] + 0.5 * heights

    dx = rel_codes[:, 0] / weights[0]
    dy = rel_codes[:, 1] / weights[1]
    dw = rel_codes[:, 2] / weights[2]
    dh = rel_codes[:, 3] / weights[3]
    bbox_xform_clip = math.log(1000.0 / 16.0)
    dw = torch.clamp(dw, max=bbox_xform_clip)
    dh = torch.clamp(dh, max=bbox_xform_clip)

    pred_ctr_x = dx * widths + ctr_x
    pred_ctr_y = dy * heights + ctr_y
    pred_w = torch.exp(dw) * widths
    pred_h = torch.exp(dh) * heights

    boxes = torch.stack(
        (
            pred_ctr_x - 0.5 * pred_w,
            pred_ctr_y - 0.5 * pred_h,
            pred_ctr_x + 0.5 * pred_w,
            pred_ctr_y + 0.5 * pred_h,
        ),
        dim=1,
    )
    return boxes


def raw_postprocess(
    torch: Any,
    batched_nms: Any,
    bbox_regression: Any,
    cls_logits: Any,
    anchors_xyxy: Any,
    input_height: int,
    input_width: int,
    orig_height: int,
    orig_width: int,
    score_thresh: float,
    nms_thresh: float,
    topk_candidates: int,
    detections_per_img: int,
) -> dict[str, Any]:
    boxes = decode_boxes(
        torch=torch,
        rel_codes=bbox_regression[0],
        anchors=anchors_xyxy,
    )
    boxes[:, 0::2] = boxes[:, 0::2].clamp(min=0.0, max=float(input_width))
    boxes[:, 1::2] = boxes[:, 1::2].clamp(min=0.0, max=float(input_height))
    scores = torch.nn.functional.softmax(cls_logits[0], dim=-1)
    image_boxes = []
    image_scores = []
    image_labels = []

    for label in range(1, scores.shape[-1]):
        class_scores = scores[:, label]
        keep = class_scores > score_thresh
        class_scores = class_scores[keep]
        class_boxes = boxes[keep]
        if class_scores.numel() == 0:
            continue
        num_topk = min(int(topk_candidates), int(class_scores.numel()))
        class_scores, indices = class_scores.topk(num_topk)
        class_boxes = class_boxes[indices]
        image_boxes.append(class_boxes)
        image_scores.append(class_scores)
        image_labels.append(torch.full_like(class_scores, fill_value=label, dtype=torch.int64))

    if not image_boxes:
        return {
            "boxes": boxes.new_zeros((0, 4)),
            "scores": boxes.new_zeros((0,)),
            "labels": torch.zeros((0,), dtype=torch.int64, device=boxes.device),
        }

    image_boxes_tensor = torch.cat(image_boxes, dim=0)
    image_scores_tensor = torch.cat(image_scores, dim=0)
    image_labels_tensor = torch.cat(image_labels, dim=0)
    keep_indices = batched_nms(image_boxes_tensor, image_scores_tensor, image_labels_tensor, nms_thresh)
    keep_indices = keep_indices[:detections_per_img]

    out_boxes = image_boxes_tensor[keep_indices].clone()
    out_boxes[:, 0::2] *= float(orig_width) / float(input_width)
    out_boxes[:, 1::2] *= float(orig_height) / float(input_height)
    out_boxes[:, 0::2] = out_boxes[:, 0::2].clamp(min=0.0, max=float(orig_width))
    out_boxes[:, 1::2] = out_boxes[:, 1::2].clamp(min=0.0, max=float(orig_height))
    return {
        "boxes": out_boxes,
        "scores": image_scores_tensor[keep_indices],
        "labels": image_labels_tensor[keep_indices],
    }


def run_raw_head(model: Any, image: Any) -> tuple[Any, Any, Any, tuple[int, int]]:
    images, _ = model.transform([image], None)
    features = model.backbone(images.tensors)
    feature_list = list(features.values()) if isinstance(features, dict) else [features]
    head_outputs = model.head(feature_list)
    anchors = model.anchor_generator(images, feature_list)
    return head_outputs["bbox_regression"], head_outputs["cls_logits"], anchors[0], images.image_sizes[0]


def compare_detection_outputs(torch: Any, expected: dict[str, Any], actual: dict[str, Any]) -> dict[str, Any]:
    expected_count = int(expected["scores"].shape[0])
    actual_count = int(actual["scores"].shape[0])
    compare_count = min(expected_count, actual_count)
    labels_match = True
    max_score_abs_diff = 0.0
    max_box_abs_diff = 0.0

    if compare_count > 0:
        labels_match = bool(torch.equal(expected["labels"][:compare_count], actual["labels"][:compare_count]))
        max_score_abs_diff = float((expected["scores"][:compare_count] - actual["scores"][:compare_count]).abs().max().item())
        max_box_abs_diff = float((expected["boxes"][:compare_count] - actual["boxes"][:compare_count]).abs().max().item())

    return {
        "expected_count": expected_count,
        "actual_count": actual_count,
        "compare_count": compare_count,
        "labels_match": labels_match,
        "max_score_abs_diff": max_score_abs_diff,
        "max_box_abs_diff": max_box_abs_diff,
    }


def main() -> int:
    configure_console_encoding()
    args = parse_args()
    torch, batched_nms = require_torch_stack()
    device = pick_device(torch, args.device)
    model, class_names, cfg = load_model(args, device)
    score_thresh = float(cfg["score_thresh"]) if args.score_thresh is None else float(args.score_thresh)
    nms_thresh = float(cfg["nms_thresh"]) if args.nms_thresh is None else float(args.nms_thresh)
    input_width = int(cfg["input_width"])
    input_height = int(cfg["input_height"])

    dataset = FlirCocoDetectionDataset(
        manifest_path=args.manifest,
        split=args.split,
        training=False,
        max_samples=args.max_images,
    )

    records = []
    max_box_abs_diff = 0.0
    max_score_abs_diff = 0.0
    mismatch_count = 0
    start_time = time.perf_counter()

    with torch.no_grad():
        for idx in range(len(dataset)):
            image, target = dataset[idx]
            image = image.to(device)
            model_output = model([image])[0]
            bbox_regression, cls_logits, anchors, transformed_size = run_raw_head(model, image)
            transformed_height, transformed_width = transformed_size
            raw_output = raw_postprocess(
                torch=torch,
                batched_nms=batched_nms,
                bbox_regression=bbox_regression,
                cls_logits=cls_logits,
                anchors_xyxy=anchors,
                input_height=int(transformed_height),
                input_width=int(transformed_width),
                orig_height=int(image.shape[-2]),
                orig_width=int(image.shape[-1]),
                score_thresh=score_thresh,
                nms_thresh=nms_thresh,
                topk_candidates=int(args.topk_candidates),
                detections_per_img=int(args.detections_per_img),
            )
            comparison = compare_detection_outputs(torch, model_output, raw_output)
            max_box_abs_diff = max(max_box_abs_diff, comparison["max_box_abs_diff"])
            max_score_abs_diff = max(max_score_abs_diff, comparison["max_score_abs_diff"])
            passed = (
                comparison["expected_count"] == comparison["actual_count"]
                and comparison["labels_match"]
                and comparison["max_box_abs_diff"] <= args.tolerance
                and comparison["max_score_abs_diff"] <= args.tolerance
            )
            if not passed:
                mismatch_count += 1
            records.append(
                {
                    "index": idx,
                    "image_id": int(target["image_id"][0].item()),
                    "passed": passed,
                    **comparison,
                }
            )

    elapsed_sec = time.perf_counter() - start_time
    report = {
        "format": "ir_ssd_raw_postprocess_verify_v1",
        "checkpoint": str(args.checkpoint),
        "manifest": str(args.manifest),
        "split": args.split,
        "classes": class_names,
        "device": str(device),
        "num_images": len(dataset),
        "score_thresh": score_thresh,
        "nms_thresh": nms_thresh,
        "detections_per_img": int(args.detections_per_img),
        "topk_candidates": int(args.topk_candidates),
        "tolerance": float(args.tolerance),
        "mismatch_count": mismatch_count,
        "max_box_abs_diff": max_box_abs_diff,
        "max_score_abs_diff": max_score_abs_diff,
        "elapsed_sec": elapsed_sec,
        "records": records,
    }

    args.output_dir.mkdir(parents=True, exist_ok=True)
    report_path = args.output_dir / "raw_postprocess_verify.json"
    with report_path.open("w", encoding="utf-8") as fp:
        json.dump(report, fp, indent=2, ensure_ascii=False)
        fp.write("\n")

    print(
        f"Raw postprocess verify images={len(dataset)} mismatches={mismatch_count} "
        f"max_box_abs_diff={max_box_abs_diff:.8f} max_score_abs_diff={max_score_abs_diff:.8f} "
        f"elapsed_sec={elapsed_sec:.2f}"
    )
    print(f"Artifacts: {report_path}")
    return 0 if mismatch_count == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
