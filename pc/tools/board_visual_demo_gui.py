#!/usr/bin/env python3
"""Minimal tkinter GUI for AC880 board visual inference."""

from __future__ import annotations

import argparse
import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from PIL import Image, ImageTk

from board_visual_infer import recover_board_pl, repo_root_from_script, run_board_visual_inference


PREVIEW_SIZE = (520, 420)


class BoardVisualDemoApp:
    def __init__(
        self,
        root: tk.Tk,
        *,
        repo_root: Path,
        host: str,
        host_candidates: tuple[str, ...],
        host_wait_seconds: int,
        port: int,
        user: str,
        password: str,
        remote_dir: str,
        output_dir: Path,
    ) -> None:
        self.root = root
        self.repo_root = repo_root
        self.host = host
        self.host_candidates = host_candidates
        self.host_wait_seconds = host_wait_seconds
        self.port = port
        self.user = user
        self.password = password
        self.remote_dir = remote_dir
        self.output_dir = output_dir

        self.image_path: Path | None = None
        self.worker_thread: threading.Thread | None = None
        self.event_queue: queue.Queue[tuple[str, object]] = queue.Queue()
        self.original_photo = None
        self.result_photo = None

        self.mode_var = tk.StringVar(value="inpath_dw_pl_full")
        self.image_var = tk.StringVar(value="No image selected")
        self.auto_recover_pl_var = tk.BooleanVar(value=False)
        self.status_var = tk.StringVar(value="Tip: click Recover PL after a power cycle before running inpath_dw_pl_full.")

        self.root.title("AC880 Board Visual Demo")
        self.root.geometry("1280x900")
        self._build_ui()
        self.root.after(120, self._poll_events)

    def _build_ui(self) -> None:
        controls = ttk.Frame(self.root, padding=10)
        controls.pack(fill=tk.X)

        self.select_button = ttk.Button(controls, text="Select Image", command=self._select_image)
        self.select_button.pack(side=tk.LEFT, padx=(0, 8))

        self.recover_button = ttk.Button(controls, text="Recover PL", command=self._recover_pl)
        self.recover_button.pack(side=tk.LEFT, padx=(0, 8))

        self.run_button = ttk.Button(controls, text="Run Board Inference", command=self._run_inference)
        self.run_button.pack(side=tk.LEFT, padx=(0, 12))

        ttk.Label(controls, text="Mode").pack(side=tk.LEFT, padx=(0, 6))
        self.mode_box = ttk.Combobox(
            controls,
            textvariable=self.mode_var,
            values=("gray8", "inpath_dw_cpu_full", "inpath_dw_pl_full"),
            state="readonly",
            width=22,
        )
        self.mode_box.pack(side=tk.LEFT, padx=(0, 12))

        self.auto_recover_check = ttk.Checkbutton(
            controls,
            text="Auto Recover PL",
            variable=self.auto_recover_pl_var,
        )
        self.auto_recover_check.pack(side=tk.LEFT, padx=(0, 12))

        image_label = ttk.Label(controls, textvariable=self.image_var)
        image_label.pack(side=tk.LEFT, fill=tk.X, expand=True)

        status_frame = ttk.Frame(self.root, padding=(10, 0, 10, 6))
        status_frame.pack(fill=tk.X)
        ttk.Label(status_frame, textvariable=self.status_var).pack(anchor="w")

        image_frame = ttk.Frame(self.root, padding=(10, 0, 10, 10))
        image_frame.pack(fill=tk.BOTH, expand=True)
        image_frame.columnconfigure(0, weight=1)
        image_frame.columnconfigure(1, weight=1)
        image_frame.rowconfigure(1, weight=1)

        ttk.Label(image_frame, text="Original").grid(row=0, column=0, sticky="w", pady=(0, 6))
        ttk.Label(image_frame, text="Result").grid(row=0, column=1, sticky="w", pady=(0, 6))

        self.original_label = ttk.Label(image_frame, anchor="center", relief=tk.SOLID)
        self.original_label.grid(row=1, column=0, sticky="nsew", padx=(0, 8))

        self.result_label = ttk.Label(image_frame, anchor="center", relief=tk.SOLID)
        self.result_label.grid(row=1, column=1, sticky="nsew", padx=(8, 0))

        log_frame = ttk.Frame(self.root, padding=(10, 0, 10, 10))
        log_frame.pack(fill=tk.BOTH, expand=True)
        ttk.Label(log_frame, text="Log").pack(anchor="w", pady=(0, 6))

        self.log_text = tk.Text(log_frame, wrap="word", height=16)
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        log_scroll = ttk.Scrollbar(log_frame, orient=tk.VERTICAL, command=self.log_text.yview)
        log_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text.configure(yscrollcommand=log_scroll.set)

    def _append_log(self, message: str) -> None:
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)

    def _set_preview(self, label: ttk.Label, image_path: Path, which: str) -> None:
        image = Image.open(image_path).convert("RGB")
        image.thumbnail(PREVIEW_SIZE, Image.Resampling.LANCZOS)
        photo = ImageTk.PhotoImage(image)
        label.configure(image=photo)
        if which == "original":
            self.original_photo = photo
        else:
            self.result_photo = photo

    def _set_busy(self, is_busy: bool) -> None:
        state = ["disabled"] if is_busy else ["!disabled"]
        self.select_button.state(state)
        self.recover_button.state(state)
        self.run_button.state(state)
        self.mode_box.state(["disabled"] if is_busy else ["readonly"])
        self.auto_recover_check.state(state)

    def _select_image(self) -> None:
        file_path = filedialog.askopenfilename(
            title="Select one thermal image",
            filetypes=[
                ("Image files", "*.png;*.jpg;*.jpeg;*.bmp;*.tif;*.tiff"),
                ("All files", "*.*"),
            ],
        )
        if not file_path:
            return

        self.image_path = Path(file_path)
        self.image_var.set(str(self.image_path))
        self._set_preview(self.original_label, self.image_path, "original")
        self.result_label.configure(image="")
        self.result_photo = None
        self._append_log(f"Selected image: {self.image_path}")

    def _recover_pl(self) -> None:
        if self.worker_thread is not None and self.worker_thread.is_alive():
            return
        self._append_log("Recovering PL over JTAG ...")
        self._set_busy(True)
        self.worker_thread = threading.Thread(target=self._worker_recover_entry, daemon=True)
        self.worker_thread.start()

    def _run_inference(self) -> None:
        if self.image_path is None:
            messagebox.showwarning("No image", "Please select one image first.")
            return
        if self.worker_thread is not None and self.worker_thread.is_alive():
            return

        self._append_log(f"Running board inference mode={self.mode_var.get()} ...")
        self._set_busy(True)
        self.worker_thread = threading.Thread(target=self._worker_infer_entry, daemon=True)
        self.worker_thread.start()

    def _worker_log(self, message: str) -> None:
        self.event_queue.put(("log", message))

    def _worker_recover_entry(self) -> None:
        try:
            recover_board_pl(repo_root=self.repo_root, log_callback=self._worker_log)
            self.event_queue.put(("recovered", None))
        except Exception as exc:
            self.event_queue.put(("error", str(exc)))

    def _worker_infer_entry(self) -> None:
        try:
            result = run_board_visual_inference(
                image=self.image_path,
                mode=self.mode_var.get(),
                repo_root=self.repo_root,
                host=self.host,
                host_candidates=self.host_candidates,
                host_wait_seconds=self.host_wait_seconds,
                port=self.port,
                user=self.user,
                password=self.password,
                remote_dir=self.remote_dir,
                output_dir=self.output_dir,
                recover_pl_first=self.auto_recover_pl_var.get(),
                log_callback=self._worker_log,
            )
            self.event_queue.put(("result", result))
        except Exception as exc:
            self.event_queue.put(("error", str(exc)))

    def _poll_events(self) -> None:
        try:
            while True:
                event_type, payload = self.event_queue.get_nowait()
                if event_type == "log":
                    self._append_log(str(payload))
                elif event_type == "recovered":
                    self._append_log("PL recovery finished.")
                    self.status_var.set(
                        "PL recovery finished. You can now run inpath_dw_pl_full if Linux and SSH are ready."
                    )
                    self._set_busy(False)
                elif event_type == "result":
                    result = payload
                    annotated_path = Path(result["artifacts"]["annotated_out"])
                    self._set_preview(self.result_label, annotated_path, "result")
                    self._append_log(f"Result image: {annotated_path}")
                    self._append_log(f"Result JSON: {result['artifacts']['result_json']}")
                    self._append_log(f"Board log: {result['artifacts']['log_out']}")
                    self.status_var.set(
                        f"Finished mode={result['mode']} det_count={result['remote_inference']['det_count']}."
                    )
                    self._set_busy(False)
                elif event_type == "error":
                    self._append_log(f"ERROR: {payload}")
                    self.status_var.set("The last operation failed. Check the log for details.")
                    messagebox.showerror("Board operation failed", str(payload))
                    self._set_busy(False)
        except queue.Empty:
            pass
        finally:
            self.root.after(120, self._poll_events)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Tkinter GUI for AC880 board visual inference.")
    parser.add_argument("--repo-root", type=Path, default=repo_root_from_script(), help="Repository root.")
    parser.add_argument("--host", default="auto", help="Board IPv4 address or auto.")
    parser.add_argument(
        "--host-candidates",
        default="169.254.132.113,192.168.0.233,192.168.0.2",
        help="Comma-separated candidate host list used when --host auto.",
    )
    parser.add_argument(
        "--host-wait-seconds",
        type=int,
        default=20,
        help="How long to wait for the board SSH port after power-up or recovery.",
    )
    parser.add_argument("--port", type=int, default=22, help="SSH port.")
    parser.add_argument("--user", default="root", help="SSH username.")
    parser.add_argument("--password", default="root", help="SSH password.")
    parser.add_argument("--remote-dir", default="/home/root/irdet_demo", help="Remote demo bundle directory.")
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=repo_root_from_script() / "outputs" / "board_vis",
        help="Directory used for saved results.",
    )
    return parser


def main() -> int:
    parser = build_arg_parser()
    args = parser.parse_args()
    host_candidates = tuple(item.strip() for item in args.host_candidates.split(",") if item.strip())

    root = tk.Tk()
    BoardVisualDemoApp(
        root,
        repo_root=args.repo_root,
        host=args.host,
        host_candidates=host_candidates,
        host_wait_seconds=args.host_wait_seconds,
        port=args.port,
        user=args.user,
        password=args.password,
        remote_dir=args.remote_dir,
        output_dir=args.out_dir,
    )
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
