#!/usr/bin/env python3
"""Package a U-Boot-stage PL preload bundle for the AC880 board."""

from __future__ import annotations

import argparse
import json
import shutil
import struct
import time
import zlib
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BITSTREAM = REPO_ROOT / "build" / "vivado" / "ir_zynq_detector.runs" / "impl_1" / "system_wrapper.bit"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "build" / "ac880_uboot_pl_preload"

IH_MAGIC = 0x27051956
IH_OS_LINUX = 5
IH_ARCH_ARM = 2
IH_TYPE_SCRIPT = 6
IH_COMP_NONE = 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Package AC880 U-Boot-stage PL preload files.")
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--bitstream", type=Path, default=DEFAULT_BITSTREAM)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--script-name", type=str, default="irdet_pl_preload.scr")
    parser.add_argument("--command-name", type=str, default="irdet_pl_preload.cmd")
    parser.add_argument("--bitstream-name", type=str, default="system_wrapper.bit")
    return parser.parse_args()


def ensure_exists(path: Path, label: str) -> None:
    if not path.exists():
        raise FileNotFoundError(f"{label} not found: {path}")


def build_boot_cmd(bitstream_name: str) -> str:
    lines = [
        'echo "IR detector U-Boot PL preload"',
        'if test -z "${loadaddr}"; then setenv loadaddr 0x10000000; fi',
        'setenv irdet_pl_loaded 0',
        'setenv irdet_pl_source unknown',
        "",
        "for dev in 0 1; do",
        '  if mmc dev ${dev}; then',
        "    for part in 1 0; do",
        '      if test "${irdet_pl_loaded}" = "0"; then',
        f'        if fatload mmc ${{dev}}:${{part}} ${{loadaddr}} {bitstream_name}; then',
        '          echo "Loaded bitstream from FAT mmc ${dev}:${part}"',
        '          if fpga loadb 0 ${loadaddr} ${filesize}; then',
        '            setenv irdet_pl_loaded 1',
        '            setenv irdet_pl_source mmc:${dev}:${part}:fat',
        "          fi",
        "        fi",
        "      fi",
        '      if test "${irdet_pl_loaded}" = "0"; then',
        f'        if ext4load mmc ${{dev}}:${{part}} ${{loadaddr}} /{bitstream_name}; then',
        '          echo "Loaded bitstream from EXT4 mmc ${dev}:${part} path=/"',
        '          if fpga loadb 0 ${loadaddr} ${filesize}; then',
        '            setenv irdet_pl_loaded 1',
        '            setenv irdet_pl_source mmc:${dev}:${part}:ext4:/',
        "          fi",
        "        fi",
        "      fi",
        '      if test "${irdet_pl_loaded}" = "0"; then',
        f'        if ext4load mmc ${{dev}}:${{part}} ${{loadaddr}} /boot/{bitstream_name}; then',
        '          echo "Loaded bitstream from EXT4 mmc ${dev}:${part} path=/boot"',
        '          if fpga loadb 0 ${loadaddr} ${filesize}; then',
        '            setenv irdet_pl_loaded 1',
        '            setenv irdet_pl_source mmc:${dev}:${part}:ext4:/boot',
        "          fi",
        "        fi",
        "      fi",
        "    done",
        "  fi",
        "done",
        "",
        'if test "${irdet_pl_loaded}" = "1"; then',
        '  echo "PL preload done source=${irdet_pl_source}"',
        "else",
        '  echo "WARNING: PL preload bundle did not find the bitstream; continuing normal boot"',
        "fi",
        "",
        'echo "Running existing bootcmd..."',
        "run bootcmd",
        "",
    ]
    return "\n".join(lines)


