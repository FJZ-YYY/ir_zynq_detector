#!/usr/bin/env python3
"""Evaluate the trained FLIR SSDLite-MobileNetV2 detector and save visualizations."""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
from PIL import ImageColor, ImageDraw, ImageFont


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from pc.models.flir_ir_dataset import FlirCocoDetectionDataset, detection_collate_fn
from pc.models.ssdlite_mobilenetv2_ir import LEGACY_BRIDGE_INPUT_CONTRACT, build_ssdlite_mobilenetv2_ir


def require_torch() -> tuple[Any, Any]:
    try:
        import torch
        from torch.utils.data import DataLoader
    except ImportError as exc:  # pragma: no cover - runtime dependency
        raise RuntimeError("PyTorch is required for evaluation.") from exc
    return torch, DataLoader


def pick_device(torch: Any, requested: str) -> Any:
    if requested != "auto":
        return torch.device(requested)
    if torch.cuda.is_available():
        return torch.device("cuda")
    return torch.device("cpu")


def configure_console_encoding() -> None:
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if stream is not None and hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except OSError:
                pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate a trained FLIR SSDLite-MobileNetV2 detector.")
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
    parser.add_argument("--split", choices=("train", "val"), default="val", help="Dataset split to evaluate.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("outputs/eval_ssdlite_ir"),
        help="Directory for metrics and visualizations.",
    )
    parser.add_argument("--device", type=str, default="auto", help="auto, cpu, or cuda.")
    parser.add_argument("--batch-size", type=int, default=8, help="Inference batch size.")
    parser.add_argument("--num-workers", type=int, default=0, help="DataLoader workers.")
    parser.add_argument("--pin-memory", action="store_true", help="Enable DataLoader pin_memory.")
    parser.add_argument(
        "--max-images",
        type=int,
        default=None,
        help="Optional cap on evaluated images for quick smoke checks.",
    )
    parser.add_argument(
        "--score-thresh",
        type=float,
        default=0.05,
        help="Detector score threshold used during evaluation inference.",
    )
    parser.add_argument(
        "--nms-thresh",
        type=float,
        default=None,
        help="Override NMS threshold. Defaults to checkpoint config.",
    )
    parser.add_argument(
        "--detections-per-img",
        type=int,
        default=100,
        help="Maximum detections per image during evaluation inference.",
    )
    parser.add_argument("--vis-count", type=int, default=12, help="Number of images to render with boxes.")
    parser.add_argument(
        "--vis-score-thresh",
        type=float,
        default=0.35,
        help="Minimum score shown in visualization images.",
    )
    parser.add_argument("--amp", action="store_true", help="Enable autocast on CUDA for faster evaluation.")
    parser.add_argument("--log-interval", type=int, default=50, help="Print progress every N batches. Use 0 to disable.")
    return parser.parse_args()


def load_checkpoint_model(args: argparse.Namespace, device: Any) -> tuple[Any, list[str], dict[str, Any]]:
    torch, _ = require_torch()
    checkpoint = torch.load(args.checkpoint, map_location="cpu")
    cfg = checkpoint["config"]
    class_names = list(checkpoint["class_names"])

    nms_thresh = float(cfg["nms_thresh"]) if args.nms_thresh is None else float(args.nms_thresh)
    model = build_ssdlite_mobilenetv2_ir(
        num_classes_with_background=int(cfg["num_classes_with_background"]),
        input_width=int(cfg["input_width"]),
        input_height=int(cfg["input_height"]),
        width_mult=float(cfg["width_mult"]),
        input_contract=str(cfg.get("input_contract", LEGACY_BRIDGE_INPUT_CONTRACT)),
        pretrained_backbone=False,
        score_thresh=float(args.score_thresh),
        nms_thresh=nms_thresh,
        detections_per_img=int(args.detections_per_img),
    )
    model.load_state_dict(checkpoint["model_state_dict"])
    model.to(device)
    model.eval()
    return model, class_names, cfg


