#!/usr/bin/env python3
"""Smoke-test a transform-free SSDLite raw-head ONNX runtime export."""

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
from pc.models.ssdlite_mobilenetv2_ir import (
    LEGACY_BRIDGE_INPUT_CONTRACT,
    build_ssdlite_mobilenetv2_ir,
    build_transform_free_raw_head_export_wrapper,
)
from pc.scripts.verify_ssd_raw_postprocess import raw_postprocess, require_torch_stack


def require_onnxruntime() -> Any:
    try:
        import onnxruntime as ort
    except ImportError as exc:  # pragma: no cover - runtime dependency
        raise RuntimeError(
            "onnxruntime is required for this smoke test. Install it with: "
            "G:\\FPGA\\ir_zynq_detector\\.venv-train\\Scripts\\python.exe -m pip install onnxruntime"
        ) from exc
    return ort


def configure_console_encoding() -> None:
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if stream is not None and hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except OSError:
                pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run ONNX Runtime smoke test for SSDLite raw-head export.")
    parser.add_argument("--onnx", type=Path, required=True, help="Runtime ONNX model path.")
    parser.add_argument("--metadata", type=Path, required=True, help="Runtime metadata JSON path.")
    parser.add_argument("--checkpoint", type=Path, default=None, help="Optional checkpoint for PyTorch reference.")
    parser.add_argument("--manifest", type=Path, default=None, help="Optional FLIR manifest for a real-image sample.")
    parser.add_argument("--split", choices=("train", "val"), default="val")
    parser.add_argument("--index", type=int, default=0)
    parser.add_argument("--output-dir", type=Path, default=Path("build/runtime_onnx_smoke"))
    parser.add_argument("--provider", choices=("cpu", "cuda", "auto"), default="cpu")
    parser.add_argument("--tolerance", type=float, default=1.0e-3)
    parser.add_argument("--score-thresh", type=float, default=None)
    parser.add_argument("--nms-thresh", type=float, default=None)
    parser.add_argument("--detections-per-img", type=int, default=4)
    parser.add_argument("--topk-candidates", type=int, default=100)
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as fp:
        return json.load(fp)


def pick_providers(ort: Any, requested: str) -> list[str]:
    available = set(ort.get_available_providers())
    if requested == "cpu":
        return ["CPUExecutionProvider"]
    if requested == "cuda":
        if "CUDAExecutionProvider" not in available:
            raise RuntimeError(f"CUDAExecutionProvider is not available. Available providers: {sorted(available)}")
        return ["CUDAExecutionProvider", "CPUExecutionProvider"]
    if "CUDAExecutionProvider" in available:
        return ["CUDAExecutionProvider", "CPUExecutionProvider"]
    return ["CPUExecutionProvider"]


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
        detections_per_img=50,
    )
    model.load_state_dict(checkpoint["model_state_dict"])
    model.eval()
    return model, class_names, cfg


def build_runtime_input_from_dataset(
    torch: Any,
    model: Any,
    manifest: Path,
    split: str,
    index: int,
) -> tuple[np.ndarray, dict[str, int]]:
    dataset = FlirCocoDetectionDataset(
        manifest_path=manifest,
        split=split,
        training=False,
    )
    if index < 0 or index >= len(dataset):
        raise IndexError(f"Dataset index out of range: {index}, dataset size={len(dataset)}")

    image, target = dataset[index]
    with torch.no_grad():
        transformed, _ = model.transform([image], None)
    return (
        transformed.tensors.detach().cpu().numpy().astype(np.float32),
        {
            "image_id": int(target["image_id"][0].item()),
            "source_height": int(image.shape[-2]),
            "source_width": int(image.shape[-1]),
            "runtime_height": int(transformed.tensors.shape[-2]),
            "runtime_width": int(transformed.tensors.shape[-1]),
            "transformed_height": int(transformed.image_sizes[0][0]),
            "transformed_width": int(transformed.image_sizes[0][1]),
        },
    )


