#!/usr/bin/env python3
"""Pack an ONNX model with external tensor data into a single ONNX file."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any


def require_onnx() -> Any:
    try:
        import onnx
    except ImportError as exc:  # pragma: no cover - runtime dependency
        raise RuntimeError("onnx is required to pack external tensor data.") from exc
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
    parser = argparse.ArgumentParser(description="Pack ONNX external tensor data into one file.")
    parser.add_argument("--input", type=Path, required=True, help="Input ONNX path.")
    parser.add_argument("--output", type=Path, required=True, help="Output packed ONNX path.")
    return parser.parse_args()


def main() -> int:
    configure_console_encoding()
    args = parse_args()
    onnx = require_onnx()

    model = onnx.load(str(args.input), load_external_data=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    onnx.save_model(
        model,
        str(args.output),
        save_as_external_data=False,
    )

    input_size = args.input.stat().st_size if args.input.exists() else 0
    output_size = args.output.stat().st_size
    print(f"Packed ONNX: {args.output}")
    print(f"input_main_bytes={input_size} output_bytes={output_size}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