def box_iou_numpy(box: np.ndarray, boxes: np.ndarray) -> np.ndarray:
    if boxes.size == 0:
        return np.zeros((0,), dtype=np.float32)
    x1 = np.maximum(box[0], boxes[:, 0])
    y1 = np.maximum(box[1], boxes[:, 1])
    x2 = np.minimum(box[2], boxes[:, 2])
    y2 = np.minimum(box[3], boxes[:, 3])
    inter_w = np.clip(x2 - x1, a_min=0.0, a_max=None)
    inter_h = np.clip(y2 - y1, a_min=0.0, a_max=None)
    inter = inter_w * inter_h
    area_a = np.clip(box[2] - box[0], a_min=0.0, a_max=None) * np.clip(box[3] - box[1], a_min=0.0, a_max=None)
    area_b = np.clip(boxes[:, 2] - boxes[:, 0], a_min=0.0, a_max=None) * np.clip(boxes[:, 3] - boxes[:, 1], a_min=0.0, a_max=None)
    union = np.maximum(area_a + area_b - inter, 1e-6)
    return inter / union


def compute_ap(recalls: np.ndarray, precisions: np.ndarray) -> float:
    mrec = np.concatenate(([0.0], recalls, [1.0]))
    mpre = np.concatenate(([0.0], precisions, [0.0]))
    for idx in range(mpre.size - 1, 0, -1):
        mpre[idx - 1] = max(mpre[idx - 1], mpre[idx])
    change_points = np.where(mrec[1:] != mrec[:-1])[0]
    return float(np.sum((mrec[change_points + 1] - mrec[change_points]) * mpre[change_points + 1]))


def evaluate_class_at_iou(
    gt_by_image: dict[int, np.ndarray],
    predictions: list[dict[str, Any]],
    iou_thresh: float,
) -> tuple[float, int, int]:
    total_gt = int(sum(boxes.shape[0] for boxes in gt_by_image.values()))
    if total_gt == 0:
        return float("nan"), 0, len(predictions)

    matched = {image_id: np.zeros(boxes.shape[0], dtype=bool) for image_id, boxes in gt_by_image.items()}
    sorted_predictions = sorted(predictions, key=lambda item: float(item["score"]), reverse=True)
    tp = np.zeros((len(sorted_predictions),), dtype=np.float32)
    fp = np.zeros((len(sorted_predictions),), dtype=np.float32)

    for idx, pred in enumerate(sorted_predictions):
        image_id = int(pred["image_id"])
        pred_box = np.asarray(pred["box"], dtype=np.float32)
        gt_boxes = gt_by_image.get(image_id)
        if gt_boxes is None or gt_boxes.size == 0:
            fp[idx] = 1.0
            continue

        ious = box_iou_numpy(pred_box, gt_boxes)
        max_index = int(np.argmax(ious))
        max_iou = float(ious[max_index])
        if max_iou >= iou_thresh and not matched[image_id][max_index]:
            tp[idx] = 1.0
            matched[image_id][max_index] = True
        else:
            fp[idx] = 1.0

    tp_cum = np.cumsum(tp)
    fp_cum = np.cumsum(fp)
    recalls = tp_cum / max(total_gt, 1)
    precisions = tp_cum / np.maximum(tp_cum + fp_cum, 1e-6)
    ap = compute_ap(recalls, precisions)
    return ap, total_gt, len(sorted_predictions)


def evaluate_map_metrics(
    gt_records: dict[int, dict[str, Any]],
    pred_records: dict[int, dict[str, Any]],
    class_names: list[str],
) -> dict[str, Any]:
    iou_thresholds = [round(0.5 + 0.05 * idx, 2) for idx in range(10)]
    per_class = []
    ap50_values = []
    ap5095_values = []

    for class_offset, class_name in enumerate(class_names, start=1):
        gt_by_image: dict[int, np.ndarray] = {}
        predictions = []

        for image_id, gt in gt_records.items():
            labels = gt["labels"]
            boxes = gt["boxes"]
            mask = labels == class_offset
            gt_by_image[image_id] = boxes[mask]

        for image_id, pred in pred_records.items():
            labels = pred["labels"]
            scores = pred["scores"]
            boxes = pred["boxes"]
            mask = labels == class_offset
            for box, score in zip(boxes[mask], scores[mask]):
                predictions.append(
                    {
                        "image_id": image_id,
                        "score": float(score),
                        "box": box.tolist(),
                    }
                )

        ap_by_threshold = {}
        gt_count = int(sum(boxes.shape[0] for boxes in gt_by_image.values()))
        pred_count = len(predictions)
        for iou in iou_thresholds:
            ap_value, _, _ = evaluate_class_at_iou(gt_by_image, predictions, iou)
            ap_by_threshold[f"{iou:.2f}"] = ap_value

        valid_ap = [value for value in ap_by_threshold.values() if not math.isnan(value)]
        ap50 = float(ap_by_threshold["0.50"]) if not math.isnan(ap_by_threshold["0.50"]) else float("nan")
        ap5095 = float(np.mean(valid_ap)) if valid_ap else float("nan")
        if not math.isnan(ap50):
            ap50_values.append(ap50)
        if not math.isnan(ap5095):
            ap5095_values.append(ap5095)

        per_class.append(
            {
                "class_id": class_offset,
                "class_name": class_name,
                "gt_count": gt_count,
                "prediction_count": pred_count,
                "ap50": ap50,
                "ap5095": ap5095,
                "ap_by_iou": ap_by_threshold,
            }
        )

    return {
        "mAP50": float(np.mean(ap50_values)) if ap50_values else float("nan"),
        "mAP50_95": float(np.mean(ap5095_values)) if ap5095_values else float("nan"),
        "iou_thresholds": iou_thresholds,
        "per_class": per_class,
    }


