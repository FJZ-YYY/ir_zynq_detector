#!/usr/bin/env python3
"""Create a minimal deployment bundle contract for the Zynq IR detector."""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as fp:
        data = yaml.safe_load(fp)
    if not isinstance(data, dict):
        raise ValueError(f"Top-level YAML object must be a mapping: {path}")
    return data


def ensure_output_dir(path: Path, overwrite: bool) -> None:
    if path.exists():
        if not overwrite:
            raise FileExistsError(
                f"Output directory already exists: {path}. Use --overwrite to refresh it."
            )
        if not path.is_dir():
            raise NotADirectoryError(f"Output path exists but is not a directory: {path}")
        for child in path.iterdir():
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()
    path.mkdir(parents=True, exist_ok=True)


def get_required_section(cfg: dict[str, Any], key: str) -> dict[str, Any]:
    section = cfg.get(key)
    if not isinstance(section, dict):
        raise ValueError(f"Missing or invalid section '{key}' in project config")
    return section


def build_manifest(
    cfg: dict[str, Any],
    bundle_name: str,
    backend: str,
    model_path: Path | None,
) -> dict[str, Any]:
    project = get_required_section(cfg, "project")
    dataset = get_required_section(cfg, "dataset")
    model = get_required_section(cfg, "model")
    board = get_required_section(cfg, "board")
    io_cfg = get_required_section(cfg, "io")
    uart_cfg = get_required_section(io_cfg, "uart")

    classes = dataset.get("classes")
    if not isinstance(classes, list) or not all(isinstance(x, str) for x in classes):
        raise ValueError("dataset.classes must be a list of strings")

    input_width = int(model.get("input_width", 160))
    input_height = int(model.get("input_height", 128))
    score_threshold = float(model.get("score_threshold", 0.35))
    iou_threshold = float(model.get("iou_threshold", 0.45))

    source_model = None
    if model_path is not None:
        source_model = str(model_path)

    return {
        "bundle_version": 1,
        "bundle_name": bundle_name,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "project": {
            "name": str(project.get("name", "ir_zynq_detector")),
            "stage": str(project.get("stage", "unknown")),
        },
        "dataset": {
            "name": str(dataset.get("name", "unknown")),
            "classes": classes,
            "num_classes": len(classes),
        },
        "model": {
            "backend": backend,
            "source_model_path": source_model,
            "export_format": str(model.get("export_format", "onnx")),
            "input_width": input_width,
            "input_height": input_height,
            "input_pixel_format": str(uart_cfg.get("pixel_format", "gray8")),
            "input_tensor_layout": "1x1xHxW",
            "input_tensor_dtype": "float32",
            "score_threshold": score_threshold,
            "iou_threshold": iou_threshold,
            "max_detections": 4,
        },
        "preprocess": {
            "source_transport": str(io_cfg.get("input_transport", "uart")),
            "host_decodes_image_file": bool(io_cfg.get("pc_decode_image_file", True)),
            "board_resize_image": bool(io_cfg.get("board_resize_image", True)),
            "board_normalize_image": bool(io_cfg.get("board_normalize_image", True)),
            "resize_algorithm": "bilinear",
            "normalize": {
                "input_scale": 1.0 / 255.0,
                "mean": 0.0,
                "stddev": 1.0,
            },
        },
        "output_contract": {
            "format": "detection_list" if backend == "stub" else "raw_ssd_head",
            "bbox_format": "xyxy",
            "score_encoding": "x1000 on bare-metal print path",
            "class_fields": ["class_id", "class_name"],
            "detection_fields": [
                "class_id",
                "class_name",
                "score_x1000",
                "x1",
                "y1",
                "x2",
                "y2",
            ]
            if backend == "stub"
            else [
                "bbox_regression",
                "cls_logits",
                "anchors_xyxy",
            ],
        },
        "board_target": {
            "family": str(board.get("family", "zynq-7000")),
            "soc": str(board.get("soc", "zynq-7020")),
            "toolchain": str(board.get("toolchain", "vivado_vitis_2020_2")),
            "ps_runtime": str(board.get("ps_runtime", "baremetal_first")),
            "runtime_backend": backend,
            "uart_baud_rate": int(uart_cfg.get("baud_rate", 921600)),
            "max_payload_bytes": int(uart_cfg.get("max_payload_bytes", 327680)),
        },
        "notes": [
            "This bundle is the deployment contract between PC export and PS-side model_runner.",
            "The current board backend is still stub-based until a real quantized model is integrated."
            if backend == "stub"
            else "The exported ONNX now provides raw SSD head tensors and leaves decode/NMS to the PS runtime.",
            "A future ONNX or int8 backend should preserve the same preprocess contract.",
        ],
    }


def write_json(path: Path, data: dict[str, Any]) -> None:
    with path.open("w", encoding="utf-8") as fp:
        json.dump(data, fp, indent=2, ensure_ascii=False)
        fp.write("\n")


