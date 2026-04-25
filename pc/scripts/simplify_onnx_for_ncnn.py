#!/usr/bin/env python3
"""Apply small ONNX graph cleanups for ncnn's legacy onnx2ncnn converter."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any


def require_onnx() -> Any:
    try:
        import onnx
    except ImportError as exc:  # pragma: no cover - runtime dependency
        raise RuntimeError("onnx is required for graph cleanup.") from exc
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
    parser = argparse.ArgumentParser(description="Simplify ONNX graph for ncnn conversion.")
    parser.add_argument("--input", type=Path, required=True, help="Input ONNX path.")
    parser.add_argument("--output", type=Path, required=True, help="Output ONNX path.")
    parser.add_argument("--check", action="store_true", help="Run onnx.checker after cleanup.")
    return parser.parse_args()


def remove_identity_nodes(model: Any) -> int:
    graph = model.graph
    replacements: dict[str, str] = {}
    kept_nodes = []
    removed = 0

    for node in graph.node:
        if node.op_type == "Identity" and len(node.input) == 1 and len(node.output) == 1:
            replacements[node.output[0]] = node.input[0]
            removed += 1
            continue
        kept_nodes.append(node)

    def resolve(name: str) -> str:
        while name in replacements:
            name = replacements[name]
        return name

    for node in kept_nodes:
        for idx, name in enumerate(node.input):
            node.input[idx] = resolve(name)

    for output in graph.output:
        output.name = resolve(output.name)

    del graph.node[:]
    graph.node.extend(kept_nodes)
    return removed


def main() -> int:
    configure_console_encoding()
    args = parse_args()
    onnx = require_onnx()

    model = onnx.load(str(args.input), load_external_data=True)
    removed_identity = remove_identity_nodes(model)
    if args.check:
        onnx.checker.check_model(model)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    onnx.save_model(model, str(args.output), save_as_external_data=False)
    print(f"Simplified ONNX: {args.output}")
    print(f"removed_identity={removed_identity}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