def render_visualizations(
    dataset: FlirCocoDetectionDataset,
    pred_records: dict[int, dict[str, Any]],
    output_dir: Path,
    class_names: list[str],
    vis_count: int,
    score_thresh: float,
) -> list[dict[str, Any]]:
    output_dir.mkdir(parents=True, exist_ok=True)
    font = ImageFont.load_default()
    pred_color = ImageColor.getrgb("#ff5a36")
    gt_color = ImageColor.getrgb("#36d17d")
    saved = []

    for image_info in dataset.images[:vis_count]:
        image_id = int(image_info["id"])
        image = dataset._load_image(str(image_info["file_name"])).convert("RGB")
        draw = ImageDraw.Draw(image)

        gt_annotations = dataset.annotations_by_image.get(image_id, [])
        for ann in gt_annotations:
            x, y, w, h = ann["bbox"]
            box = [float(x), float(y), float(x + w), float(y + h)]
            class_name = class_names[int(ann["category_id"]) - 1]
            draw.rectangle(box, outline=gt_color, width=2)
            draw.text((box[0] + 1, max(0.0, box[1] - 10)), f"GT:{class_name}", fill=gt_color, font=font)

        pred = pred_records.get(image_id)
        if pred is not None:
            for box, score, label in zip(pred["boxes"], pred["scores"], pred["labels"]):
                if float(score) < score_thresh:
                    continue
                class_name = class_names[int(label) - 1]
                box_list = [float(v) for v in box]
                draw.rectangle(box_list, outline=pred_color, width=2)
                draw.text(
                    (box_list[0] + 1, min(max(0.0, box_list[1] + 2), image.height - 12)),
                    f"{class_name}:{float(score):.2f}",
                    fill=pred_color,
                    font=font,
                )

        dst_path = output_dir / f"{image_id:06d}_{Path(str(image_info['file_name'])).stem}.png"
        image.save(dst_path)
        saved.append({"image_id": image_id, "path": str(dst_path), "file_name": str(image_info["file_name"])})

    return saved


def write_detection_records(
    path: Path,
    gt_records: dict[int, dict[str, Any]],
    pred_records: dict[int, dict[str, Any]],
    class_names: list[str],
) -> None:
    records = []
    for image_id in sorted(gt_records):
        gt = gt_records[image_id]
        pred = pred_records.get(
            image_id,
            {
                "boxes": np.zeros((0, 4), dtype=np.float32),
                "scores": np.zeros((0,), dtype=np.float32),
                "labels": np.zeros((0,), dtype=np.int64),
            },
        )
        records.append(
            {
                "image_id": image_id,
                "ground_truth": [
                    {
                        "class_id": int(label),
                        "class_name": class_names[int(label) - 1],
                        "box_xyxy": [float(v) for v in box],
                    }
                    for box, label in zip(gt["boxes"], gt["labels"])
                ],
                "predictions": [
                    {
                        "class_id": int(label),
                        "class_name": class_names[int(label) - 1],
                        "score": float(score),
                        "box_xyxy": [float(v) for v in box],
                    }
                    for box, score, label in zip(pred["boxes"], pred["scores"], pred["labels"])
                    if int(label) > 0
                ],
            }
        )

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fp:
        json.dump(
            {
                "format": "ir_ssdlite_eval_records_v1",
                "classes": class_names,
                "records": records,
            },
            fp,
            indent=2,
            ensure_ascii=False,
        )
        fp.write("\n")


