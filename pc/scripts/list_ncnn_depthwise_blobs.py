#!/usr/bin/env python3
"""List depthwise-convolution blob names from an ncnn .param file."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="List ConvolutionDepthWise blobs from an ncnn param file.")
    parser.add_argument(
        "--param",
        type=Path,
        default=Path("build/ncnn_runtime_fixed_v2_tracer_op13_ncnn/irdet_ssdlite_ir_runtime_fixed_v2.param"),
        help="Path to the ncnn .param file.",
    )
    parser.add_argument(
        "--match",
        type=str,
        default="",
        help="Optional case-insensitive substring filter applied to layer/input/output names.",
    )
    parser.add_argument(
        "--json-out",
        type=Path,
        default=None,
        help="Optional JSON output path.",
    )
    return parser.parse_args()


def parse_param_line(line: str, line_index: int) -> dict[str, object] | None:
    tokens = line.strip().split()
    if len(tokens) < 4 or tokens[0] != "ConvolutionDepthWise":
        return None

    bottom_count = int(tokens[2])
    top_count = int(tokens[3])
    cursor = 4
    bottoms = tokens[cursor : cursor + bottom_count]
    cursor += bottom_count
    tops = tokens[cursor : cursor + top_count]
    cursor += top_count
    params = tokens[cursor:]

    parsed_params: dict[str, str] = {}
    for item in params:
        if "=" not in item:
            continue
        key, value = item.split("=", 1)
        parsed_params[key] = value

    return {
        "line_index": line_index,
        "layer_type": tokens[0],
        "layer_name": tokens[1],
        "bottoms": bottoms,
        "tops": tops,
        "num_output": int(parsed_params.get("0", "0")),
        "kernel_w": int(parsed_params.get("1", "0")),
        "kernel_h": int(parsed_params.get("11", parsed_params.get("1", "0"))),
        "stride_w": int(parsed_params.get("3", "0")),
        "stride_h": int(parsed_params.get("13", parsed_params.get("3", "0"))),
        "pad_w": int(parsed_params.get("4", "0")),
        "pad_h": int(parsed_params.get("14", parsed_params.get("4", "0"))),
        "groups": int(parsed_params.get("7", "0")),
    }


def main() -> int:
    args = parse_args()
    lines = args.param.read_text(encoding="utf-8").splitlines()
    records: list[dict[str, object]] = []
    match_text = args.match.lower().strip()

    for line_index, line in enumerate(lines[2:], start=3):
        record = parse_param_line(line, line_index)
        if record is None:
            continue
        haystack = " ".join(
            [
                str(record["layer_name"]),
                " ".join(record["bottoms"]),
                " ".join(record["tops"]),
            ]
        ).lower()
        if match_text and match_text not in haystack:
            continue
        records.append(record)

    if args.json_out is not None:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(records, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"param={args.param}")
    print(f"depthwise_count={len(records)}")
    for idx, record in enumerate(records, start=1):
        bottom = record["bottoms"][0] if record["bottoms"] else "-"
        top = record["tops"][0] if record["tops"] else "-"
        print(
            f"[{idx}] line={record['line_index']} "
            f"layer={record['layer_name']} "
            f"in={bottom} out={top} "
            f"k={record['kernel_w']}x{record['kernel_h']} "
            f"s={record['stride_w']}x{record['stride_h']} "
            f"p={record['pad_w']}x{record['pad_h']} "
            f"groups={record['groups']} "
            f"num_output={record['num_output']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
