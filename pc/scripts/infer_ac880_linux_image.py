#!/usr/bin/env python3
"""Decode one PC-side image, upload GRAY8 raw to AC880 Linux, and run board-side inference."""

from __future__ import annotations

import argparse
import json
import os
import posixpath
import random
import re
import sys
from pathlib import Path
from typing import Iterable, Optional

try:
    import paramiko
except ImportError as exc:  # pragma: no cover - handled at runtime
    raise SystemExit(
        "paramiko is required. Install it with: python -m pip install --user paramiko"
    ) from exc

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError as exc:  # pragma: no cover - handled at runtime
    raise SystemExit("Pillow is required. Install it with: python -m pip install --user pillow") from exc


IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff")
TARGET_CLASS_MAP = {
    "person": "person",
    "bike": "bicycle",
    "bicycle": "bicycle",
    "car": "car",
}


def strip_wrapping_quotes(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        return value[1:-1]
    return value


def parse_path_arg(value: str) -> Path:
    return Path(strip_wrapping_quotes(value))


def is_image_file(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS


def collect_dataset_images(dataset_root: Path) -> list[Path]:
    return sorted(path for path in dataset_root.rglob("*") if is_image_file(path))


def filter_images(images: Iterable[Path], name_contains: Optional[str]) -> list[Path]:
    if not name_contains:
        return list(images)
    needle = name_contains.lower()
    return [path for path in images if needle in str(path).lower()]


def resolve_image_path(
    image_path: Optional[Path],
    dataset_root: Optional[Path],
    index: int,
    name_contains: Optional[str],
    pick_mode: str,
) -> tuple[Path, Optional[dict]]:
    if image_path is not None:
        if not image_path.exists():
            raise FileNotFoundError(f"Image does not exist: {image_path}")
        return image_path, None

    if dataset_root is None:
        raise ValueError("Either --image or --dataset-root must be provided")
    if not dataset_root.exists():
        raise FileNotFoundError(f"Dataset root does not exist: {dataset_root}")

    images = collect_dataset_images(dataset_root)
    images = filter_images(images, name_contains)
    if not images:
        raise FileNotFoundError("No image files were found under the selected dataset root")

    if pick_mode == "random":
        selected = random.choice(images)
        selected_index = images.index(selected)
    else:
        if index < 0 or index >= len(images):
            raise IndexError(f"Image index {index} is out of range for {len(images)} files")
        selected = images[index]
        selected_index = index

    meta = {
        "dataset_root": str(dataset_root),
        "match": name_contains,
        "candidate_count": len(images),
        "selected_index": selected_index,
        "pick_mode": pick_mode,
    }
    return selected, meta


def load_gray_payload(image_path: Path) -> tuple[int, int, bytes]:
    image = Image.open(image_path).convert("L")
    width, height = image.size
    payload = image.tobytes()
    return width, height, payload


def checksum32(data: bytes) -> int:
    return sum(data) & 0xFFFFFFFF


def sanitize_name(name: str) -> str:
    sanitized = re.sub(r"[^A-Za-z0-9._-]", "_", name)
    return sanitized or "input"


def ensure_remote_dir(sftp, remote_path: str) -> None:
    if remote_path in ("", "/"):
        return
    parts = []
    current = remote_path
    while current not in ("", "/"):
        parts.append(current)
        current = posixpath.dirname(current)
    for part in reversed(parts):
        try:
            sftp.stat(part)
        except FileNotFoundError:
            sftp.mkdir(part)


def upload_bytes(sftp, remote_path: str, data: bytes) -> None:
    ensure_remote_dir(sftp, posixpath.dirname(remote_path))
    with sftp.file(remote_path, "wb") as remote_file:
        remote_file.write(data)


def run_command(ssh: paramiko.SSHClient, command: str, timeout: int) -> tuple[int, str, str]:
    stdin, stdout, stderr = ssh.exec_command(command, timeout=timeout)
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    rc = stdout.channel.recv_exit_status()
    return rc, out, err


def parse_remote_output(output_text: str) -> dict:
    result = {
        "model": {},
        "preprocess": {},
        "det_count": 0,
        "detections": [],
        "raw_output": output_text,
    }

    det_re = re.compile(
        r"^det(?P<index>\d+)\s+class=(?P<class_name>\S+)\s+score=(?P<score>[0-9.]+)\s+bbox=\[(?P<x1>-?\d+),(?P<y1>-?\d+),(?P<x2>-?\d+),(?P<y2>-?\d+)\]$"
    )
    model_re = re.compile(
        r"^Model backend=(?P<backend>\S+)\s+runtime_in=(?P<runtime_w>\d+)x(?P<runtime_h>\d+)\s+anchors=(?P<anchors>\d+)\s+score_thresh=(?P<score_thresh>\d+)\s+mean=(?P<mean>-?[0-9.]+)\s+std=(?P<std>-?[0-9.]+)$"
    )
    preprocess_re = re.compile(
        r"^pre_in=(?P<src_w>\d+)x(?P<src_h>\d+)\s+pre_out=(?P<dst_w>\d+)x(?P<dst_h>\d+)\s+min=(?P<min>\d+)\s+max=(?P<max>\d+)\s+mean_x1000=(?P<mean_x1000>-?\d+)$"
    )
    count_re = re.compile(r"^det_count=(?P<count>\d+)$")

    for raw_line in output_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        match = model_re.match(line)
        if match:
            result["model"] = {
                "backend": match.group("backend"),
                "runtime_width": int(match.group("runtime_w")),
                "runtime_height": int(match.group("runtime_h")),
                "anchors": int(match.group("anchors")),
                "score_thresh_x1000": int(match.group("score_thresh")),
                "mean": float(match.group("mean")),
                "stddev": float(match.group("std")),
            }
            continue

        match = preprocess_re.match(line)
        if match:
            result["preprocess"] = {
                "src_width": int(match.group("src_w")),
                "src_height": int(match.group("src_h")),
                "dst_width": int(match.group("dst_w")),
                "dst_height": int(match.group("dst_h")),
                "min_pixel": int(match.group("min")),
                "max_pixel": int(match.group("max")),
                "mean_x1000": int(match.group("mean_x1000")),
            }
            continue

        match = count_re.match(line)
        if match:
            result["det_count"] = int(match.group("count"))
            continue

        match = det_re.match(line)
        if match:
            result["detections"].append(
                {
                    "index": int(match.group("index")),
                    "class_name": match.group("class_name"),
                    "score": float(match.group("score")),
                    "bbox_xyxy": [
                        int(match.group("x1")),
                        int(match.group("y1")),
                        int(match.group("x2")),
                        int(match.group("y2")),
                    ],
                }
            )

    return result


def load_flir_ground_truth_for_image(image_path: Path) -> list[dict]:
    image_path = image_path.resolve()
    split_dir = image_path.parent.parent
    coco_path = split_dir / "coco.json"
    if not coco_path.exists():
        return []

    with coco_path.open("r", encoding="utf-8") as fp:
        coco = json.load(fp)

    categories = {
        int(cat["id"]): TARGET_CLASS_MAP.get(str(cat.get("name", "")).strip().lower())
        for cat in coco.get("categories", [])
    }

    file_key = image_path.name
    image_id = None
    width = None
    height = None
    for image_info in coco.get("images", []):
        file_name = str(image_info.get("file_name", ""))
        if Path(file_name).name == file_key:
            image_id = int(image_info["id"])
            width = int(image_info.get("width", 0))
            height = int(image_info.get("height", 0))
            break

    if image_id is None:
        return []

    detections = []
    for ann in coco.get("annotations", []):
        if int(ann.get("image_id", -1)) != image_id:
            continue
        mapped_name = categories.get(int(ann.get("category_id", -1)))
        if mapped_name is None:
            continue
        x, y, w, h = ann["bbox"]
        x1 = int(round(float(x)))
        y1 = int(round(float(y)))
        x2 = int(round(float(x) + float(w)))
        y2 = int(round(float(y) + float(h)))
        if width is not None:
            x1 = max(0, min(x1, width - 1))
            x2 = max(0, min(x2, width - 1))
        if height is not None:
            y1 = max(0, min(y1, height - 1))
            y2 = max(0, min(y2, height - 1))
        detections.append(
            {
                "class_name": mapped_name,
                "bbox_xyxy": [x1, y1, x2, y2],
            }
        )
    return detections


def draw_detections(
    image_path: Path,
    detections: list[dict],
    output_path: Path,
    ground_truth: Optional[list[dict]] = None,
) -> None:
    image = Image.open(image_path).convert("RGB")
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.load_default()
    except Exception:  # pragma: no cover - fallback safe path
        font = None

    pred_colors = [
        (255, 80, 80),
        (80, 160, 255),
        (255, 200, 80),
        (240, 120, 255),
    ]
    gt_color = (80, 220, 120)

    if ground_truth:
        for gt in ground_truth:
            x1, y1, x2, y2 = gt["bbox_xyxy"]
            label = f"GT:{gt['class_name']}"
            draw.rectangle([x1, y1, x2, y2], outline=gt_color, width=2)
            if font is not None:
                left, top, right, bottom = draw.textbbox((x1, y1), label, font=font)
                text_w = right - left
                text_h = bottom - top
            else:
                text_w = max(8 * len(label), 40)
                text_h = 12
            text_x = x1
            text_y = max(0, y1 - text_h - 4)
            draw.rectangle([text_x, text_y, text_x + text_w + 4, text_y + text_h + 4], fill=gt_color)
            draw.text((text_x + 2, text_y + 2), label, fill=(0, 0, 0), font=font)

    for idx, det in enumerate(detections):
        color = pred_colors[idx % len(pred_colors)]
        x1, y1, x2, y2 = det["bbox_xyxy"]
        label = f"{det['class_name']} {det['score']:.3f}"
        draw.rectangle([x1, y1, x2, y2], outline=color, width=2)

        if font is not None:
            left, top, right, bottom = draw.textbbox((x1, y1), label, font=font)
            text_w = right - left
            text_h = bottom - top
        else:
            text_w = max(8 * len(label), 40)
            text_h = 12
        text_x = x1
        text_y = max(0, y1 - text_h - 4)
        draw.rectangle([text_x, text_y, text_x + text_w + 4, text_y + text_h + 4], fill=color)
        draw.text((text_x + 2, text_y + 2), label, fill=(0, 0, 0), font=font)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(output_path)


def build_remote_command(
    remote_dir: str,
    remote_gray8_path: str,
    src_width: int,
    src_height: int,
    runtime_width: int,
    runtime_height: int,
    score_thresh_x1000: int,
    iou_thresh_x1000: int,
    mean: float,
    stddev: float,
    input_scale: float,
) -> str:
    rel_gray8 = posixpath.relpath(remote_gray8_path, remote_dir)
    return (
        f"cd {remote_dir} && "
        f"chmod +x app/irdet_linux_ncnn_app lib/ld-linux-armhf.so.3 && "
        f"./lib/ld-linux-armhf.so.3 --library-path ./lib ./app/irdet_linux_ncnn_app "
        f"--param ./model/irdet_ssdlite_ir_runtime_fixed_v2.param "
        f"--bin ./model/irdet_ssdlite_ir_runtime_fixed_v2.bin "
        f"--anchors ./model/anchors_xyxy_f32.bin "
        f"--gray8 ./{rel_gray8} "
        f"--src-width {src_width} "
        f"--src-height {src_height} "
        f"--runtime-width {runtime_width} "
        f"--runtime-height {runtime_height} "
        f"--score-thresh-x1000 {score_thresh_x1000} "
        f"--iou-thresh-x1000 {iou_thresh_x1000} "
        f"--mean {mean} "
        f"--std {stddev} "
        f"--input-scale {input_scale}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Decode a local image, upload GRAY8 raw to AC880 Linux, and run board-side inference."
    )
    image_group = parser.add_mutually_exclusive_group(required=True)
    image_group.add_argument("--image", type=parse_path_arg, help="Path to one input image file.")
    image_group.add_argument(
        "--dataset-root",
        type=parse_path_arg,
        help="Root directory of a dataset such as FLIR_ADAS_v2. One image will be selected recursively.",
    )
    parser.add_argument("--index", type=int, default=0, help="Dataset index when --pick is first.")
    parser.add_argument(
        "--match",
        type=str,
        default=None,
        help="Optional case-insensitive substring filter used with --dataset-root.",
    )
    parser.add_argument(
        "--pick",
        choices=("first", "random"),
        default="first",
        help="Dataset selection mode when --dataset-root is used.",
    )
    parser.add_argument("--host", default="169.254.132.113", help="Board IPv4 address.")
    parser.add_argument("--port", type=int, default=22, help="SSH port.")
    parser.add_argument("--user", default="root", help="SSH username.")
    parser.add_argument("--password", default="root", help="SSH password.")
    parser.add_argument("--remote-dir", default="/home/root/irdet_demo", help="Remote demo bundle directory.")
    parser.add_argument(
        "--remote-name",
        default=None,
        help="Optional remote raw filename. Defaults to a sanitized local image stem with .bin suffix.",
    )
    parser.add_argument("--runtime-width", type=int, default=160, help="Board-side runtime tensor width.")
    parser.add_argument("--runtime-height", type=int, default=128, help="Board-side runtime tensor height.")
    parser.add_argument("--score-thresh-x1000", type=int, default=200, help="Detection score threshold x1000.")
    parser.add_argument("--iou-thresh-x1000", type=int, default=450, help="NMS IoU threshold x1000.")
    parser.add_argument("--mean", type=float, default=0.5, help="Input normalization mean.")
    parser.add_argument("--std", type=float, default=0.5, help="Input normalization stddev.")
    parser.add_argument(
        "--input-scale",
        type=float,
        default=1.0 / 255.0,
        help="Input scaling factor before mean/std normalization.",
    )
    parser.add_argument("--timeout", type=int, default=180, help="Remote command timeout in seconds.")
    parser.add_argument(
        "--result-json",
        type=parse_path_arg,
        default=None,
        help="Optional local path to save structured inference result JSON.",
    )
    parser.add_argument(
        "--annotated-out",
        type=parse_path_arg,
        default=None,
        help="Optional local path to save an annotated detection image.",
    )
    parser.add_argument(
        "--with-gt",
        action="store_true",
        help="When possible, overlay FLIR ground-truth boxes onto the annotated output.",
    )
    args = parser.parse_args()
    args.match = strip_wrapping_quotes(args.match)

    selected_image, dataset_meta = resolve_image_path(
        image_path=args.image,
        dataset_root=args.dataset_root,
        index=args.index,
        name_contains=args.match,
        pick_mode=args.pick,
    )
    width, height, payload = load_gray_payload(selected_image)
    checksum = checksum32(payload)

    if dataset_meta is not None:
        print(
            f"Selected dataset image index={dataset_meta['selected_index']} "
            f"out_of={dataset_meta['candidate_count']} pick={dataset_meta['pick_mode']}"
        )
        if dataset_meta["match"]:
            print(f"Applied dataset filter: {dataset_meta['match']}")

    print(
        f"Decoded image={selected_image} width={width} height={height} "
        f"payload={len(payload)} checksum=0x{checksum:08X}"
    )

    remote_name = args.remote_name or f"{sanitize_name(selected_image.stem)}.bin"
    remote_path = posixpath.join(args.remote_dir, "data", remote_name)

    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    print(f"Connecting to {args.host}:{args.port} as {args.user}...")
    ssh.connect(
        args.host,
        port=args.port,
        username=args.user,
        password=args.password,
        timeout=10,
        look_for_keys=False,
        allow_agent=False,
    )
    print("SSH connected.")

    sftp = ssh.open_sftp()
    upload_bytes(sftp, remote_path, payload)
    sftp.close()
    print(f"Uploaded GRAY8 payload to {remote_path}")

    remote_command = build_remote_command(
        remote_dir=args.remote_dir,
        remote_gray8_path=remote_path,
        src_width=width,
        src_height=height,
        runtime_width=args.runtime_width,
        runtime_height=args.runtime_height,
        score_thresh_x1000=args.score_thresh_x1000,
        iou_thresh_x1000=args.iou_thresh_x1000,
        mean=args.mean,
        stddev=args.std,
        input_scale=args.input_scale,
    )
    print("Running remote inference...")
    rc, out, err = run_command(ssh, remote_command, timeout=args.timeout)
    if out:
        print(out, end="")
    if err:
        print(err, end="", file=sys.stderr)
    ssh.close()
    if rc != 0:
        raise SystemExit(rc)

    parsed = parse_remote_output(out)
    ground_truth = load_flir_ground_truth_for_image(selected_image) if args.with_gt else []
    result = {
        "source_image": str(selected_image),
        "decoded_width": width,
        "decoded_height": height,
        "payload_bytes": len(payload),
        "checksum32": checksum,
        "remote_gray8_path": remote_path,
        "dataset_selection": dataset_meta,
        "ground_truth": ground_truth,
        "remote_inference": parsed,
    }
    if args.result_json is not None:
        args.result_json.parent.mkdir(parents=True, exist_ok=True)
        args.result_json.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"Saved result JSON to: {args.result_json}")

    if args.annotated_out is not None:
        draw_detections(selected_image, parsed["detections"], args.annotated_out, ground_truth=ground_truth)
        print(f"Saved annotated image to: {args.annotated_out}")

    print("REMOTE_IMAGE_INFER_DONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
