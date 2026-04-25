from __future__ import annotations

import json
import random
from collections import Counter
from pathlib import Path
from typing import Any

from PIL import Image

REPO_ROOT = Path(__file__).resolve().parents[2]


def _require_torch() -> tuple[Any, Any]:
    try:
        import torch
        from torch.utils.data import Dataset
    except ImportError as exc:  # pragma: no cover - runtime dependency
        raise RuntimeError(
            "PyTorch is required for dataset loading. Install torch/torchvision in a training environment."
        ) from exc
    return torch, Dataset


class FlirCocoDetectionDataset(_require_torch()[1]):
    """Load the filtered FLIR thermal subset in COCO format for detection training."""

    def __init__(
        self,
        manifest_path: str | Path,
        split: str,
        training: bool = False,
        max_samples: int | None = None,
        hflip_prob: float = 0.0,
    ) -> None:
        self.manifest_path = Path(manifest_path)
        self.split = split
        self.training = training
        self.hflip_prob = hflip_prob if training else 0.0

        with self.manifest_path.open("r", encoding="utf-8") as fp:
            manifest = json.load(fp)

        split_meta = manifest["splits"][split]
        self.image_root = self._resolve_manifest_path(split_meta["image_root"])
        self.annotation_file = self._resolve_manifest_path(split_meta["annotation_file"])
        self.class_names = list(manifest["target_classes"])

        with self.annotation_file.open("r", encoding="utf-8") as fp:
            coco = json.load(fp)

        self.images = list(coco["images"])
        self.categories = list(coco["categories"])
        self.category_id_to_name = {int(cat["id"]): str(cat["name"]) for cat in self.categories}
        self.annotations_by_image: dict[int, list[dict[str, Any]]] = {}
        for ann in coco["annotations"]:
            self.annotations_by_image.setdefault(int(ann["image_id"]), []).append(ann)

        if max_samples is not None:
            self.images = self.images[:max_samples]

        self.image_class_ids: list[tuple[int, ...]] = []
        class_image_counter: Counter[int] = Counter()
        self.empty_image_count = 0
        for image_info in self.images:
            annotations = self.annotations_by_image.get(int(image_info["id"]), [])
            class_ids = self._extract_valid_class_ids(image_info, annotations)
            self.image_class_ids.append(class_ids)
            if not class_ids:
                self.empty_image_count += 1
                continue
            for class_id in class_ids:
                class_image_counter[class_id] += 1

        self.class_image_counts = {
            int(category["id"]): int(class_image_counter.get(int(category["id"]), 0))
            for category in self.categories
        }

    def _resolve_manifest_path(self, raw_path: str | Path) -> Path:
        candidate = Path(raw_path)
        if candidate.is_absolute():
            return candidate

        manifest_relative = (self.manifest_path.parent / candidate).resolve()
        if manifest_relative.exists():
            return manifest_relative

        repo_relative = (REPO_ROOT / candidate).resolve()
        if repo_relative.exists():
            return repo_relative

        return candidate.resolve()

    def __len__(self) -> int:
        return len(self.images)

    def _load_image(self, file_name: str) -> Image.Image:
        image_path = self.image_root / Path(file_name)
        if not image_path.exists():
            raise FileNotFoundError(f"Image file not found: {image_path}")
        return Image.open(image_path).convert("L")

    def _build_target(
        self,
        image_info: dict[str, Any],
        width: int,
        annotations: list[dict[str, Any]],
    ) -> dict[str, Any]:
        boxes = []
        labels = []
        areas = []
        iscrowd = []

        for ann in annotations:
            x, y, w, h = ann["bbox"]
            if w <= 1.0 or h <= 1.0:
                continue
            x1 = max(0.0, float(x))
            y1 = max(0.0, float(y))
            x2 = min(float(image_info["width"]), x1 + float(w))
            y2 = min(float(image_info["height"]), y1 + float(h))
            if x2 <= x1 or y2 <= y1:
                continue

            boxes.append([x1, y1, x2, y2])
            labels.append(int(ann["category_id"]))
            areas.append(float(ann.get("area", w * h)))
            iscrowd.append(int(ann.get("iscrowd", 0)))

        if boxes:
            torch, _ = _require_torch()
            boxes_tensor = torch.tensor(boxes, dtype=torch.float32)
            labels_tensor = torch.tensor(labels, dtype=torch.int64)
            area_tensor = torch.tensor(areas, dtype=torch.float32)
            iscrowd_tensor = torch.tensor(iscrowd, dtype=torch.int64)
        else:
            torch, _ = _require_torch()
            boxes_tensor = torch.zeros((0, 4), dtype=torch.float32)
            labels_tensor = torch.zeros((0,), dtype=torch.int64)
            area_tensor = torch.zeros((0,), dtype=torch.float32)
            iscrowd_tensor = torch.zeros((0,), dtype=torch.int64)

        return {
            "boxes": boxes_tensor,
            "labels": labels_tensor,
            "image_id": torch.tensor([int(image_info["id"])], dtype=torch.int64),
            "area": area_tensor,
            "iscrowd": iscrowd_tensor,
            "orig_size": torch.tensor([int(image_info["height"]), int(image_info["width"])], dtype=torch.int64),
            "size": torch.tensor([int(image_info["height"]), int(image_info["width"])], dtype=torch.int64),
        }

    def _extract_valid_class_ids(
        self,
        image_info: dict[str, Any],
        annotations: list[dict[str, Any]],
    ) -> tuple[int, ...]:
        class_ids = set()
        for ann in annotations:
            x, y, w, h = ann["bbox"]
            if w <= 1.0 or h <= 1.0:
                continue
            x1 = max(0.0, float(x))
            y1 = max(0.0, float(y))
            x2 = min(float(image_info["width"]), x1 + float(w))
            y2 = min(float(image_info["height"]), y1 + float(h))
            if x2 <= x1 or y2 <= y1:
                continue
            class_ids.add(int(ann["category_id"]))
        return tuple(sorted(class_ids))

    def build_sampling_weights(
        self,
        rare_class_power: float = 1.0,
        empty_image_weight: float = 0.2,
        max_class_weight: float = 4.0,
    ) -> list[float]:
        if rare_class_power < 0.0:
            raise ValueError("rare_class_power must be >= 0")
        if empty_image_weight <= 0.0:
            raise ValueError("empty_image_weight must be > 0")
        if max_class_weight < 1.0:
            raise ValueError("max_class_weight must be >= 1")

        positive_counts = [count for count in self.class_image_counts.values() if count > 0]
        if not positive_counts:
            return [1.0] * len(self.images)

        reference_count = max(positive_counts)
        class_weights: dict[int, float] = {}
        for class_id, image_count in self.class_image_counts.items():
            if image_count <= 0:
                class_weights[class_id] = float(max_class_weight)
                continue
            raw_weight = (float(reference_count) / float(image_count)) ** rare_class_power
            class_weights[class_id] = min(float(max_class_weight), max(1.0, raw_weight))

        weights = []
        for class_ids in self.image_class_ids:
            if not class_ids:
                weights.append(float(empty_image_weight))
                continue
            weights.append(max(class_weights[class_id] for class_id in class_ids))
        return weights

    def summarize_sampling_weights(
        self,
        rare_class_power: float = 1.0,
        empty_image_weight: float = 0.2,
        max_class_weight: float = 4.0,
    ) -> dict[str, Any]:
        weights = self.build_sampling_weights(
            rare_class_power=rare_class_power,
            empty_image_weight=empty_image_weight,
            max_class_weight=max_class_weight,
        )
        positive_counts = [count for count in self.class_image_counts.values() if count > 0]
        reference_count = max(positive_counts) if positive_counts else 1
        class_weights = {}
        for category in self.categories:
            class_id = int(category["id"])
            image_count = int(self.class_image_counts.get(class_id, 0))
            if image_count <= 0:
                weight = float(max_class_weight)
            else:
                weight = min(
                    float(max_class_weight),
                    max(1.0, (float(reference_count) / float(image_count)) ** rare_class_power),
                )
            class_weights[str(category["name"])] = {
                "image_count": image_count,
                "weight": float(weight),
            }
        return {
            "num_images": len(self.images),
            "num_empty_images": int(self.empty_image_count),
            "empty_image_weight": float(empty_image_weight),
            "rare_class_power": float(rare_class_power),
            "max_class_weight": float(max_class_weight),
            "class_image_counts": class_weights,
            "weight_min": float(min(weights)) if weights else 0.0,
            "weight_max": float(max(weights)) if weights else 0.0,
            "weight_mean": float(sum(weights) / max(len(weights), 1)),
        }

    def _maybe_horizontal_flip(
        self,
        image_tensor: Any,
        target: dict[str, Any],
        width: int,
    ) -> tuple[Any, dict[str, Any]]:
        if self.hflip_prob <= 0.0 or random.random() >= self.hflip_prob:
            return image_tensor, target

        torch, _ = _require_torch()
        image_tensor = torch.flip(image_tensor, dims=[2])
        boxes = target["boxes"].clone()
        if boxes.numel() > 0:
            old_x1 = boxes[:, 0].clone()
            old_x2 = boxes[:, 2].clone()
            boxes[:, 0] = width - old_x2
            boxes[:, 2] = width - old_x1
            target = dict(target)
            target["boxes"] = boxes
        return image_tensor, target

    def __getitem__(self, index: int) -> tuple[Any, dict[str, Any]]:
        torch, _ = _require_torch()
        image_info = self.images[index]
        image = self._load_image(str(image_info["file_name"]))
        width, height = image.size

        image_tensor = torch.from_numpy(__import__("numpy").array(image, dtype="float32") / 255.0)
        image_tensor = image_tensor.unsqueeze(0)

        annotations = self.annotations_by_image.get(int(image_info["id"]), [])
        target = self._build_target(image_info, width, annotations)
        image_tensor, target = self._maybe_horizontal_flip(image_tensor, target, width)
        return image_tensor, target


def detection_collate_fn(batch: list[tuple[Any, dict[str, Any]]]) -> tuple[list[Any], list[dict[str, Any]]]:
    images, targets = zip(*batch)
    return list(images), list(targets)
