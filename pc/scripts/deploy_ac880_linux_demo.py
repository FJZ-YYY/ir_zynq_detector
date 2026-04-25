import argparse
import os
import posixpath
import sys

try:
    import paramiko
except ImportError as exc:  # pragma: no cover - operator guidance path
    raise SystemExit(
        "paramiko is required. Install it with: python -m pip install --user paramiko"
    ) from exc


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


def upload_tree(sftp, local_root, remote_root):
    for root, _, files in os.walk(local_root):
        rel = os.path.relpath(root, local_root)
        remote_dir = remote_root if rel == "." else posixpath.join(remote_root, *rel.split(os.sep))
        ensure_remote_dir(sftp, remote_dir)
        for name in files:
            local_path = os.path.join(root, name)
            remote_path = posixpath.join(remote_dir, name)
            print(f"UPLOAD {local_path} -> {remote_path}")
            sftp.put(local_path, remote_path)


def run_command(ssh, command, timeout):
    stdin, stdout, stderr = ssh.exec_command(command, timeout=timeout)
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    rc = stdout.channel.recv_exit_status()
    return rc, out, err


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
        choices=("gray8", "tensor", "pl_selftest", "none"),
        default="gray8",
        help="Run the gray8 demo, tensor demo, PL selftest, or upload only",
    )
    parser.add_argument("--timeout", type=int, default=180, help="Remote command timeout in seconds")
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

    rc, out, err = run_command(
        ssh,
        f"rm -rf {args.remote_dir} && mkdir -p {args.remote_dir}",
        timeout=max(30, args.timeout),
    )
    if out:
        print(out, end="")
    if err:
        print(err, end="", file=sys.stderr)
    if rc != 0:
        raise SystemExit(rc)

    sftp = ssh.open_sftp()
    upload_tree(sftp, args.bundle_dir, args.remote_dir)
    sftp.close()
    print("Upload tree done.")

    rc, out, err = run_command(
        ssh,
        f"cd {args.remote_dir} && find . -maxdepth 2 -type f | sort",
        timeout=max(30, args.timeout),
    )
    if out:
        print(out, end="")
    if err:
        print(err, end="", file=sys.stderr)
    if rc != 0:
        raise SystemExit(rc)

    if args.mode != "none":
        if args.mode == "gray8":
            script_name = "run_demo_gray8.sh"
        elif args.mode == "tensor":
            script_name = "run_demo_tensor.sh"
        else:
            script_name = "run_pl_selftest.sh"
        command = (
            f"cd {args.remote_dir} && chmod +x app/irdet_linux_ncnn_app app/irdet_linux_pl_dw3x3_tool "
            f"lib/ld-linux-armhf.so.3 run_demo_gray8.sh run_demo_tensor.sh run_pl_selftest.sh && ./{script_name}"
        )
        rc, out, err = run_command(ssh, command, timeout=args.timeout)
        if out:
            print(out, end="")
        if err:
            print(err, end="", file=sys.stderr)
        if rc != 0:
            raise SystemExit(rc)

    ssh.close()
    print("DEPLOY_DEMO_DONE")


if __name__ == "__main__":
    raise SystemExit(main())