def write_lines(path: Path, lines: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as fp:
        for line in lines:
            fp.write(f"{line}\n")


def copy_model_if_present(model_path: Path | None, output_dir: Path) -> str | None:
    if model_path is None:
        return None
    if not model_path.exists():
        raise FileNotFoundError(f"Model file does not exist: {model_path}")

    dst_path = output_dir / model_path.name
    shutil.copy2(model_path, dst_path)
    return dst_path.name


def copy_optional_artifact(src_path: Path | None, output_dir: Path) -> str | None:
    if src_path is None:
        return None
    if not src_path.exists():
        raise FileNotFoundError(f"Artifact file does not exist: {src_path}")

    dst_path = output_dir / src_path.name
    shutil.copy2(src_path, dst_path)
    return dst_path.name


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create a minimal deploy bundle contract for the Zynq IR detector."
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/project_config.yaml"),
        help="Project config YAML path.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("build/model_export"),
        help="Directory that will receive the generated bundle files.",
    )
    parser.add_argument(
        "--bundle-name",
        type=str,
        default="irdet_deploy_bundle",
        help="Logical name written into the deployment manifest.",
    )
    parser.add_argument(
        "--backend",
        choices=("stub", "onnx_raw_head"),
        default="stub",
        help="Current deployment backend. More backends will be added later.",
    )
    parser.add_argument(
        "--model-path",
        type=Path,
        default=None,
        help="Optional path to a real exported model file such as ONNX.",
    )
    parser.add_argument(
        "--export-metadata",
        type=Path,
        default=None,
        help="Optional JSON metadata generated beside the ONNX export.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Allow replacing an existing output directory.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    cfg = load_yaml(args.config)
    ensure_output_dir(args.output_dir, args.overwrite)

    manifest = build_manifest(
        cfg=cfg,
        bundle_name=args.bundle_name,
        backend=args.backend,
        model_path=args.model_path,
    )

    copied_model_name = copy_model_if_present(args.model_path, args.output_dir)
    copied_metadata_name = copy_optional_artifact(args.export_metadata, args.output_dir)

    classes = manifest["dataset"]["classes"]
    quant_params = {
        "mode": "placeholder",
        "input_scale": manifest["preprocess"]["normalize"]["input_scale"],
        "mean": manifest["preprocess"]["normalize"]["mean"],
        "stddev": manifest["preprocess"]["normalize"]["stddev"],
        "weights_dtype": "not_available_yet",
        "activation_dtype": "float32_stub",
        "notes": [
            "Replace this file with real calibration results after model quantization.",
            "The bare-metal preprocess path already matches input_scale/mean/stddev in this file.",
        ],
    }
    tensor_contract = {
        "input_tensor": {
            "name": "input_0",
            "shape": [1, 1, manifest["model"]["input_height"], manifest["model"]["input_width"]],
            "dtype": "float32",
            "layout": manifest["model"]["input_tensor_layout"],
        }
    }

    if args.backend == "onnx_raw_head":
        metadata = None
        if args.export_metadata is not None:
            with args.export_metadata.open("r", encoding="utf-8") as fp:
                metadata = json.load(fp)

        if metadata is None:
            tensor_contract["output_tensors"] = [
                {"name": "bbox_regression", "dtype": "float32", "meaning": "ssd_box_deltas"},
                {"name": "cls_logits", "dtype": "float32", "meaning": "raw_class_logits"},
                {"name": "anchors_xyxy", "dtype": "float32", "meaning": "anchor_boxes_xyxy_pixels"},
            ]
        else:
            tensor_contract["output_tensors"] = metadata.get("output_tensors", [])
            tensor_contract["classes"] = metadata.get("classes", {})
            tensor_contract["export_format"] = metadata.get("export_format", "ssdlite_raw_head_v1")
    else:
        tensor_contract["output_tensor"] = {
            "name": "detections_0",
            "format": "detection_list_placeholder",
            "max_detections": manifest["model"]["max_detections"],
            "fields": manifest["output_contract"]["detection_fields"],
        }

    manifest["artifacts"] = {
        "manifest_json": "deploy_manifest.json",
        "classes_txt": "classes.txt",
        "quant_params_json": "quant_params.json",
        "tensor_contract_json": "tensor_contract.json",
        "model_file": copied_model_name,
        "export_metadata_json": copied_metadata_name,
    }

    write_json(args.output_dir / "deploy_manifest.json", manifest)
    write_json(args.output_dir / "quant_params.json", quant_params)
    write_json(args.output_dir / "tensor_contract.json", tensor_contract)
    write_lines(args.output_dir / "classes.txt", list(classes))

    note_lines = [
        f"bundle_name={args.bundle_name}",
        f"backend={args.backend}",
        f"classes={','.join(classes)}",
        f"input={manifest['model']['input_width']}x{manifest['model']['input_height']}",
        f"score_threshold={manifest['model']['score_threshold']}",
        f"iou_threshold={manifest['model']['iou_threshold']}",
        f"model_file={copied_model_name if copied_model_name else '<not provided>'}",
        "status=deployment_contract_ready",
    ]
    write_lines(args.output_dir / "bundle_summary.txt", note_lines)

    print(f"Bundle created: {args.output_dir}")
    print(f"Classes: {', '.join(classes)}")
    print(
        "Input tensor: "
        f"1x1x{manifest['model']['input_height']}x{manifest['model']['input_width']} "
        f"dtype={tensor_contract['input_tensor']['dtype']}"
    )
    if copied_model_name is None:
        print("Model file: <not provided, placeholder bundle only>")
    else:
        print(f"Model file copied: {copied_model_name}")
    print("Generated files: deploy_manifest.json, classes.txt, quant_params.json, tensor_contract.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
