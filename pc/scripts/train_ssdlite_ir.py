#!/usr/bin/env python3
"""Minimal training entrypoint for FLIR thermal 3-class SSDLite-MobileNetV2."""

from __future__ import annotations

import argparse
import json
import random
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from pc.models.flir_ir_dataset import FlirCocoDetectionDataset, detection_collate_fn
from pc.models.ssdlite_mobilenetv2_ir import (
    FIXED_NCHW_INPUT_CONTRACT,
    LEGACY_BRIDGE_INPUT_CONTRACT,
    build_ssdlite_mobilenetv2_ir,
    normalize_input_contract_name,
)


def require_torch() -> tuple[Any, Any]:
    try:
        import torch
        from torch.utils.data import DataLoader
    except ImportError as exc:  # pragma: no cover - runtime dependency
        raise RuntimeError(
            "PyTorch is not installed. Create a training environment with torch and torchvision first."
        ) from exc
    return torch, DataLoader


def load_manifest(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as fp:
        return json.load(fp)


def pick_device(torch: Any, requested: str) -> Any:
    if requested != "auto":
        return torch.device(requested)
    if torch.cuda.is_available():
        return torch.device("cuda")
    return torch.device("cpu")


def move_targets_to_device(torch: Any, targets: list[dict[str, Any]], device: Any) -> list[dict[str, Any]]:
    moved = []
    for target in targets:
        new_target = {}
        for key, value in target.items():
            if torch.is_tensor(value):
                new_target[key] = value.to(device)
            else:
                new_target[key] = value
        moved.append(new_target)
    return moved


def set_seed(seed: int, torch: Any) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def pick_autocast(torch: Any, device: Any, enabled: bool) -> Any:
    if not enabled or device.type != "cuda":
        return torch.autocast(device_type="cpu", enabled=False)
    return torch.autocast(device_type="cuda", dtype=torch.float16, enabled=True)


def build_grad_scaler(torch: Any, device: Any, enabled: bool) -> Any:
    use_amp = enabled and device.type == "cuda"
    return torch.amp.GradScaler("cuda", enabled=use_amp)


def build_scheduler(torch: Any, optimizer: Any, args: argparse.Namespace, steps_per_epoch: int) -> Any:
    scheduler_name = args.lr_scheduler
    if scheduler_name == "none":
        return None
    if scheduler_name == "cosine":
        return torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=max(args.epochs, 1))
    if scheduler_name == "multistep":
        milestones = [int(x) for x in args.lr_milestones.split(",") if x.strip()]
        if not milestones:
            milestones = [max(args.epochs // 2, 1), max((args.epochs * 3) // 4, 1)]
        return torch.optim.lr_scheduler.MultiStepLR(optimizer, milestones=milestones, gamma=args.lr_gamma)
    raise ValueError(f"Unsupported lr scheduler: {scheduler_name}")


def get_learning_rate(optimizer: Any) -> float:
    return float(optimizer.param_groups[0]["lr"])


def build_train_sampler(torch: Any, dataset: Any, args: argparse.Namespace) -> tuple[Any, dict[str, Any] | None]:
    if args.sampler == "shuffle":
        return None, None

    weights = dataset.build_sampling_weights(
        rare_class_power=args.sampler_rare_class_power,
        empty_image_weight=args.sampler_empty_image_weight,
        max_class_weight=args.sampler_max_class_weight,
    )
    sampler = torch.utils.data.WeightedRandomSampler(
        weights=torch.tensor(weights, dtype=torch.double),
        num_samples=len(weights),
        replacement=True,
    )
    summary = dataset.summarize_sampling_weights(
        rare_class_power=args.sampler_rare_class_power,
        empty_image_weight=args.sampler_empty_image_weight,
        max_class_weight=args.sampler_max_class_weight,
    )
    summary["sampler"] = args.sampler
    return sampler, summary


def train_one_epoch(
    torch: Any,
    model: Any,
    optimizer: Any,
    scheduler: Any,
    scaler: Any,
    loader: Any,
    device: Any,
    epoch: int,
    log_interval: int,
    amp_enabled: bool,
) -> float:
    model.train()
    running_loss = 0.0
    sample_count = 0

    for step, (images, targets) in enumerate(loader, start=1):
        images = [img.to(device) for img in images]
        targets = move_targets_to_device(torch, targets, device)

        optimizer.zero_grad(set_to_none=True)
        with pick_autocast(torch, device, amp_enabled):
            loss_dict = model(images, targets)
            loss = sum(loss_dict.values())

        if scaler.is_enabled():
            scaler.scale(loss).backward()
            scaler.unscale_(optimizer)
            scaler.step(optimizer)
            scaler.update()
        else:
            loss.backward()
            optimizer.step()

        batch_size = len(images)
        running_loss += float(loss.item()) * batch_size
        sample_count += batch_size

        if step % log_interval == 0:
            details = " ".join(f"{k}={float(v.item()):.4f}" for k, v in loss_dict.items())
            print(
                f"[train] epoch={epoch} step={step}/{len(loader)} "
                f"loss={float(loss.item()):.4f} lr={get_learning_rate(optimizer):.6f} {details}"
            )

    return running_loss / max(sample_count, 1)


def evaluate_val_loss(torch: Any, model: Any, loader: Any, device: Any, amp_enabled: bool) -> float:
    # torchvision detection models return losses only in train mode.
    model.train()
    running_loss = 0.0
    sample_count = 0

    with torch.no_grad():
        for images, targets in loader:
            images = [img.to(device) for img in images]
            targets = move_targets_to_device(torch, targets, device)
            with pick_autocast(torch, device, amp_enabled):
                loss_dict = model(images, targets)
                loss = sum(loss_dict.values())
            batch_size = len(images)
            running_loss += float(loss.item()) * batch_size
            sample_count += batch_size

    model.eval()
    return running_loss / max(sample_count, 1)


def summarize_predictions(
    torch: Any,
    model: Any,
    loader: Any,
    device: Any,
    score_thresh: float,
    amp_enabled: bool,
) -> dict[str, float]:
    model.eval()
    image_count = 0
    total_kept = 0
    with torch.no_grad():
        for images, _ in loader:
            images = [img.to(device) for img in images]
            with pick_autocast(torch, device, amp_enabled):
                outputs = model(images)
            image_count += len(outputs)
            for output in outputs:
                scores = output["scores"].detach().cpu()
                total_kept += int((scores >= score_thresh).sum().item())

    return {
        "images": float(image_count),
        "avg_detections_per_image": float(total_kept) / max(image_count, 1),
    }


def save_checkpoint(
    path: Path,
    model: Any,
    optimizer: Any,
    scheduler: Any,
    scaler: Any,
    epoch: int,
    train_loss: float,
    val_loss: float,
    class_names: list[str],
    args: argparse.Namespace,
) -> None:
    torch, _ = require_torch()
    path.parent.mkdir(parents=True, exist_ok=True)
    scheduler_state = scheduler.state_dict() if scheduler is not None else None
    scaler_state = scaler.state_dict() if scaler is not None and scaler.is_enabled() else None
    torch.save(
        {
            "epoch": epoch,
            "model_state_dict": model.state_dict(),
            "optimizer_state_dict": optimizer.state_dict(),
            "scheduler_state_dict": scheduler_state,
            "scaler_state_dict": scaler_state,
            "train_loss": train_loss,
            "val_loss": val_loss,
            "class_names": class_names,
            "config": {
                "input_width": args.input_width,
                "input_height": args.input_height,
                "width_mult": args.width_mult,
                "score_thresh": args.score_thresh,
                "nms_thresh": args.nms_thresh,
                "num_classes_with_background": len(class_names) + 1,
                "hflip_prob": args.hflip_prob,
                "lr_scheduler": args.lr_scheduler,
                "amp": bool(args.amp),
                "input_contract": normalize_input_contract_name(args.input_contract),
                "sampler": args.sampler,
                "sampler_empty_image_weight": args.sampler_empty_image_weight,
                "sampler_rare_class_power": args.sampler_rare_class_power,
                "sampler_max_class_weight": args.sampler_max_class_weight,
            },
        },
        path,
    )


def maybe_resume_checkpoint(
    torch: Any,
    checkpoint_path: Path | None,
    model: Any,
    optimizer: Any,
    scheduler: Any,
    scaler: Any,
) -> tuple[int, float]:
    if checkpoint_path is None:
        return 1, float("inf")
    checkpoint = torch.load(checkpoint_path, map_location="cpu")
    model.load_state_dict(checkpoint["model_state_dict"])
    if "optimizer_state_dict" in checkpoint:
        optimizer.load_state_dict(checkpoint["optimizer_state_dict"])
    if scheduler is not None and checkpoint.get("scheduler_state_dict") is not None:
        scheduler.load_state_dict(checkpoint["scheduler_state_dict"])
    if scaler is not None and scaler.is_enabled() and checkpoint.get("scaler_state_dict") is not None:
        scaler.load_state_dict(checkpoint["scaler_state_dict"])
    start_epoch = int(checkpoint["epoch"]) + 1
    best_val_loss = float(checkpoint.get("val_loss", float("inf")))
    print(f"Resumed from checkpoint: {checkpoint_path} next_epoch={start_epoch} best_val_loss={best_val_loss:.4f}")
    return start_epoch, best_val_loss


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train a minimal FLIR SSDLite-MobileNetV2 detector.")
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("build/flir_thermal_3cls/dataset_manifest.json"),
        help="Path to the prepared FLIR subset manifest.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("build/train_ssdlite_ir"),
        help="Directory for checkpoints and training logs.",
    )
    parser.add_argument("--epochs", type=int, default=10, help="Number of training epochs.")
    parser.add_argument("--batch-size", type=int, default=4, help="Training batch size.")
    parser.add_argument("--val-batch-size", type=int, default=4, help="Validation batch size.")
    parser.add_argument("--lr", type=float, default=1e-3, help="AdamW learning rate.")
    parser.add_argument("--weight-decay", type=float, default=1e-4, help="AdamW weight decay.")
    parser.add_argument("--num-workers", type=int, default=0, help="DataLoader workers.")
    parser.add_argument("--device", type=str, default="auto", help="auto, cpu, or cuda.")
    parser.add_argument("--width-mult", type=float, default=1.0, help="MobileNetV2 width multiplier.")
    parser.add_argument("--input-width", type=int, default=160, help="Detector input width.")
    parser.add_argument("--input-height", type=int, default=128, help="Detector input height.")
    parser.add_argument(
        "--input-contract",
        choices=(LEGACY_BRIDGE_INPUT_CONTRACT, FIXED_NCHW_INPUT_CONTRACT),
        default=FIXED_NCHW_INPUT_CONTRACT,
        help="How input_width/input_height map into torchvision SSD fixed_size.",
    )
    parser.add_argument("--score-thresh", type=float, default=0.20, help="Inference score threshold.")
    parser.add_argument("--nms-thresh", type=float, default=0.45, help="Inference NMS threshold.")
    parser.add_argument("--hflip-prob", type=float, default=0.5, help="Horizontal flip probability for train split.")
    parser.add_argument(
        "--sampler",
        choices=("shuffle", "weighted"),
        default="shuffle",
        help="Training sample selection strategy. weighted oversamples images containing rare classes.",
    )
    parser.add_argument(
        "--sampler-empty-image-weight",
        type=float,
        default=0.20,
        help="Relative sampling weight for empty images when --sampler weighted.",
    )
    parser.add_argument(
        "--sampler-rare-class-power",
        type=float,
        default=1.0,
        help="Exponent controlling how aggressively rare classes are oversampled when --sampler weighted.",
    )
    parser.add_argument(
        "--sampler-max-class-weight",
        type=float,
        default=4.0,
        help="Upper cap for per-class oversampling weight when --sampler weighted.",
    )
    parser.add_argument("--max-train-samples", type=int, default=None, help="Optional cap for quick debug training.")
    parser.add_argument("--max-val-samples", type=int, default=None, help="Optional cap for quick debug validation.")
    parser.add_argument("--log-interval", type=int, default=20, help="Steps between training logs.")
    parser.add_argument("--seed", type=int, default=42, help="Random seed.")
    parser.add_argument("--resume", type=Path, default=None, help="Resume from checkpoint.")
    parser.add_argument("--save-every", type=int, default=5, help="Save epoch checkpoint every N epochs.")
    parser.add_argument(
        "--lr-scheduler",
        choices=("none", "cosine", "multistep"),
        default="cosine",
        help="Learning-rate scheduler.",
    )
    parser.add_argument(
        "--lr-milestones",
        type=str,
        default="",
        help="Comma-separated epoch milestones for multistep scheduler.",
    )
    parser.add_argument("--lr-gamma", type=float, default=0.1, help="Gamma for multistep scheduler.")
    parser.add_argument("--amp", action="store_true", help="Enable AMP on CUDA.")
    parser.add_argument("--pin-memory", action="store_true", help="Enable DataLoader pin_memory.")
    parser.add_argument(
        "--persistent-workers",
        action="store_true",
        help="Keep DataLoader workers alive between epochs when num_workers > 0.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    torch, DataLoader = require_torch()
    set_seed(args.seed, torch)

    manifest = load_manifest(args.manifest)
    class_names = list(manifest["target_classes"])
    num_classes_with_background = len(class_names) + 1

    train_dataset = FlirCocoDetectionDataset(
        manifest_path=args.manifest,
        split="train",
        training=True,
        max_samples=args.max_train_samples,
        hflip_prob=args.hflip_prob,
    )
    val_dataset = FlirCocoDetectionDataset(
        manifest_path=args.manifest,
        split="val",
        training=False,
        max_samples=args.max_val_samples,
    )
    train_sampler, train_sampler_summary = build_train_sampler(torch, train_dataset, args)

    train_loader = DataLoader(
        train_dataset,
        batch_size=args.batch_size,
        shuffle=train_sampler is None,
        sampler=train_sampler,
        num_workers=args.num_workers,
        collate_fn=detection_collate_fn,
        pin_memory=args.pin_memory,
        persistent_workers=args.persistent_workers if args.num_workers > 0 else False,
    )
    val_loader = DataLoader(
        val_dataset,
        batch_size=args.val_batch_size,
        shuffle=False,
        num_workers=args.num_workers,
        collate_fn=detection_collate_fn,
        pin_memory=args.pin_memory,
        persistent_workers=args.persistent_workers if args.num_workers > 0 else False,
    )

    device = pick_device(torch, args.device)
    model = build_ssdlite_mobilenetv2_ir(
        num_classes_with_background=num_classes_with_background,
        input_width=args.input_width,
        input_height=args.input_height,
        width_mult=args.width_mult,
        input_contract=args.input_contract,
        pretrained_backbone=True,
        score_thresh=args.score_thresh,
        nms_thresh=args.nms_thresh,
    ).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=args.weight_decay)
    scheduler = build_scheduler(torch, optimizer, args, steps_per_epoch=len(train_loader))
    scaler = build_grad_scaler(torch, device, args.amp)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    history = []
    start_epoch, best_val_loss = maybe_resume_checkpoint(
        torch=torch,
        checkpoint_path=args.resume,
        model=model,
        optimizer=optimizer,
        scheduler=scheduler,
        scaler=scaler,
    )

    print(
        f"Training SSDLite-MobileNetV2-IR on {device} "
        f"with classes={class_names} input={args.input_width}x{args.input_height} "
        f"contract={normalize_input_contract_name(args.input_contract)} width_mult={args.width_mult}"
    )
    print(
        f"train_images={len(train_dataset)} val_images={len(val_dataset)} "
        f"batch_size={args.batch_size} epochs={args.epochs} amp={bool(args.amp and device.type == 'cuda')}"
    )
    print(
        f"lr={args.lr} scheduler={args.lr_scheduler} num_workers={args.num_workers} "
        f"pin_memory={args.pin_memory} save_every={args.save_every} sampler={args.sampler}"
    )
    if train_sampler_summary is not None:
        print("weighted_sampler_summary=" + json.dumps(train_sampler_summary, ensure_ascii=False))

    for epoch in range(start_epoch, args.epochs + 1):
        epoch_start = time.perf_counter()
        train_loss = train_one_epoch(
            torch=torch,
            model=model,
            optimizer=optimizer,
            scheduler=scheduler,
            scaler=scaler,
            loader=train_loader,
            device=device,
            epoch=epoch,
            log_interval=args.log_interval,
            amp_enabled=args.amp,
        )
        val_loss = evaluate_val_loss(
            torch=torch,
            model=model,
            loader=val_loader,
            device=device,
            amp_enabled=args.amp,
        )
        pred_summary = summarize_predictions(
            torch=torch,
            model=model,
            loader=val_loader,
            device=device,
            score_thresh=args.score_thresh,
            amp_enabled=args.amp,
        )
        epoch_seconds = time.perf_counter() - epoch_start
        current_lr = get_learning_rate(optimizer)

        epoch_record = {
            "epoch": epoch,
            "train_loss": train_loss,
            "val_loss_proxy": val_loss,
            "avg_val_detections_per_image": pred_summary["avg_detections_per_image"],
            "lr": current_lr,
            "epoch_seconds": epoch_seconds,
        }
        history.append(epoch_record)

        print(
            f"[epoch {epoch}] train_loss={train_loss:.4f} "
            f"val_loss_proxy={val_loss:.4f} "
            f"avg_val_dets={pred_summary['avg_detections_per_image']:.3f} "
            f"lr={current_lr:.6f} epoch_sec={epoch_seconds:.1f}"
        )

        if scheduler is not None:
            scheduler.step()

        save_checkpoint(
            path=args.output_dir / "last.pt",
            model=model,
            optimizer=optimizer,
            scheduler=scheduler,
            scaler=scaler,
            epoch=epoch,
            train_loss=train_loss,
            val_loss=val_loss,
            class_names=class_names,
            args=args,
        )
        if args.save_every > 0 and epoch % args.save_every == 0:
            save_checkpoint(
                path=args.output_dir / f"epoch_{epoch:03d}.pt",
                model=model,
                optimizer=optimizer,
                scheduler=scheduler,
                scaler=scaler,
                epoch=epoch,
                train_loss=train_loss,
                val_loss=val_loss,
                class_names=class_names,
                args=args,
            )
        if val_loss < best_val_loss:
            best_val_loss = val_loss
            save_checkpoint(
                path=args.output_dir / "best.pt",
                model=model,
                optimizer=optimizer,
                scheduler=scheduler,
                scaler=scaler,
                epoch=epoch,
                train_loss=train_loss,
                val_loss=val_loss,
                class_names=class_names,
                args=args,
            )

        with (args.output_dir / "history.json").open("w", encoding="utf-8") as fp:
            json.dump(history, fp, indent=2, ensure_ascii=False)
            fp.write("\n")

    print(f"Training finished. Best proxy val loss: {best_val_loss:.4f}")
    print(f"Artifacts: {args.output_dir / 'best.pt'} {args.output_dir / 'last.pt'} {args.output_dir / 'history.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
