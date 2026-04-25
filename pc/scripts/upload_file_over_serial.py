import argparse
import hashlib
import os
import posixpath
import re
import sys
import time

import serial


DEFAULT_PROMPT_SUFFIX = b"# "


class SerialShell:
    def __init__(self, port: str, baudrate: int, timeout: float) -> None:
        self._serial = serial.Serial(port, baudrate, timeout=timeout)

    def close(self) -> None:
        if self._serial.is_open:
            self._serial.close()

    def sync(self, settle_seconds: float) -> bytes:
        time.sleep(settle_seconds)
        self._serial.reset_input_buffer()
        self._serial.write(b"\r\n")
        time.sleep(0.3)
        return self.read_until_idle(1.5, 8.0)

    def write(self, data: bytes) -> None:
        self._serial.write(data)

    def read_until_idle(self, idle_seconds: float, max_seconds: float) -> bytes:
        chunks = []
        start = time.time()
        last_data = time.time()
        while (time.time() - start) < max_seconds:
            data = self._serial.read(4096)
            if data:
                chunks.append(data)
                last_data = time.time()
                continue
            if (time.time() - last_data) >= idle_seconds:
                break
            time.sleep(0.05)
        return b"".join(chunks)

    def run_command(self, command: str, idle_seconds: float = 1.0, max_seconds: float = 20.0) -> bytes:
        self.write(command.encode("utf-8") + b"\n")
        return self.read_until_idle(idle_seconds, max_seconds)


def sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def hex_lines_for_bytes(data: bytes, bytes_per_line: int):
    offset = 0
    while offset < len(data):
        chunk = data[offset : offset + bytes_per_line]
        yield chunk.hex().encode("ascii") + b"\n"
        offset += len(chunk)


def quote_sh(text: str) -> str:
    return "'" + text.replace("'", "'\"'\"'") + "'"


def ensure_success(output: bytes, context: str) -> None:
    if b"not found" in output or b"No such file or directory" in output or b"syntax error" in output:
        raise RuntimeError(f"{context} failed:\n{output.decode('utf-8', errors='replace')}")


def remote_sha256(shell: SerialShell, remote_path: str) -> str:
    cmd = f"sha256sum {quote_sh(remote_path)} | awk '{{print $1}}'"
    output = shell.run_command(cmd, idle_seconds=1.0, max_seconds=20.0)
    text = output.decode("utf-8", errors="replace")
    match = re.search(r"\b([0-9a-fA-F]{64})\b", text)
    if match:
        return match.group(1).lower()
    for line in text.replace("\r", "\n").splitlines():
        line = line.strip(" >#\t")
        if len(line) == 64 and all(ch in "0123456789abcdef" for ch in line.lower()):
            return line.lower()
    raise RuntimeError(f"Unable to parse remote sha256 for {remote_path}:\n{text}")


