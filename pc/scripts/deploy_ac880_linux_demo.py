import argparse
import hashlib
import os
import posixpath
import shlex
import sys

try:
    import paramiko
except ImportError as exc:  # pragma: no cover - operator guidance path
    raise SystemExit(
        "paramiko is required. Install it with: python -m pip install --user paramiko"
    ) from exc


MODE_TO_SCRIPT = {
    "gray8": "run_demo_gray8.sh",
    "gray8_pl_probe": "run_demo_gray8_with_pl_probe.sh",
    "gray8_pl_real_layer": "run_demo_gray8_with_pl_real_layer.sh",
    "dump_runtime_dw_input": "run_dump_runtime_dw_input.sh",
    "runtime_dw_pl_compare": "run_demo_runtime_dw_pl_compare.sh",
    "inpath_dw_cpu_full": "run_demo_inpath_dw_cpu_full.sh",
    "inpath_dw_pl_full": "run_demo_inpath_dw_pl_full.sh",
    "tensor": "run_demo_tensor.sh",
    "pl_selftest": "run_pl_selftest.sh",
}

CHMOD_TARGETS = [
    "app/irdet_linux_ncnn_app",
    "app/irdet_linux_pl_dw3x3_tool",
    "lib/ld-linux-armhf.so.3",
    "run_demo_gray8.sh",
    "run_demo_gray8_with_pl_probe.sh",
    "run_demo_gray8_with_pl_real_layer.sh",
    "run_dump_runtime_dw_input.sh",
    "run_demo_runtime_dw_pl_compare.sh",
    "run_demo_inpath_dw_cpu_full.sh",
    "run_demo_inpath_dw_pl_full.sh",
    "run_demo_tensor.sh",
    "run_pl_selftest.sh",
]


def shell_quote(value: str) -> str:
    return shlex.quote(value)


def ensure_remote_dir(sftp, remote_path):
    if remote_path in ("", "/"):
        return
    parts = []
    current = remote_path
    while current not in ("", "/"):
        parts.append(current)
        current = posixpath.dirname(current)
    for part in reversed(parts):
        try:
            sftp.stat(part)
        except FileNotFoundError:
            sftp.mkdir(part)


def sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def iter_local_files(local_root):
    entries = []
    for root, dirs, files in os.walk(local_root):
        dirs.sort()
        files.sort()
        rel_dir = os.path.relpath(root, local_root)
        for name in files:
            local_path = os.path.join(root, name)
            rel_path = name if rel_dir == "." else os.path.join(rel_dir, name)
            entries.append((rel_path.replace("\\", "/"), local_path))
    entries.sort(key=lambda item: item[0])
    return entries


def run_command(ssh, command, timeout):
    stdin, stdout, stderr = ssh.exec_command(command, timeout=timeout)
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    rc = stdout.channel.recv_exit_status()
    return rc, out, err


def collect_remote_hashes(ssh, remote_root, timeout):
    quoted_root = shell_quote(remote_root)
    command = (
        f"if [ -d {quoted_root} ]; then "
        f"cd {quoted_root} && "
        "find . -type f -print | sort | while read f; do sha256sum \"$f\"; done; "
        "fi"
    )
    rc, out, err = run_command(ssh, command, timeout=max(30, timeout))
    if err:
        print(err, end="", file=sys.stderr)
    if rc != 0:
        raise SystemExit(rc)

    hashes = {}
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split(None, 1)
        if len(parts) != 2:
            continue
        digest, rel_path = parts
        if len(digest) != 64:
            continue
        rel_path = rel_path.strip()
        if rel_path.startswith("./"):
            rel_path = rel_path[2:]
        hashes[rel_path] = digest.lower()
    return hashes


def upload_tree_incremental(ssh, sftp, local_root, remote_root, timeout, clean=False, delete_stale=False):
    quoted_root = shell_quote(remote_root)
    if clean:
        rc, out, err = run_command(
            ssh,
            f"rm -rf {quoted_root} && mkdir -p {quoted_root}",
            timeout=max(30, timeout),
        )
        if out:
            print(out, end="")
        if err:
            print(err, end="", file=sys.stderr)
        if rc != 0:
            raise SystemExit(rc)
        remote_hashes = {}
    else:
        rc, out, err = run_command(ssh, f"mkdir -p {quoted_root}", timeout=max(30, timeout))
        if out:
            print(out, end="")
        if err:
            print(err, end="", file=sys.stderr)
        if rc != 0:
            raise SystemExit(rc)
        remote_hashes = collect_remote_hashes(ssh, remote_root, timeout)

    local_entries = iter_local_files(local_root)
    local_hashes = {}
    uploaded = []
    skipped = []
    for rel_path, local_path in local_entries:
        local_hash = sha256_file(local_path)
        local_hashes[rel_path] = local_hash
        remote_path = posixpath.join(remote_root, rel_path)
        if remote_hashes.get(rel_path) == local_hash:
            print(f"SKIP   {local_path} -> {remote_path}")
            skipped.append(rel_path)
            continue

        ensure_remote_dir(sftp, posixpath.dirname(remote_path))
        print(f"UPLOAD {local_path} -> {remote_path}")
        sftp.put(local_path, remote_path)
        uploaded.append(rel_path)

    deleted = []
    if delete_stale:
        stale_paths = sorted(set(remote_hashes) - set(local_hashes))
        if stale_paths:
            delete_commands = [
                f"rm -f {shell_quote(posixpath.join(remote_root, rel_path))}" for rel_path in stale_paths
            ]
            rc, out, err = run_command(ssh, " && ".join(delete_commands), timeout=max(30, timeout))
            if out:
                print(out, end="")
            if err:
                print(err, end="", file=sys.stderr)
            if rc != 0:
                raise SystemExit(rc)
            deleted = stale_paths
            for rel_path in stale_paths:
                print(f"DELETE {posixpath.join(remote_root, rel_path)}")

    return {
        "local_count": len(local_entries),
        "uploaded": uploaded,
        "skipped": skipped,
        "deleted": deleted,
    }


