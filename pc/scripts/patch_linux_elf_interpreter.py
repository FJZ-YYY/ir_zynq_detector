import argparse
from pathlib import Path

try:
    import lief
except ImportError as exc:  # pragma: no cover
    raise SystemExit("lief is required. Install it with: python -m pip install --user lief") from exc


def patch_binary(input_path: Path, output_path: Path, runtime_root: str) -> None:
    binary = lief.parse(str(input_path))
    if binary is None:
        raise SystemExit(f"Failed to parse ELF file: {input_path}")

    interpreter = f"{runtime_root}/lib/ld-linux-armhf.so.3"
    runpath = f"{runtime_root}/lib"

    binary.interpreter = interpreter

    for entry in list(binary.dynamic_entries):
        if isinstance(entry, lief.ELF.DynamicEntryRunPath) or isinstance(entry, lief.ELF.DynamicEntryRpath):
            binary.remove(entry)

    binary.add(lief.ELF.DynamicEntryRunPath(runpath))
    binary.write(str(output_path))


def main() -> int:
    parser = argparse.ArgumentParser(description="Patch ARM Linux ELF interpreter and RUNPATH for board deployment")
    parser.add_argument("--input", required=True, help="Input ELF file")
    parser.add_argument("--output", help="Output ELF file; defaults to input path when --in-place is set")
    parser.add_argument("--runtime-root", default="/home/root/irdet_demo", help="Board-side bundle root directory")
    parser.add_argument("--in-place", action="store_true", help="Patch the input file in place")
    args = parser.parse_args()

    input_path = Path(args.input).resolve()
    if not input_path.is_file():
        raise SystemExit(f"Input ELF not found: {input_path}")

    if args.in_place:
        output_path = input_path
    elif args.output:
        output_path = Path(args.output).resolve()
    else:
        raise SystemExit("Provide --output or use --in-place")

    patch_binary(input_path, output_path, args.runtime_root)
    print(f"PATCHED_ELF {output_path} runtime_root={args.runtime_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
