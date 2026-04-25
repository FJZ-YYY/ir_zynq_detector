#!/usr/bin/env python3
"""Inspect an ONNX model's basic IO shapes and operator inventory."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any


def require_onnx() -> Any:
    try:
        import onnx
    except ImportError as exc:  # pragma: no cover - runtime dependency
        raise RuntimeError("onnx is required for model inspection.") from exc
    return onnx


def configure_console_encoding() -> None:
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if stream is not None and hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except OSError:
                pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Inspect ONNX model IO shapes and operator counts.")
    parser.add_argument("--onnx", type=Path, required=True, help="ONNX model path.")
    parser.add_argument("--output", type=Path, default=None, help="Optional JSON report path.")
    parser.add_argument(
        "--load-external-data",
        action="store_true",
        help="Load external tensor data. Not needed for operator inventory.",
    )
    return parser.parse_args()


def tensor_shape(value_info: Any) -> list[int | str]:
    dims: list[int | str] = []
    for dim in value_info.type.tensor_type.shape.dim:
        if dim.dim_value:
            dims.append(int(dim.dim_value))
        elif dim.dim_param:
            dims.append(str(dim.dim_param))
        else:
            dims.append("?")
    return dims


def main() -> int:
    configure_console_encoding()
    args = parse_args()
    onnx = require_onnx()

    model = onnx.load(str(args.onnx), load_external_data=bool(args.load_external_data))
    ops = Counter(node.op_type for node in model.graph.node)
    report = {
        "format": "ir_onnx_inspect_v1",
        "onnx": str(args.onnx),
        "num_nodes": len(model.graph.node),
        "op_counts": dict(sorted(ops.items())),
        "inputs": [
            {
                "name": item.name,
                "shape": tensor_shape(item),
            }
            for item in model.graph.input
        ],
        "outputs": [
            {
                "name": item.name,
                "shape": tensor_shape(item),
            }
            for item in model.graph.output
        ],
    }

    print(f"ONNX: {args.onnx}")
    print(f"nodes={report['num_nodes']}")
    print("inputs:")
    for item in report["inputs"]:
        print(f"  {item['name']} shape={item['shape']}")
    print("outputs:")
    for item in report["outputs"]:
        print(f"  {item['name']} shape={item['shape']}")
    print("ops:")
    for op, count in report["op_counts"].items():
        print(f"  {op}: {count}")

    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("w", encoding="utf-8") as fp:
            json.dump(report, fp, indent=2, ensure_ascii=False)
            fp.write("\n")
        print(f"Report: {args.output}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
