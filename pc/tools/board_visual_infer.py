#!/usr/bin/env python3
"""PC-side board inference helper for AC880 visual demos."""

from __future__ import annotations

import argparse
import json
import posixpath
import random
import re
import shlex
import socket
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

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
DEFAULT_BOARD_HOST_CANDIDATES = ("169.254.132.113", "192.168.0.233", "192.168.0.2")
SUPPORTED_MODES = ("gray8", "inpath_dw_cpu_full", "inpath_dw_pl_full")
MODE_TO_EXTRA_ARGS = {
    "gray8": (),
    "inpath_dw_cpu_full": ("--inpath-dw-cpu-full-dir", "./data/pl_real_layer_case"),
    "inpath_dw_pl_full": ("--inpath-dw-pl-full-dir", "./data/pl_real_layer_case"),
}
TARGET_CLASS_MAP = {
    "person": "person",
    "bike": "bicycle",
    "bicycle": "bicycle",
    "car": "car",
}


def repo_root_from_script() -> Path:
    return Path(__file__).resolve().parents[2]


def emit(log_callback: Optional[Callable[[str], None]], message: str) -> None:
    if log_callback is not None:
        log_callback(message)


def run_powershell_file(
    script_path: Path,
    script_args: list[str],
    *,
    description: str,
    log_callback: Optional[Callable[[str], None]],
) -> None:
    if not script_path.exists():
        raise FileNotFoundError(f"Script not found: {script_path}")

    cmd = [
        "powershell",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(script_path),
        *script_args,
    ]
    emit(log_callback, description)
    completed = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if completed.stdout:
        emit(log_callback, completed.stdout.rstrip())
    if completed.stderr:
        emit(log_callback, completed.stderr.rstrip())
    if completed.returncode != 0:
        raise RuntimeError(f"{script_path.name} failed with exit code {completed.returncode}")


def recover_board_pl(repo_root: Path, log_callback: Optional[Callable[[str], None]] = None) -> None:
    script_path = repo_root / "pc" / "scripts" / "program_ac880_pl_only.ps1"
    run_powershell_file(
        script_path,
        ["-RepoRoot", str(repo_root)],
        description="Recovering AC880 PL by programming the current local bitstream over JTAG...",
        log_callback=log_callback,
    )


