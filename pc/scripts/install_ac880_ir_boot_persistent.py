#!/usr/bin/env python3
"""Prepare and optionally install a persistent AC880 boot configuration for the IR detector."""

from __future__ import annotations

import argparse
import ftplib
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BOOT_DIR = "/run/media/mmcblk0p1"
DEFAULT_BITSTREAM = REPO_ROOT / "build" / "vivado" / "ir_zynq_detector.runs" / "impl_1" / "system_wrapper.bit"
DEFAULT_DTB = REPO_ROOT / "build" / "ac880_uboot_pl_preload" / "system_ir_boot.dtb"
DEFAULT_BACKUP_DIR = REPO_ROOT / "build" / "ac880_uboot_pl_preload" / "boot_partition_backup"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Install a persistent AC880 IR-detector boot configuration.")
    parser.add_argument("--host", default="169.254.132.113")
    parser.add_argument("--user", default="root")
    parser.add_argument("--password", default="root")
    parser.add_argument("--boot-dir", default=DEFAULT_BOOT_DIR)
    parser.add_argument("--bitstream", type=Path, default=DEFAULT_BITSTREAM)
    parser.add_argument("--dtb", type=Path, default=DEFAULT_DTB)
    parser.add_argument("--bitstream-name", default="system_wrapper.bit")
    parser.add_argument("--dtb-name", default="system_ir_boot.dtb")
    parser.add_argument("--backup-dir", type=Path, default=DEFAULT_BACKUP_DIR)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def ftp_download(ftp: ftplib.FTP, remote_path: str, local_path: Path) -> None:
    local_path.parent.mkdir(parents=True, exist_ok=True)
    with local_path.open("wb") as handle:
        ftp.retrbinary(f"RETR {remote_path}", handle.write)


def ftp_upload(ftp: ftplib.FTP, local_path: Path, remote_path: str) -> None:
    with local_path.open("rb") as handle:
        ftp.storbinary(f"STOR {remote_path}", handle)


def patch_uenv(uenv_text: str, bitstream_name: str, dtb_name: str, bitstream_size_hex: str) -> str:
    replacements = {
        "bitstream_image": bitstream_name,
        "bitstream_size": bitstream_size_hex,
        "devicetree_image": dtb_name,
    }

    lines = uenv_text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    seen = set()
    patched: list[str] = []
    for line in lines:
        if "=" not in line:
            patched.append(line)
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if key in replacements:
            patched.append(f"{key}={replacements[key]}")
            seen.add(key)
        else:
            patched.append(line)

    for key, value in replacements.items():
        if key not in seen:
            patched.append(f"{key}={value}")

    return "\n".join(patched).rstrip() + "\n"


def main() -> int:
    args = parse_args()
    if not args.bitstream.exists():
        raise FileNotFoundError(f"Bitstream not found: {args.bitstream}")
    if not args.dtb.exists():
        raise FileNotFoundError(f"DTB not found: {args.dtb}")

    args.backup_dir.mkdir(parents=True, exist_ok=True)
    bitstream_size_hex = f"0x{args.bitstream.stat().st_size:X}"

    ftp = ftplib.FTP()
    ftp.connect(args.host, 21, timeout=15)
    ftp.login(args.user, args.password)

    remote_uenv = f"{args.boot_dir}/uEnv.txt"
    remote_factory_backup = f"{args.boot_dir}/uEnv_factory_backup.txt"
    local_uenv = args.backup_dir / "uEnv.txt"
    local_system_dtb = args.backup_dir / "system.dtb"
    local_system_bit = args.backup_dir / "system.bit"

    ftp_download(ftp, remote_uenv, local_uenv)
    ftp_download(ftp, f"{args.boot_dir}/system.dtb", local_system_dtb)
    ftp_download(ftp, f"{args.boot_dir}/system.bit", local_system_bit)

    original_uenv = local_uenv.read_text(encoding="ascii", errors="ignore")
    patched_uenv = patch_uenv(original_uenv, args.bitstream_name, args.dtb_name, bitstream_size_hex)
    patched_uenv_path = args.backup_dir / "uEnv_ir_detector.txt"
    patched_uenv_path.write_text(patched_uenv, encoding="ascii", newline="\n")

    print(f"Backed up uEnv/system files under {args.backup_dir}")
    print(f"Patched bitstream_image={args.bitstream_name}")
    print(f"Patched bitstream_size={bitstream_size_hex}")
    print(f"Patched devicetree_image={args.dtb_name}")

    if args.dry_run:
        print("Dry run only: no remote files were modified.")
        ftp.quit()
        return 0

    try:
        ftp_upload(ftp, local_uenv, remote_factory_backup)
    except ftplib.error_perm:
        # Some FTP servers refuse overwrite when the file exists. Keep going.
        pass

    ftp_upload(ftp, args.bitstream, f"{args.boot_dir}/{args.bitstream_name}")
    ftp_upload(ftp, args.dtb, f"{args.boot_dir}/{args.dtb_name}")
    ftp_upload(ftp, patched_uenv_path, remote_uenv)
    ftp.quit()

    print("Persistent boot files uploaded.")
    print(f"Remote boot dir: {args.boot_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