def upload_file(args) -> None:
    local_path = os.path.abspath(args.local_file)
    if not os.path.isfile(local_path):
        raise SystemExit(f"Local file not found: {local_path}")

    remote_path = args.remote_path
    remote_dir = posixpath.dirname(remote_path)
    remote_tmp_hex = posixpath.join(args.tmp_dir, f"irdet_upload_{os.getpid()}.hex")
    local_sha = sha256_file(local_path)

    shell = SerialShell(args.port, args.baud, timeout=0.2)
    try:
        banner = shell.sync(args.startup_delay)
        if args.verbose and banner:
            sys.stdout.write(banner.decode("utf-8", errors="replace"))

        if args.disable_echo:
            out = shell.run_command("stty -echo", idle_seconds=0.5, max_seconds=5.0)
            if args.verbose and out:
                sys.stdout.write(out.decode("utf-8", errors="replace"))

        prep_cmd = f"mkdir -p {quote_sh(remote_dir)} {quote_sh(args.tmp_dir)}"
        out = shell.run_command(prep_cmd, idle_seconds=0.5, max_seconds=10.0)
        ensure_success(out, "mkdir")
        if args.verbose and out:
            sys.stdout.write(out.decode("utf-8", errors="replace"))

        out = shell.run_command(f": > {quote_sh(remote_path)}", idle_seconds=0.5, max_seconds=10.0)
        ensure_success(out, "truncate remote")
        if args.verbose and out:
            sys.stdout.write(out.decode("utf-8", errors="replace"))

        with open(local_path, "rb") as handle:
            chunk_index = 0
            while True:
                binary_chunk = handle.read(args.upload_chunk_bytes)
                if not binary_chunk:
                    break
                chunk_index += 1
                shell.write(f"cat > {quote_sh(remote_tmp_hex)} <<'__IRDET_HEX__'\n".encode("utf-8"))
                time.sleep(args.heredoc_enter_delay)
                for index, line in enumerate(hex_lines_for_bytes(binary_chunk, args.bytes_per_line), start=1):
                    shell.write(line)
                    if args.line_delay_ms > 0:
                        time.sleep(args.line_delay_ms / 1000.0)
                    if args.batch_lines > 0 and (index % args.batch_lines) == 0 and args.batch_delay_ms > 0:
                        time.sleep(args.batch_delay_ms / 1000.0)
                shell.write(b"__IRDET_HEX__\n")
                time.sleep(args.heredoc_exit_delay)
                heredoc_out = shell.read_until_idle(0.8, max(20.0, args.max_seconds))
                ensure_success(heredoc_out, f"hex upload chunk {chunk_index}")
                if args.verbose and heredoc_out:
                    sys.stdout.write(heredoc_out.decode("utf-8", errors="replace"))

                decode_cmd = (
                    f"while IFS= read -r line || [ -n \"$line\" ]; do "
                    f"printf '%b' \"$(echo \"$line\" | sed 's/../\\\\x&/g')\"; "
                    f"done < {quote_sh(remote_tmp_hex)} >> {quote_sh(remote_path)}"
                )
                out = shell.run_command(decode_cmd, idle_seconds=1.0, max_seconds=args.max_seconds)
                ensure_success(out, f"decode chunk {chunk_index}")
                if args.verbose and out:
                    sys.stdout.write(out.decode("utf-8", errors="replace"))

        if args.chmod:
            out = shell.run_command(
                f"chmod {quote_sh(args.chmod)} {quote_sh(remote_path)}",
                idle_seconds=0.5,
                max_seconds=10.0,
            )
            ensure_success(out, "chmod")
            if args.verbose and out:
                sys.stdout.write(out.decode("utf-8", errors="replace"))

        out = shell.run_command(f"rm -f {quote_sh(remote_tmp_hex)}", idle_seconds=0.5, max_seconds=10.0)
        ensure_success(out, "cleanup")
        if args.verbose and out:
            sys.stdout.write(out.decode("utf-8", errors="replace"))

        remote_digest = remote_sha256(shell, remote_path)
        if remote_digest != local_sha:
            raise RuntimeError(
                f"sha256 mismatch for {remote_path}: local={local_sha} remote={remote_digest}"
            )

        if args.disable_echo:
            out = shell.run_command("stty echo", idle_seconds=0.5, max_seconds=5.0)
            if args.verbose and out:
                sys.stdout.write(out.decode("utf-8", errors="replace"))

        print(f"SERIAL_UPLOAD_OK local={local_path} remote={remote_path} sha256={local_sha}")
    finally:
        try:
            if args.disable_echo:
                try:
                    shell.run_command("stty echo", idle_seconds=0.3, max_seconds=3.0)
                except Exception:
                    pass
        finally:
            shell.close()


def parse_args():
    parser = argparse.ArgumentParser(description="Upload one file to AC880 Linux over a serial shell using hex text.")
    parser.add_argument("--port", default="COM3", help="Serial COM port")
    parser.add_argument("--baud", type=int, default=115200, help="Serial baud rate")
    parser.add_argument("--local-file", required=True, help="Local file path to upload")
    parser.add_argument("--remote-path", required=True, help="Remote destination path")
    parser.add_argument("--tmp-dir", default="/tmp", help="Remote temporary directory")
    parser.add_argument("--bytes-per-line", type=int, default=256, help="Bytes encoded per hex line")
    parser.add_argument("--startup-delay", type=float, default=0.3, help="Initial settle delay before sync")
    parser.add_argument("--max-seconds", type=float, default=120.0, help="Max seconds for long remote commands")
    parser.add_argument("--chmod", default="", help="Optional chmod mode to apply after upload")
    parser.add_argument("--disable-echo", action="store_true", help="Disable tty echo during transfer")
    parser.add_argument("--upload-chunk-bytes", type=int, default=32768, help="Binary bytes uploaded per remote heredoc chunk")
    parser.add_argument("--line-delay-ms", type=float, default=1.0, help="Delay after each hex line write")
    parser.add_argument("--batch-lines", type=int, default=32, help="Insert an extra delay after this many hex lines")
    parser.add_argument("--batch-delay-ms", type=float, default=20.0, help="Extra delay after each batch")
    parser.add_argument("--heredoc-enter-delay", type=float, default=0.4, help="Delay after opening the remote heredoc")
    parser.add_argument("--heredoc-exit-delay", type=float, default=0.4, help="Delay after sending the heredoc terminator")
    parser.add_argument("--verbose", action="store_true", help="Print serial shell output")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    upload_file(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
