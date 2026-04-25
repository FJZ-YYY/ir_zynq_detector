#!/usr/bin/env python3
"""Create a minimal AC880 boot DTB compatible with the IR detector PL design."""

from __future__ import annotations

import argparse
from pathlib import Path

from pyfdt.pyfdt import FdtBlobParse


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT = REPO_ROOT / "build" / "ac880_uboot_pl_preload" / "factory_system.dtb"
DEFAULT_OUTPUT = REPO_ROOT / "build" / "ac880_uboot_pl_preload" / "system_ir_boot.dtb"
DEFAULT_DTS_OUT = REPO_ROOT / "build" / "ac880_uboot_pl_preload" / "system_ir_boot.dts"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a stripped AC880 DTB for the IR detector PL design.")
    parser.add_argument("--input-dtb", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-dtb", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--output-dts", type=Path, default=DEFAULT_DTS_OUT)
    return parser.parse_args()


def remove_node(fdt, path: str) -> bool:
    try:
        node = fdt.resolve_path(path)
    except Exception:
        return False
    parent = node.get_parent_node()
    if parent is None:
        return False
    parent.remove(node.get_name())
    return True


def remove_aliases(fdt, names: list[str]) -> int:
    removed = 0
    try:
      aliases = fdt.resolve_path("/aliases")
    except Exception:
      return removed

    for item in list(aliases):
        item_name = getattr(item, "name", "")
        if item_name in names:
            aliases.remove(item_name)
            removed += 1
    return removed


def main() -> int:
    args = parse_args()
    if not args.input_dtb.exists():
        raise FileNotFoundError(f"Input DTB not found: {args.input_dtb}")

    parser = FdtBlobParse(args.input_dtb.open("rb"))
    fdt = parser.to_fdt()

    removed_pl = remove_node(fdt, "/amba_pl")
    removed_alias_count = remove_aliases(fdt, ["i2c0", "i2c1", "i2c2"])

    args.output_dtb.parent.mkdir(parents=True, exist_ok=True)
    args.output_dtb.write_bytes(fdt.to_dtb())
    args.output_dts.write_text(fdt.to_dts(), encoding="utf-8")

    print(f"Input DTB: {args.input_dtb}")
    print(f"Output DTB: {args.output_dtb}")
    print(f"Output DTS: {args.output_dts}")
    print(f"Removed /amba_pl: {removed_pl}")
    print(f"Removed aliases: {removed_alias_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