def strip_wrapping_quotes(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        return value[1:-1]
    return value


def parse_path_arg(value: str) -> Path:
    return Path(strip_wrapping_quotes(value))


def parse_host_candidates_arg(value: str) -> tuple[str, ...]:
    text = strip_wrapping_quotes(value) or ""
    if not text.strip():
        return DEFAULT_BOARD_HOST_CANDIDATES
    return tuple(item.strip() for item in text.split(",") if item.strip())


def is_image_file(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS


def collect_dataset_images(dataset_root: Path) -> list[Path]:
    return sorted(path for path in dataset_root.rglob("*") if is_image_file(path))


def filter_images(images: list[Path], name_contains: Optional[str]) -> list[Path]:
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

    images = filter_images(collect_dataset_images(dataset_root), name_contains)
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
    return width, height, image.tobytes()


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


def probe_tcp_port(host_name: str, port: int, timeout_s: float = 1.5) -> bool:
    try:
        with socket.create_connection((host_name, port), timeout=timeout_s):
            return True
    except OSError:
        return False


def resolve_board_host(
    requested_host: str,
    candidates: tuple[str, ...],
    port: int,
    wait_seconds: int = 0,
    log_callback: Optional[Callable[[str], None]] = None,
) -> str:
    deadline = time.monotonic() + max(0, wait_seconds)
    wait_logged = False
    last_error = ""

    while True:
        if requested_host and requested_host.lower() != "auto":
            if probe_tcp_port(requested_host, port):
                return requested_host
            last_error = f"Unable to reach requested AC880 host {requested_host}:{port}"
        else:
            for candidate in candidates:
                if probe_tcp_port(candidate, port):
                    return candidate
            last_error = f"Unable to reach AC880 Linux on any candidate hosts: {', '.join(candidates)}"

        if time.monotonic() >= deadline:
            raise ConnectionError(last_error)
        if not wait_logged:
            emit(log_callback, f"Waiting for AC880 Linux SSH to come up on port {port} ...")
            wait_logged = True
        time.sleep(1.0)


def parse_numeric_value(raw_value: str):
    value = raw_value.strip()
    if re.fullmatch(r"-?\d+", value):
        return int(value)
    if re.fullmatch(r"-?\d+\.\d+", value):
        return float(value)
    return value


def parse_remote_output(output_text: str) -> dict:
    result = {
        "model": {},
        "runtime_contract": {},
        "preprocess": {},
        "metrics": {},
        "mode_status": {},
        "det_count": 0,
        "detections": [],
        "raw_output": output_text,
    }

    det_re = re.compile(
        r"^det(?P<index>\d+)\s+class=(?P<class_name>\S+)\s+score=(?P<score>[0-9.]+)\s+bbox=\[(?P<x1>-?\d+),(?P<y1>-?\d+),(?P<x2>-?\d+),(?P<y2>-?\d+)\]$"
    )
    count_re = re.compile(r"^det_count=(?P<count>\d+)$")
    model_re = re.compile(
        r"^Model backend=(?P<backend>\S+)\s+runtime_in=(?P<runtime_w>\d+)x(?P<runtime_h>\d+)\s+anchors=(?P<anchors>\d+)\s+score_thresh=(?P<score_thresh>\d+)\s+mean=(?P<mean>-?[0-9.]+)\s+std=(?P<std>-?[0-9.]+)$"
    )
    runtime_contract_re = re.compile(
        r"^Runtime contract nchw=1x1x(?P<h>\d+)x(?P<w>\d+)\s+width=(?P<width>\d+)\s+height=(?P<height>\d+)$"
    )
    preprocess_re = re.compile(
        r"^pre_in=(?P<src_w>\d+)x(?P<src_h>\d+)\s+pre_out=(?P<dst_w>\d+)x(?P<dst_h>\d+)\s+min=(?P<min>\d+)\s+max=(?P<max>\d+)\s+mean_x1000=(?P<mean_x1000>-?\d+)$"
    )
    mode_status_re = re.compile(r"^(?P<mode>[A-Za-z0-9_]+)\s+rc=(?P<rc>-?\d+)$")
    metric_re = re.compile(r"^(?P<key>[A-Za-z_][A-Za-z0-9_]*)=(?P<value>.+)$")

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

        match = runtime_contract_re.match(line)
        if match:
            result["runtime_contract"] = {
                "nchw": [1, 1, int(match.group("h")), int(match.group("w"))],
                "width": int(match.group("width")),
                "height": int(match.group("height")),
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
            continue

        match = mode_status_re.match(line)
        if match:
            result["mode_status"] = {
                "mode": match.group("mode"),
                "rc": int(match.group("rc")),
            }
            continue

        match = metric_re.match(line)
        if match and not line.startswith("full_ref "):
            key = match.group("key")
            if key not in ("det_count",):
                result["metrics"][key] = parse_numeric_value(match.group("value"))

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
    mode: str,
    runtime_width: int,
    runtime_height: int,
    score_thresh_x1000: int,
    iou_thresh_x1000: int,
    mean: float,
    stddev: float,
    input_scale: float,
) -> str:
    if mode not in MODE_TO_EXTRA_ARGS:
        raise ValueError(f"Unsupported mode: {mode}")

    rel_gray8 = posixpath.relpath(remote_gray8_path, remote_dir)
    command_parts = [
        "./lib/ld-linux-armhf.so.3",
        "--library-path",
        "./lib",
        "./app/irdet_linux_ncnn_app",
        "--param",
        "./model/irdet_ssdlite_ir_runtime_fixed_v2.param",
        "--bin",
        "./model/irdet_ssdlite_ir_runtime_fixed_v2.bin",
        "--anchors",
        "./model/anchors_xyxy_f32.bin",
        "--gray8",
        f"./{rel_gray8}",
        "--src-width",
        str(src_width),
        "--src-height",
        str(src_height),
        "--runtime-width",
        str(runtime_width),
        "--runtime-height",
        str(runtime_height),
        "--score-thresh-x1000",
        str(score_thresh_x1000),
        "--iou-thresh-x1000",
        str(iou_thresh_x1000),
        "--mean",
        str(mean),
        "--std",
        str(stddev),
        "--input-scale",
        str(input_scale),
    ]
    command_parts.extend(MODE_TO_EXTRA_ARGS[mode])

    command_text = " ".join(shlex.quote(item) for item in command_parts)
    return (
        f"cd {shlex.quote(remote_dir)} && "
        "chmod +x app/irdet_linux_ncnn_app lib/ld-linux-armhf.so.3 || true && "
        f"{command_text}"
    )


def refresh_remote_bundle(
    repo_root: Path,
    board_host: str,
    port: int,
    user: str,
    password: str,
    remote_dir: str,
    skip_package: bool,
    log_callback: Optional[Callable[[str], None]],
) -> None:
    deploy_script = repo_root / "pc" / "scripts" / "run_ac880_linux_demo.ps1"
    if not deploy_script.exists():
        raise FileNotFoundError(f"Script not found: {deploy_script}")

    cmd = [
        "powershell",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(deploy_script),
        "-RepoRoot",
        str(repo_root),
        "-BoardHost",
        board_host,
        "-Port",
        str(port),
        "-User",
        user,
        "-Password",
        password,
        "-RemoteDir",
        remote_dir,
        "-Mode",
        "none",
    ]
    if skip_package:
        cmd.append("-SkipPackage")

    run_powershell_file(
        deploy_script,
        cmd[5:],
        description="Refreshing remote AC880 bundle...",
        log_callback=log_callback,
    )


def build_output_paths(
    output_dir: Path,
    image_path: Path,
    mode: str,
    annotated_out: Optional[Path],
    result_json: Optional[Path],
    log_out: Optional[Path],
) -> dict[str, Path]:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_name = f"{sanitize_name(image_path.stem)}_{mode}_{timestamp}"
    output_dir.mkdir(parents=True, exist_ok=True)
    return {
        "annotated_out": annotated_out or (output_dir / f"{base_name}.png"),
        "result_json": result_json or (output_dir / f"{base_name}.json"),
        "log_out": log_out or (output_dir / f"{base_name}.log"),
    }


def run_board_visual_inference(
    *,
    image: Optional[Path] = None,
    dataset_root: Optional[Path] = None,
    match: Optional[str] = None,
    index: int = 0,
    pick: str = "first",
    mode: str = "inpath_dw_pl_full",
    repo_root: Optional[Path] = None,
    host: str = "auto",
    host_candidates: tuple[str, ...] = DEFAULT_BOARD_HOST_CANDIDATES,
    host_wait_seconds: int = 20,
    port: int = 22,
    user: str = "root",
    password: str = "root",
    remote_dir: str = "/home/root/irdet_demo",
    remote_name: Optional[str] = None,
    runtime_width: int = 160,
    runtime_height: int = 128,
    score_thresh_x1000: int = 200,
    iou_thresh_x1000: int = 450,
    mean: float = 0.5,
    stddev: float = 0.5,
    input_scale: float = 1.0 / 255.0,
    timeout: int = 180,
    output_dir: Optional[Path] = None,
    result_json: Optional[Path] = None,
    annotated_out: Optional[Path] = None,
    log_out: Optional[Path] = None,
    with_gt: bool = False,
    recover_pl_first: bool = False,
    refresh_bundle_first: bool = False,
    refresh_bundle_skip_package: bool = False,
    log_callback: Optional[Callable[[str], None]] = None,
) -> dict:
    if mode not in SUPPORTED_MODES:
        raise ValueError(f"Unsupported mode: {mode}")

    repo_root = repo_root or repo_root_from_script()
    output_dir = output_dir or (repo_root / "outputs" / "board_vis")
    match = strip_wrapping_quotes(match)
    image_path, dataset_meta = resolve_image_path(
        image_path=image,
        dataset_root=dataset_root,
        index=index,
        name_contains=match,
        pick_mode=pick,
    )
    output_paths = build_output_paths(
        output_dir=output_dir,
        image_path=image_path,
        mode=mode,
        annotated_out=annotated_out,
        result_json=result_json,
        log_out=log_out,
    )

    width, height, payload = load_gray_payload(image_path)
    checksum = checksum32(payload)

    if recover_pl_first:
        recover_board_pl(repo_root=repo_root, log_callback=log_callback)

    resolved_host = resolve_board_host(
        host,
        host_candidates,
        port,
        wait_seconds=host_wait_seconds,
        log_callback=log_callback,
    )

    if dataset_meta is not None:
        emit(
            log_callback,
            f"Selected dataset image index={dataset_meta['selected_index']} out_of={dataset_meta['candidate_count']} pick={dataset_meta['pick_mode']}",
        )
        if dataset_meta["match"]:
            emit(log_callback, f"Applied dataset filter: {dataset_meta['match']}")

    emit(
        log_callback,
        f"Decoded image={image_path} width={width} height={height} payload={len(payload)} checksum=0x{checksum:08X}",
    )
    emit(log_callback, f"Resolved AC880 host: {resolved_host}")

    if refresh_bundle_first:
        refresh_remote_bundle(
            repo_root=repo_root,
            board_host=resolved_host,
            port=port,
            user=user,
            password=password,
            remote_dir=remote_dir,
            skip_package=refresh_bundle_skip_package,
            log_callback=log_callback,
        )

    remote_basename = remote_name or f"{sanitize_name(image_path.stem)}_{mode}.bin"
    remote_path = posixpath.join(remote_dir, "data", "board_vis", remote_basename)
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    emit(log_callback, f"Connecting to {resolved_host}:{port} as {user}...")
    ssh.connect(
        resolved_host,
        port=port,
        username=user,
        password=password,
        timeout=10,
        look_for_keys=False,
        allow_agent=False,
    )
    emit(log_callback, "SSH connected.")

    stdout_text = ""
    stderr_text = ""
    rc = 0
    try:
        sftp = ssh.open_sftp()
        upload_bytes(sftp, remote_path, payload)
        sftp.close()
        emit(log_callback, f"Uploaded GRAY8 payload to {remote_path}")

        remote_command = build_remote_command(
            remote_dir=remote_dir,
            remote_gray8_path=remote_path,
            src_width=width,
            src_height=height,
            mode=mode,
            runtime_width=runtime_width,
            runtime_height=runtime_height,
            score_thresh_x1000=score_thresh_x1000,
            iou_thresh_x1000=iou_thresh_x1000,
            mean=mean,
            stddev=stddev,
            input_scale=input_scale,
        )
        emit(log_callback, f"Running remote inference mode={mode}...")
        rc, stdout_text, stderr_text = run_command(ssh, remote_command, timeout=timeout)
    finally:
        ssh.close()

    combined_log_lines = [
        f"[board] host={resolved_host} mode={mode}",
        f"[board] image={image_path}",
        f"[board] remote_gray8={remote_path}",
        "[stdout]",
        stdout_text.rstrip(),
        "[stderr]",
        stderr_text.rstrip(),
        f"[exit_code] {rc}",
        "",
    ]
    output_paths["log_out"].parent.mkdir(parents=True, exist_ok=True)
    output_paths["log_out"].write_text("\n".join(combined_log_lines), encoding="utf-8")

    if stdout_text:
        emit(log_callback, stdout_text.rstrip())
    if stderr_text:
        emit(log_callback, stderr_text.rstrip())
    emit(log_callback, f"Saved board log to: {output_paths['log_out']}")

    parsed = parse_remote_output(stdout_text)
    ground_truth = load_flir_ground_truth_for_image(image_path) if with_gt else []

    result = {
        "success": rc == 0,
        "exit_code": rc,
        "mode": mode,
        "source_image": str(image_path),
        "decoded_width": width,
        "decoded_height": height,
        "payload_bytes": len(payload),
        "checksum32": checksum,
        "board_host": resolved_host,
        "remote_dir": remote_dir,
        "remote_gray8_path": remote_path,
        "dataset_selection": dataset_meta,
        "ground_truth": ground_truth,
        "recover_pl_first": recover_pl_first,
        "remote_inference": parsed,
        "artifacts": {
            "annotated_out": str(output_paths["annotated_out"]),
            "result_json": str(output_paths["result_json"]),
            "log_out": str(output_paths["log_out"]),
        },
    }

    output_paths["result_json"].parent.mkdir(parents=True, exist_ok=True)
    output_paths["result_json"].write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    emit(log_callback, f"Saved result JSON to: {output_paths['result_json']}")

    if rc != 0:
        raise RuntimeError(f"Board inference failed with exit code {rc}. See log: {output_paths['log_out']}")

    draw_detections(
        image_path=image_path,
        detections=parsed["detections"],
        output_path=output_paths["annotated_out"],
        ground_truth=ground_truth,
    )
    emit(log_callback, f"Saved annotated image to: {output_paths['annotated_out']}")
    emit(log_callback, "BOARD_VISUAL_INFER_DONE")
    return result


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Select a PC image, run AC880 board inference, and save an annotated result image."
    )
    image_group = parser.add_mutually_exclusive_group(required=True)
    image_group.add_argument("--image", type=parse_path_arg, help="Path to one input image file.")
    image_group.add_argument(
        "--dataset-root",
        type=parse_path_arg,
        help="Root directory of a dataset such as FLIR_ADAS_v2. One image will be selected recursively.",
    )
    parser.add_argument("--index", type=int, default=0, help="Dataset index when --pick is first.")
    parser.add_argument("--match", type=str, default=None, help="Optional case-insensitive substring dataset filter.")
    parser.add_argument("--pick", choices=("first", "random"), default="first", help="Dataset selection mode.")
    parser.add_argument("--mode", choices=SUPPORTED_MODES, default="inpath_dw_pl_full", help="Board inference mode.")
    parser.add_argument("--repo-root", type=parse_path_arg, default=repo_root_from_script(), help="Repository root.")
    parser.add_argument("--host", default="auto", help="Board IPv4 address or auto.")
    parser.add_argument(
        "--host-candidates",
        type=parse_host_candidates_arg,
        default=DEFAULT_BOARD_HOST_CANDIDATES,
        help="Comma-separated candidate host list used when --host auto.",
    )
    parser.add_argument("--port", type=int, default=22, help="SSH port.")
    parser.add_argument(
        "--host-wait-seconds",
        type=int,
        default=20,
        help="How long to wait for the board SSH port after power-up or recovery.",
    )
    parser.add_argument("--user", default="root", help="SSH username.")
    parser.add_argument("--password", default="root", help="SSH password.")
    parser.add_argument("--remote-dir", default="/home/root/irdet_demo", help="Remote demo bundle directory.")
    parser.add_argument("--remote-name", default=None, help="Optional remote GRAY8 filename.")
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
        "--out-dir",
        type=parse_path_arg,
        default=repo_root_from_script() / "outputs" / "board_vis",
        help="Directory used for default output artifacts.",
    )
    parser.add_argument("--result-json", type=parse_path_arg, default=None, help="Optional result JSON path.")
    parser.add_argument("--annotated-out", type=parse_path_arg, default=None, help="Optional annotated image path.")
    parser.add_argument("--log-out", type=parse_path_arg, default=None, help="Optional board log path.")
    parser.add_argument("--with-gt", action="store_true", help="Overlay FLIR ground-truth boxes when available.")
    parser.add_argument(
        "--recover-pl",
        action="store_true",
        help="Program the current local PL bitstream over JTAG before inference.",
    )
    parser.add_argument(
        "--refresh-bundle",
        action="store_true",
        help="Refresh the remote AC880 demo bundle before image inference.",
    )
    parser.add_argument(
        "--refresh-bundle-skip-package",
        action="store_true",
        help="Reuse the existing local bundle when --refresh-bundle is enabled.",
    )
    return parser