def main() -> int:
    configure_console_encoding()
    args = parse_args()
    torch, DataLoader = require_torch()
    device = pick_device(torch, args.device)
    model, class_names, checkpoint_cfg = load_checkpoint_model(args, device)

    dataset = FlirCocoDetectionDataset(
        manifest_path=args.manifest,
        split=args.split,
        training=False,
        max_samples=args.max_images,
    )
    loader = DataLoader(
        dataset,
        batch_size=args.batch_size,
        shuffle=False,
        num_workers=args.num_workers,
        collate_fn=detection_collate_fn,
        pin_memory=args.pin_memory,
        persistent_workers=False,
    )

    gt_records: dict[int, dict[str, Any]] = {}
    pred_records: dict[int, dict[str, Any]] = {}
    vis_output_dir = args.output_dir / "vis"

    model.eval()
    autocast_enabled = bool(args.amp and device.type == "cuda")
    start_time = time.perf_counter()
    with torch.no_grad():
        for batch_index, (images, targets) in enumerate(loader, start=1):
            image_batch = [img.to(device) for img in images]
            with torch.autocast(device_type=device.type, dtype=torch.float16, enabled=autocast_enabled):
                outputs = model(image_batch)

            for target, output in zip(targets, outputs):
                image_id = int(target["image_id"][0].item())
                gt_records[image_id] = {
                    "boxes": target["boxes"].cpu().numpy().astype(np.float32),
                    "labels": target["labels"].cpu().numpy().astype(np.int64),
                }
                pred_records[image_id] = {
                    "boxes": output["boxes"].detach().cpu().numpy().astype(np.float32),
                    "scores": output["scores"].detach().cpu().numpy().astype(np.float32),
                    "labels": output["labels"].detach().cpu().numpy().astype(np.int64),
                }
            if args.log_interval > 0 and (batch_index % args.log_interval == 0 or batch_index == len(loader)):
                done_images = min(batch_index * args.batch_size, len(dataset))
                elapsed = time.perf_counter() - start_time
                print(f"[eval] batch={batch_index}/{len(loader)} images={done_images}/{len(dataset)} elapsed_sec={elapsed:.1f}")

    metrics = evaluate_map_metrics(gt_records=gt_records, pred_records=pred_records, class_names=class_names)
    vis_manifest = render_visualizations(
        dataset=dataset,
        pred_records=pred_records,
        output_dir=vis_output_dir,
        class_names=class_names,
        vis_count=min(args.vis_count, len(dataset)),
        score_thresh=args.vis_score_thresh,
    )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    report = {
        "checkpoint": str(args.checkpoint),
        "manifest": str(args.manifest),
        "split": args.split,
        "device": str(device),
        "num_images": len(dataset),
        "checkpoint_config": checkpoint_cfg,
        "eval_config": {
            "score_thresh": args.score_thresh,
            "nms_thresh": checkpoint_cfg["nms_thresh"] if args.nms_thresh is None else args.nms_thresh,
            "detections_per_img": args.detections_per_img,
            "batch_size": args.batch_size,
            "amp": autocast_enabled,
        },
        "metrics": metrics,
        "visualizations": vis_manifest,
    }

    json_path = args.output_dir / "metrics.json"
    records_path = args.output_dir / "detections.json"
    with json_path.open("w", encoding="utf-8") as fp:
        json.dump(report, fp, indent=2, ensure_ascii=False)
        fp.write("\n")
    write_detection_records(
        path=records_path,
        gt_records=gt_records,
        pred_records=pred_records,
        class_names=class_names,
    )

    lines = [
        f"checkpoint={args.checkpoint}",
        f"split={args.split}",
        f"num_images={len(dataset)}",
        f"mAP50={metrics['mAP50']:.4f}",
        f"mAP50_95={metrics['mAP50_95']:.4f}",
    ]
    for entry in metrics["per_class"]:
        lines.append(
            f"class={entry['class_name']} ap50={entry['ap50']:.4f} ap50_95={entry['ap5095']:.4f} "
            f"gt={entry['gt_count']} pred={entry['prediction_count']}"
        )

    summary_path = args.output_dir / "summary.txt"
    summary_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"Evaluation finished for {len(dataset)} images on {device}.")
    print(f"mAP50={metrics['mAP50']:.4f} mAP50_95={metrics['mAP50_95']:.4f}")
    for entry in metrics["per_class"]:
        print(
            f"{entry['class_name']}: ap50={entry['ap50']:.4f} ap50_95={entry['ap5095']:.4f} "
            f"gt={entry['gt_count']} pred={entry['prediction_count']}"
        )
    print(f"Artifacts: {json_path} {summary_path} {records_path} {vis_output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
