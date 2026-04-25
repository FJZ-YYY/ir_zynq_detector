#!/usr/bin/env python3
"""Prepare a minimal FLIR thermal 3-class subset for lightweight detector training."""

from __future__ import annotations

import argparse
import json
import shutil
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


CANONICAL_TO_FLIR_NAME = {
    "person": "person",
    "bicycle": "bike",
    "car": "car",
}

THERMAL_SPLITS = {
    "train": "images_thermal_train",
    "val": "images_thermal_val",
}


@dataclass
class SplitResult:
    split_name: str
    image_root: Path
    annotation_path: Path
    num_images: int
    num_annotations: int
    class_counts: dict[str, int]


def strip_wrapping_quotes(value: str | None) -> str | None:
    if value is None:
        return None
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        return value[1:-1]
    return value


def parse_path_arg(value: str) -> Path:
    return Path(strip_wrapping_quotes(value))


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as fp:
        data = yaml.safe_load(fp)
    if not isinstance(data, dict):
        raise ValueError(f"Invalid YAML mapping: {path}")
    return data


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as fp:
        data = json.load(fp)
    if not isinstance(data, dict):
        raise ValueError(f"Invalid JSON mapping: {path}")
    return data


def ensure_clean_dir(path: Path, overwrite: bool) -> None:
    if path.exists():
        if not overwrite:
            raise FileExistsError(
                f"Output directory already exists: {path}. Use --overwrite to replace it."
            )
        if not path.is_dir():
            raise NotADirectoryError(f"Output path exists but is not a directory: {path}")
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def get_target_classes(config_path: Path) -> list[str]:
    cfg = load_yaml(config_path)
    dataset_cfg = cfg.get("dataset")
    if not isinstance(dataset_cfg, dict):
        raise ValueError("Missing dataset section in project config")

    classes = dataset_cfg.get("classes")
    if not isinstance(classes, list) or not all(isinstance(x, str) for x in classes):
        raise ValueError("dataset.classes must be a list of strings")

    normalized = [x.strip().lower() for x in classes]
    unsupported = [name for name in normalized if name not in CANONICAL_TO_FLIR_NAME]
    if unsupported:
        raise ValueError(f"Unsupported class names in config: {unsupported}")
    return normalized


def build_source_category_map(
    categories: list[dict[str, Any]],
    target_classes: list[str],
) -> dict[int, tuple[int, str, str]]:
    by_name = {}
    for cat in categories:
        name = str(cat.get("name", "")).strip().lower()
        by_name[name] = int(cat["id"])

    mapping: dict[int, tuple[int, str, str]] = {}
    for idx, canonical_name in enumerate(target_classes, start=1):
        source_name = CANONICAL_TO_FLIR_NAME[canonical_name]
        if source_name not in by_name:
            raise ValueError(f"Source category '{source_name}' not found in FLIR categories")
        source_id = by_name[source_name]
        mapping[source_id] = (idx, canonical_name, source_name)
    return mapping


def make_output_categories(target_classes: list[str]) -> list[dict[str, Any]]:
    return [
        {
            "id": idx,
            "name": class_name,
            "supercategory": "target",
        }
        for idx, class_name in enumerate(target_classes, start=1)
    ]


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fp:
        json.dump(data, fp, indent=2, ensure_ascii=False)
        fp.write("\n")