def main() -> int:
    parser = build_arg_parser()
    args = parser.parse_args()

    def log_to_stdout(message: str) -> None:
        print(message)

    try:
        result = run_board_visual_inference(
            image=args.image,
            dataset_root=args.dataset_root,
            match=args.match,
            index=args.index,
            pick=args.pick,
            mode=args.mode,
            repo_root=args.repo_root,
            host=args.host,
            host_candidates=args.host_candidates,
            host_wait_seconds=args.host_wait_seconds,
            port=args.port,
            user=args.user,
            password=args.password,
            remote_dir=args.remote_dir,
            remote_name=args.remote_name,
            runtime_width=args.runtime_width,
            runtime_height=args.runtime_height,
            score_thresh_x1000=args.score_thresh_x1000,
            iou_thresh_x1000=args.iou_thresh_x1000,
            mean=args.mean,
            stddev=args.std,
            input_scale=args.input_scale,
            timeout=args.timeout,
            output_dir=args.out_dir,
            result_json=args.result_json,
            annotated_out=args.annotated_out,
            log_out=args.log_out,
            with_gt=args.with_gt,
            recover_pl_first=args.recover_pl,
            refresh_bundle_first=args.refresh_bundle,
            refresh_bundle_skip_package=args.refresh_bundle_skip_package,
            log_callback=log_to_stdout,
        )
    except Exception as exc:
        print(f"board_visual_infer failed: {exc}", file=sys.stderr)
        return 1

    print(f"det_count={result['remote_inference']['det_count']}")
    for det in result["remote_inference"]["detections"]:
        x1, y1, x2, y2 = det["bbox_xyxy"]
        print(
            f"det{det['index']} class={det['class_name']} score={det['score']:.3f} bbox=[{x1},{y1},{x2},{y2}]"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