def build_random_runtime_input(metadata: dict[str, Any]) -> tuple[np.ndarray, dict[str, int]]:
    shape = [int(v) for v in metadata["runtime_input_tensor"]["shape"]]
    rng = np.random.default_rng(seed=1234)
    return (
        rng.normal(loc=0.0, scale=0.5, size=shape).astype(np.float32),
        {
            "image_id": -1,
            "source_height": int(shape[-2]),
            "source_width": int(shape[-1]),
            "runtime_height": int(shape[-2]),
            "runtime_width": int(shape[-1]),
            "transformed_height": int(shape[-2]),
            "transformed_width": int(shape[-1]),
        },
    )


def run_pytorch_reference(
    torch: Any,
    model: Any,
    runtime_input: np.ndarray,
) -> dict[str, np.ndarray]:
    input_height = int(runtime_input.shape[-2])
    input_width = int(runtime_input.shape[-1])
    wrapper = build_transform_free_raw_head_export_wrapper(
        detector=model,
        input_height=input_height,
        input_width=input_width,
    ).eval()
    with torch.no_grad():
        x = torch.from_numpy(runtime_input)
        bbox_regression, cls_logits, anchors = wrapper(x)
    return {
        "bbox_regression": bbox_regression.detach().cpu().numpy(),
        "cls_logits": cls_logits.detach().cpu().numpy(),
        "anchors_xyxy": anchors.detach().cpu().numpy(),
    }


def get_runtime_anchors_from_model(
    torch: Any,
    model: Any,
    runtime_input: np.ndarray,
) -> np.ndarray:
    return run_pytorch_reference(torch, model, runtime_input)["anchors_xyxy"]


def max_abs_diff(lhs: np.ndarray, rhs: np.ndarray) -> float:
    if lhs.size == 0 and rhs.size == 0:
        return 0.0
    return float(np.max(np.abs(lhs.astype(np.float32) - rhs.astype(np.float32))))


def summarize_detections(
    torch: Any,
    batched_nms: Any,
    outputs: dict[str, np.ndarray],
    cfg: dict[str, Any],
    image_meta: dict[str, int],
    class_names: list[str],
    score_thresh: float,
    nms_thresh: float,
    topk_candidates: int,
    detections_per_img: int,
) -> list[dict[str, Any]]:
    raw_output = raw_postprocess(
        torch=torch,
        batched_nms=batched_nms,
        bbox_regression=torch.from_numpy(outputs["bbox_regression"]),
        cls_logits=torch.from_numpy(outputs["cls_logits"]),
        anchors_xyxy=torch.from_numpy(outputs["anchors_xyxy"]),
        input_height=int(image_meta["runtime_height"]),
        input_width=int(image_meta["runtime_width"]),
        orig_height=int(image_meta["source_height"]),
        orig_width=int(image_meta["source_width"]),
        score_thresh=score_thresh,
        nms_thresh=nms_thresh,
        topk_candidates=topk_candidates,
        detections_per_img=detections_per_img,
    )
    detections = []
    for box, score, label in zip(raw_output["boxes"], raw_output["scores"], raw_output["labels"]):
        class_index = int(label.item()) - 1
        detections.append(
            {
                "class_id": class_index,
                "class_name": class_names[class_index] if 0 <= class_index < len(class_names) else "unknown",
                "score": float(score.item()),
                "bbox_xyxy": [int(float(v.item()) + 0.5) for v in box],
            }
        )
    return detections