def write_lines(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as fp:
        for line in lines:
            fp.write(f"{line}\n")


def filter_split(
    dataset_root: Path,
    split_name: str,
    split_dir_name: str,
    target_classes: list[str],
    output_dir: Path,
    keep_empty: bool,
) -> SplitResult:
    split_root = dataset_root / split_dir_name
    coco_path = split_root / "coco.json"
    coco = load_json(coco_path)

    images = coco.get("images", [])
    annotations = coco.get("annotations", [])
    categories = coco.get("categories", [])
    if not isinstance(images, list) or not isinstance(annotations, list) or not isinstance(categories, list):
        raise ValueError(f"Invalid COCO structure in {coco_path}")

    source_category_map = build_source_category_map(categories, target_classes)
    kept_annotations = []
    class_counter: Counter[str] = Counter()

    for ann in annotations:
        source_cat_id = int(ann["category_id"])
        mapped = source_category_map.get(source_cat_id)
        if mapped is None:
            continue

        target_cat_id, canonical_name, source_name = mapped
        new_ann = dict(ann)
        new_ann["category_id"] = target_cat_id
        new_ann["irdet_meta"] = {
            "source_category_id": source_cat_id,
            "source_category_name": source_name,
        }
        kept_annotations.append(new_ann)
        class_counter[canonical_name] += 1

    image_ids_with_targets = {int(ann["image_id"]) for ann in kept_annotations}

    kept_images = []
    for img in images:
        image_id = int(img["id"])
        if keep_empty or image_id in image_ids_with_targets:
            kept_images.append(dict(img))

    image_id_remap: dict[int, int] = {}
    compact_images = []
    for new_image_id, img in enumerate(kept_images):
        old_image_id = int(img["id"])
        image_id_remap[old_image_id] = new_image_id

        new_img = dict(img)
        new_img["id"] = new_image_id
        new_img["irdet_meta"] = {"original_image_id": old_image_id}
        compact_images.append(new_img)

    compact_annotations = []
    next_ann_id = 0
    for ann in kept_annotations:
        old_image_id = int(ann["image_id"])
        if old_image_id not in image_id_remap:
            continue

        new_ann = dict(ann)
        new_ann["id"] = next_ann_id
        new_ann["image_id"] = image_id_remap[old_image_id]
        compact_annotations.append(new_ann)
        next_ann_id += 1

    subset_coco = {
        "info": coco.get("info", {}),
        "licenses": coco.get("licenses", []),
        "images": compact_images,
        "annotations": compact_annotations,
        "categories": make_output_categories(target_classes),
        "irdet_meta": {
            "prepared_utc": datetime.now(timezone.utc).isoformat(),
            "source_split": split_dir_name,
            "split_name": split_name,
            "target_classes": target_classes,
            "keep_empty_images": keep_empty,
        },
    }

    annotation_path = output_dir / "annotations" / f"thermal_{split_name}_3cls_coco.json"
    write_json(annotation_path, subset_coco)

    image_list = [
        str(split_root / str(img["file_name"]).replace("/", "\\"))
        for img in compact_images
    ]
    write_lines(output_dir / "lists" / f"thermal_{split_name}.txt", image_list)

    return SplitResult(
        split_name=split_name,
        image_root=split_root,
        annotation_path=annotation_path,
        num_images=len(compact_images),
        num_annotations=len(compact_annotations),
        class_counts={name: int(class_counter.get(name, 0)) for name in target_classes},
    )


def build_manifest(
    dataset_root: Path,
    config_path: Path,
    output_dir: Path,
    target_classes: list[str],
    split_results: list[SplitResult],
    keep_empty: bool,
) -> dict[str, Any]:
    classes_meta = []
    for zero_based_id, canonical_name in enumerate(target_classes):
        source_name = CANONICAL_TO_FLIR_NAME[canonical_name]
        classes_meta.append(
            {
                "train_id": zero_based_id,
                "coco_category_id": zero_based_id + 1,
                "canonical_name": canonical_name,
                "source_name": source_name,
            }
        )

    splits_meta = {}
    for result in split_results:
        splits_meta[result.split_name] = {
            "image_root": str(result.image_root),
            "annotation_file": str(result.annotation_path),
            "image_list": str(output_dir / "lists" / f"thermal_{result.split_name}.txt"),
            "num_images": result.num_images,
            "num_annotations": result.num_annotations,
            "class_counts": result.class_counts,
        }

    return {
        "manifest_version": 1,
        "prepared_utc": datetime.now(timezone.utc).isoformat(),
        "dataset_name": "FLIR_ADAS_v2_thermal_3cls",
        "source_dataset_root": str(dataset_root),
        "project_config": str(config_path),
        "target_classes": target_classes,
        "keep_empty_images": keep_empty,
        "classes": classes_meta,
        "splits": splits_meta,
        "notes": [
            "FLIR category name 'bike' is remapped to canonical name 'bicycle'.",
            "Output COCO subset uses contiguous category ids 1..N.",
            "Model-side class indices should use zero-based train_id order from this manifest.",
        ],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prepare a FLIR thermal 3-class subset for lightweight detector training."
    )
    parser.add_argument(
        "--dataset-root",
        type=parse_path_arg,
        required=True,
        help="Path to FLIR_ADAS_v2 root directory.",
    )
    parser.add_argument(
        "--config",
        type=parse_path_arg,
        default=Path("configs/project_config.yaml"),
        help="Project config YAML. dataset.classes defines the target class order.",
    )
    parser.add_argument(
        "--output-dir",
        type=parse_path_arg,
        default=Path("build/flir_thermal_3cls"),
        help="Directory to write filtered annotations and manifests.",
    )
    parser.add_argument(
        "--keep-empty",
        action="store_true",
        help="Keep images without target annotations. Default is to keep only positive images.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace an existing output directory.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.dataset_root.exists():
        raise FileNotFoundError(f"Dataset root does not exist: {args.dataset_root}")

    target_classes = get_target_classes(args.config)
    ensure_clean_dir(args.output_dir, args.overwrite)

    split_results = []
    for split_name, split_dir_name in THERMAL_SPLITS.items():
        split_results.append(
            filter_split(
                dataset_root=args.dataset_root,
                split_name=split_name,
                split_dir_name=split_dir_name,
                target_classes=target_classes,
                output_dir=args.output_dir,
                keep_empty=args.keep_empty,
            )
        )

    manifest = build_manifest(
        dataset_root=args.dataset_root,
        config_path=args.config,
        output_dir=args.output_dir,
        target_classes=target_classes,
        split_results=split_results,
        keep_empty=args.keep_empty,
    )
    write_json(args.output_dir / "dataset_manifest.json", manifest)
    write_lines(args.output_dir / "classes.txt", target_classes)

    print(f"Prepared dataset subset: {args.output_dir}")
    print(f"Target classes: {', '.join(target_classes)}")
    for result in split_results:
        class_counts_text = ", ".join(f"{k}={v}" for k, v in result.class_counts.items())
        print(
            f"{result.split_name}: images={result.num_images} annotations={result.num_annotations} "
            f"[{class_counts_text}]"
        )
    print("Generated files: dataset_manifest.json, classes.txt, filtered COCO json, image lists")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