def build_legacy_script_image(payload: bytes, image_name: str) -> bytes:
    name_bytes = image_name.encode("ascii", errors="ignore")[:32].ljust(32, b"\x00")
    timestamp = int(time.time())
    data_crc = zlib.crc32(payload) & 0xFFFFFFFF
    header = struct.pack(
        ">7I4B32s",
        IH_MAGIC,
        0,
        timestamp,
        len(payload),
        0,
        0,
        data_crc,
        IH_OS_LINUX,
        IH_ARCH_ARM,
        IH_TYPE_SCRIPT,
        IH_COMP_NONE,
        name_bytes,
    )
    header_crc = zlib.crc32(header) & 0xFFFFFFFF
    header = struct.pack(
        ">7I4B32s",
        IH_MAGIC,
        header_crc,
        timestamp,
        len(payload),
        0,
        0,
        data_crc,
        IH_OS_LINUX,
        IH_ARCH_ARM,
        IH_TYPE_SCRIPT,
        IH_COMP_NONE,
        name_bytes,
    )
    return header + payload


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.replace("\r\n", "\n"), encoding="ascii", newline="\n")


def main() -> int:
    args = parse_args()
    ensure_exists(args.bitstream, "Bitstream")

    output_dir = args.output_dir
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    command_text = build_boot_cmd(args.bitstream_name)
    command_path = output_dir / args.command_name
    script_path = output_dir / args.script_name
    readme_path = output_dir / "README.txt"
    manifest_path = output_dir / "bundle_manifest.json"
    source_cmd_path = output_dir / "source_from_uboot.txt"
    bitstream_out = output_dir / args.bitstream_name

    write_text(command_path, command_text)
    script_payload = command_text.encode("ascii")
    script_image = build_legacy_script_image(script_payload, "IRDET PL preload")
    script_path.write_bytes(script_image)
    shutil.copy2(args.bitstream, bitstream_out)

    source_cmd = "\n".join(
        [
            "Stop autoboot at the U-Boot countdown, then try one of these:",
            "",
            f"fatload mmc 0:1 ${{loadaddr}} {args.script_name}; source ${{loadaddr}}",
            f"fatload mmc 1:1 ${{loadaddr}} {args.script_name}; source ${{loadaddr}}",
            "",
            "If your media uses ext4, try:",
            f"ext4load mmc 0:1 ${{loadaddr}} /{args.script_name}; source ${{loadaddr}}",
            f"ext4load mmc 1:1 ${{loadaddr}} /{args.script_name}; source ${{loadaddr}}",
            "",
            "The script itself will search mmc 0/1 and FAT/ext4 for system_wrapper.bit,",
            "program the PL, then continue with the existing bootcmd.",
            "",
        ]
    )
    write_text(source_cmd_path, source_cmd)

    readme = "\n".join(
        [
            "AC880 U-Boot-stage PL preload bundle",
            "",
            "Files:",
            f"- {args.bitstream_name}: Vivado-generated PL bitstream",
            f"- {args.command_name}: plain-text U-Boot command script",
            f"- {args.script_name}: legacy U-Boot script image (boot.scr-style)",
            "- source_from_uboot.txt: commands to run at the U-Boot prompt",
            "",
            "Recommended use:",
            "1. Copy this directory onto an SD card or another boot-visible storage device.",
            "2. Place the files at the root of the first FAT partition if possible.",
            "3. Power on the board and stop U-Boot autoboot over the PS UART.",
            "4. Run one of the commands from source_from_uboot.txt.",
            "5. The script will program PL first, then resume the board's existing bootcmd.",
            "",
            "Why this exists:",
            "- It moves PL programming earlier than Linux user-space JTAG hot-loading.",
            "- It avoids the current Linux-runtime OCM interrupt spam seen after hot-reconfiguring PL.",
            "- It lets us validate 'PL already present before Linux detector app starts' without rebuilding eMMC yet.",
            "",
        ]
    )
    write_text(readme_path, readme)

    manifest = {
        "bundle": "ac880_uboot_pl_preload",
        "bitstream": args.bitstream_name,
        "bitstream_bytes": bitstream_out.stat().st_size,
        "boot_command": args.command_name,
        "boot_script": args.script_name,
        "source_helper": source_cmd_path.name,
        "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "notes": [
            "Generated without external mkimage dependency.",
            "boot script format is legacy U-Boot script image.",
            "Script searches mmc 0/1 and FAT/ext4 paths for the bitstream.",
        ],
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    print(f"Packaged U-Boot PL preload bundle: {output_dir}")
    print(f"Bitstream: {bitstream_out}")
    print(f"U-Boot command file: {command_path}")
    print(f"U-Boot script image: {script_path}")
    print(f"Source helper: {source_cmd_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