def main() -> int:
    configure_console_encoding()
    args = parse_args()
    ort = require_onnxruntime()
    torch, batched_nms = require_torch_stack()
    metadata = load_json(args.metadata)

    model = None
    class_names = list(metadata.get("classes", {}).get("foreground_names", []))
    cfg = {
        "score_thresh": metadata.get("postprocess", {}).get("score_threshold", 0.2),
        "nms_thresh": metadata.get("postprocess", {}).get("nms_iou_threshold", 0.45),
    }
    if args.checkpoint is not None:
        model, class_names, cfg = load_model(torch, args.checkpoint)

    if model is not None and args.manifest is not None:
        runtime_input, image_meta = build_runtime_input_from_dataset(
            torch=torch,
            model=model,
            manifest=args.manifest,
            split=args.split,
            index=int(args.index),
        )
    else:
        runtime_input, image_meta = build_random_runtime_input(metadata)

    providers = pick_providers(ort, args.provider)
    session = ort.InferenceSession(str(args.onnx), providers=providers)
    input_name = session.get_inputs()[0].name
    output_names = [output.name for output in session.get_outputs()]

    start = time.perf_counter()
    output_values = session.run(output_names, {input_name: runtime_input})
    elapsed_ms = (time.perf_counter() - start) * 1000.0
    onnx_outputs = {name: value.astype(np.float32) for name, value in zip(output_names, output_values)}
    if "anchors_xyxy" not in onnx_outputs and model is not None:
        onnx_outputs["anchors_xyxy"] = get_runtime_anchors_from_model(torch, model, runtime_input)

    reference_summary = None
    if model is not None:
        ref_outputs = run_pytorch_reference(torch, model, runtime_input)
        reference_summary = {
            name: {
                "shape": list(onnx_outputs[name].shape),
                "max_abs_diff": max_abs_diff(onnx_outputs[name], ref_outputs[name]),
            }
            for name in ("bbox_regression", "cls_logits", "anchors_xyxy")
        }

    score_thresh = float(cfg["score_thresh"]) if args.score_thresh is None else float(args.score_thresh)
    nms_thresh = float(cfg["nms_thresh"]) if args.nms_thresh is None else float(args.nms_thresh)
    detections = summarize_detections(
        torch=torch,
        batched_nms=batched_nms,
        outputs=onnx_outputs,
        cfg=cfg,
        image_meta=image_meta,
        class_names=class_names,
        score_thresh=score_thresh,
        nms_thresh=nms_thresh,
        topk_candidates=int(args.topk_candidates),
        detections_per_img=int(args.detections_per_img),
    )

    passed = True
    if reference_summary is not None:
        passed = all(float(item["max_abs_diff"]) <= float(args.tolerance) for item in reference_summary.values())

    report = {
        "format": "ir_runtime_onnx_smoke_v1",
        "onnx": str(args.onnx),
        "metadata": str(args.metadata),
        "providers": providers,
        "input_name": input_name,
        "output_names": output_names,
        "input_shape": list(runtime_input.shape),
        "image_meta": image_meta,
        "elapsed_ms": elapsed_ms,
        "reference_tolerance": float(args.tolerance),
        "reference_summary": reference_summary,
        "detections": detections,
        "passed": passed,
    }

    args.output_dir.mkdir(parents=True, exist_ok=True)
    report_path = args.output_dir / "runtime_onnx_smoke.json"
    with report_path.open("w", encoding="utf-8") as fp:
        json.dump(report, fp, indent=2, ensure_ascii=False)
        fp.write("\n")

    print(f"ONNX Runtime providers={providers}")
    print(f"Input {input_name} shape={tuple(runtime_input.shape)}")
    for name in output_names:
        print(f"Output {name} shape={tuple(onnx_outputs[name].shape)}")
    if reference_summary is not None:
        for name, item in reference_summary.items():
            print(f"Compare {name} max_abs_diff={item['max_abs_diff']:.8g}")
    print(f"Detections count={len(detections)} elapsed_ms={elapsed_ms:.3f}")
    for idx, det in enumerate(detections):
        print(
            f"det{idx} class={det['class_name']} score={det['score']:.3f} "
            f"bbox={det['bbox_xyxy']}"
        )
    print(f"Report: {report_path}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
