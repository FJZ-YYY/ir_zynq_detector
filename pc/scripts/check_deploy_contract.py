#!/usr/bin/env python3
"""Check model runtime metadata against the project deployment contract."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def configure_console_encoding() -> None:
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if stream is not None and hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except OSError:
                pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check runtime metadata against the deployment contract.")
    parser.add_argument(
        "--contract",
        type=Path,
        default=Path("configs/deploy_contract_ssdlite_ir_v1.json"),
        help="Deployment contract JSON.",
    )
    parser.add_argument("--runtime-metadata", type=Path, required=True, help="Runtime ONNX metadata JSON.")
    parser.add_argument(
        "--allow-legacy-current",
        action="store_true",
        help="Return success for the current checkpoint legacy transform-free export even if it differs from the future fixed contract.",
    )
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as fp:
        return json.load(fp)


def shape_text(shape: list[int]) -> str:
    return "x".join(str(int(v)) for v in shape)


def get_runtime_input(metadata: dict[str, Any]) -> dict[str, Any]:
    if "runtime_input_tensor" in metadata:
        return metadata["runtime_input_tensor"]
    if "input_tensor" in metadata:
        return metadata["input_tensor"]
    raise KeyError("Runtime metadata does not contain runtime_input_tensor or input_tensor.")


def main() -> int:
    configure_console_encoding()
    args = parse_args()
    contract = load_json(args.contract)
    metadata = load_json(args.runtime_metadata)

    expected_shape = [int(v) for v in contract["next_retrain_fixed_contract"]["input_shape"]]
    live_shape = [int(v) for v in contract["ps_preprocess_live_tensor"]["shape"]]
    runtime_input = get_runtime_input(metadata)
    runtime_shape = [int(v) for v in runtime_input["shape"]]
    runtime_status = metadata.get("contract_status", {})
    is_future_fixed = bool(runtime_status.get("is_future_fixed_contract", False))
    is_current_compatible = bool(runtime_status.get("is_current_checkpoint_compatible", False))

    classes_expected = [item["name"] for item in contract["classes"]["foreground"]]
    classes_runtime = list(metadata.get("classes", {}).get("foreground_names", []))
    classes_match = classes_expected == classes_runtime
    runtime_matches_live = runtime_shape == live_shape
    runtime_matches_future = runtime_shape == expected_shape and is_future_fixed

    print(f"Contract file: {args.contract}")
    print(f"Runtime metadata: {args.runtime_metadata}")
    print(f"Live PS preprocess shape: {shape_text(live_shape)}")
    print(f"Future fixed contract shape: {shape_text(expected_shape)}")
    print(f"Runtime input shape: {shape_text(runtime_shape)}")
    print(f"Classes expected: {classes_expected}")
    print(f"Classes runtime:  {classes_runtime}")

    if not classes_match:
        print("CONTRACT_FAIL: class list mismatch")
        return 1

    if runtime_matches_future and runtime_matches_live:
        print("CONTRACT_OK: runtime metadata matches the fixed deployment contract")
        return 0

    if is_current_compatible and args.allow_legacy_current:
        print("CONTRACT_LEGACY_OK: runtime metadata is compatible with the current checkpoint")
        if not runtime_matches_live:
            print(
                "CONTRACT_WARNING: runtime input shape differs from the live PS preprocess shape; "
                "do not use this as the next retraining contract"
            )
        if not is_future_fixed:
            print("CONTRACT_WARNING: metadata explicitly marks this export as not future-fixed")
        return 0

    print("CONTRACT_FAIL: runtime metadata does not match the fixed deployment contract")
    print("Hint: pass --allow-legacy-current only for the current checkpoint bridge export.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