def list_remote_files(ssh, remote_root, timeout):
    quoted_root = shell_quote(remote_root)
    rc, out, err = run_command(
        ssh,
        f"cd {quoted_root} && find . -maxdepth 2 -type f | sort",
        timeout=max(30, timeout),
    )
    if out:
        print(out, end="")
    if err:
        print(err, end="", file=sys.stderr)
    if rc != 0:
        raise SystemExit(rc)


def run_mode(ssh, remote_root, mode, timeout):
    quoted_root = shell_quote(remote_root)
    chmod_targets = " ".join(shell_quote(item) for item in CHMOD_TARGETS)
    base_command = f"cd {quoted_root} && chmod +x {chmod_targets}"

    if mode == "none":
        return
    if mode == "full_demo":
        command = (
            f"{base_command} && "
            "./app/irdet_linux_pl_dw3x3_tool --all --skip-gpio && "
            "./run_demo_gray8.sh"
        )
    else:
        script_name = MODE_TO_SCRIPT[mode]
        command = f"{base_command} && ./{shell_quote(script_name)}"

    rc, out, err = run_command(ssh, command, timeout=timeout)
    if out:
        print(out, end="")
    if err:
        print(err, end="", file=sys.stderr)
    if rc != 0:
        raise SystemExit(rc)


def main():
    parser = argparse.ArgumentParser(description="Deploy and run the AC880 Linux ncnn demo bundle")
    parser.add_argument("--bundle-dir", required=True, help="Local zynq_linux_demo_bundle directory")
    parser.add_argument("--host", default="169.254.132.113", help="Board IPv4 address")
    parser.add_argument("--port", type=int, default=22, help="SSH port")
    parser.add_argument("--user", default="root", help="SSH username")
    parser.add_argument("--password", default="root", help="SSH password")
    parser.add_argument("--remote-dir", default="/home/root/irdet_demo", help="Remote bundle directory")
    parser.add_argument(
        "--mode",
        choices=(
            "gray8",
            "gray8_pl_probe",
            "gray8_pl_real_layer",
            "dump_runtime_dw_input",
            "runtime_dw_pl_compare",
            "inpath_dw_cpu_full",
            "inpath_dw_pl_full",
            "tensor",
            "pl_selftest",
            "full_demo",
            "none",
        ),
        default="gray8",
        help="Run one board-side demo script after upload, or upload only with none",
    )
    parser.add_argument("--timeout", type=int, default=180, help="Remote command timeout in seconds")
    parser.add_argument("--clean", action="store_true", help="Delete the remote bundle directory before upload")
    parser.add_argument(
        "--delete-stale",
        action="store_true",
        help="Remove remote files that no longer exist in the local bundle",
    )
    args = parser.parse_args()

    if not os.path.isdir(args.bundle_dir):
        raise SystemExit(f"Bundle directory not found: {args.bundle_dir}")

    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    print(f"Connecting to {args.host}:{args.port} as {args.user}...")
    ssh.connect(
        args.host,
        port=args.port,
        username=args.user,
        password=args.password,
        timeout=10,
        look_for_keys=False,
        allow_agent=False,
    )
    print("SSH connected.")

    sftp = ssh.open_sftp()
    sync_summary = upload_tree_incremental(
        ssh,
        sftp,
        args.bundle_dir,
        args.remote_dir,
        timeout=args.timeout,
        clean=args.clean,
        delete_stale=args.delete_stale,
    )
    sftp.close()

    print(
        "SYNC_SUMMARY "
        f"local={sync_summary['local_count']} "
        f"uploaded={len(sync_summary['uploaded'])} "
        f"skipped={len(sync_summary['skipped'])} "
        f"deleted={len(sync_summary['deleted'])}"
    )

    list_remote_files(ssh, args.remote_dir, args.timeout)
    run_mode(ssh, args.remote_dir, args.mode, args.timeout)

    ssh.close()
    print("DEPLOY_DEMO_DONE")


if __name__ == "__main__":
    raise SystemExit(main())
