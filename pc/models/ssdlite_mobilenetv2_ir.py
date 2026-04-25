from __future__ import annotations

from collections import OrderedDict
from functools import partial
from pathlib import Path
from typing import Any
import warnings

LEGACY_BRIDGE_INPUT_CONTRACT = "legacy_bridge_v1"
FIXED_NCHW_INPUT_CONTRACT = "fixed_nchw_v2"


def normalize_input_contract_name(input_contract: str | None) -> str:
    if input_contract is None or input_contract == "":
        return LEGACY_BRIDGE_INPUT_CONTRACT

    aliases = {
        "legacy": LEGACY_BRIDGE_INPUT_CONTRACT,
        "legacy_bridge": LEGACY_BRIDGE_INPUT_CONTRACT,
        "legacy_bridge_v1": LEGACY_BRIDGE_INPUT_CONTRACT,
        "fixed": FIXED_NCHW_INPUT_CONTRACT,
        "fixed_nchw": FIXED_NCHW_INPUT_CONTRACT,
        "fixed_nchw_v2": FIXED_NCHW_INPUT_CONTRACT,
    }
    normalized = aliases.get(str(input_contract).strip().lower())
    if normalized is None:
        raise ValueError(f"Unsupported input contract: {input_contract}")
    return normalized


def get_ssd_fixed_size_from_contract(
    input_width: int,
    input_height: int,
    input_contract: str | None,
) -> tuple[int, int]:
    contract = normalize_input_contract_name(input_contract)
    if contract == LEGACY_BRIDGE_INPUT_CONTRACT:
        # Legacy bridge bug: size was passed to torchvision SSD as (height, width),
        # even though SSD expects (width, height).
        return (input_height, input_width)

    # Fixed contract: keep the public NCHW tensor meaning explicit.
    # For input tensor shape 1x1x128x160, H=128 and W=160, so SSD fixed_size must be (160, 128).
    return (input_width, input_height)


def is_future_fixed_input_contract(input_contract: str | None) -> bool:
    return normalize_input_contract_name(input_contract) == FIXED_NCHW_INPUT_CONTRACT


def _require_training_stack() -> tuple[Any, Any, Any]:
    try:
        import torch
        from torch import nn
        import torchvision
    except ImportError as exc:  # pragma: no cover - runtime dependency
        raise RuntimeError(
            "Torch and torchvision are required for SSDLite-MobileNetV2 training/export."
        ) from exc
    return torch, nn, torchvision


def _convert_first_conv_to_grayscale(backbone: Any, use_pretrained_weights: bool) -> None:
    torch, nn, _ = _require_training_stack()

    first_block = backbone.features[0]
    old_conv = first_block[0]
    new_conv = nn.Conv2d(
        1,
        old_conv.out_channels,
        kernel_size=old_conv.kernel_size,
        stride=old_conv.stride,
        padding=old_conv.padding,
        dilation=old_conv.dilation,
        groups=old_conv.groups,
        bias=old_conv.bias is not None,
    )

    with torch.no_grad():
        if use_pretrained_weights:
            new_conv.weight.copy_(old_conv.weight.mean(dim=1, keepdim=True))
            if old_conv.bias is not None and new_conv.bias is not None:
                new_conv.bias.copy_(old_conv.bias)
        else:
            nn.init.kaiming_normal_(new_conv.weight, mode="fan_out")
            if new_conv.bias is not None:
                nn.init.zeros_(new_conv.bias)

    first_block[0] = new_conv


def _prediction_block(in_channels: int, out_channels: int, kernel_size: int, norm_layer: Any) -> Any:
    _, nn, torchvision = _require_training_stack()
    from torchvision.ops.misc import Conv2dNormActivation

    return nn.Sequential(
        Conv2dNormActivation(
            in_channels,
            in_channels,
            kernel_size=kernel_size,
            groups=in_channels,
            norm_layer=norm_layer,
            activation_layer=nn.ReLU6,
        ),
        nn.Conv2d(in_channels, out_channels, 1),
    )


def _extra_block(in_channels: int, out_channels: int, norm_layer: Any) -> Any:
    _, nn, torchvision = _require_training_stack()
    from torchvision.ops.misc import Conv2dNormActivation

    intermediate_channels = out_channels // 2
    activation = nn.ReLU6
    return nn.Sequential(
        Conv2dNormActivation(
            in_channels,
            intermediate_channels,
            kernel_size=1,
            norm_layer=norm_layer,
            activation_layer=activation,
        ),
        Conv2dNormActivation(
            intermediate_channels,
            intermediate_channels,
            kernel_size=3,
            stride=2,
            groups=intermediate_channels,
            norm_layer=norm_layer,
            activation_layer=activation,
        ),
        Conv2dNormActivation(
            intermediate_channels,
            out_channels,
            kernel_size=1,
            norm_layer=norm_layer,
            activation_layer=activation,
        ),
    )


def _normal_init(module: Any) -> None:
    torch, nn, _ = _require_training_stack()
    for layer in module.modules():
        if isinstance(layer, nn.Conv2d):
            torch.nn.init.normal_(layer.weight, mean=0.0, std=0.03)
            if layer.bias is not None:
                torch.nn.init.constant_(layer.bias, 0.0)


class SSDLiteHeadV2(_require_training_stack()[1].Module):
    def __init__(self, in_channels: list[int], num_anchors: list[int], num_classes: int, norm_layer: Any) -> None:
        _, nn, _ = _require_training_stack()
        from torchvision.models.detection.ssd import SSDScoringHead

        class SSDLiteClassificationHead(SSDScoringHead):
            def __init__(self, channels: list[int], anchors: list[int], classes: int, norm: Any):
                cls_logits = nn.ModuleList()
                for ch, anc in zip(channels, anchors):
                    cls_logits.append(_prediction_block(ch, classes * anc, 3, norm))
                _normal_init(cls_logits)
                super().__init__(cls_logits, classes)

        class SSDLiteRegressionHead(SSDScoringHead):
            def __init__(self, channels: list[int], anchors: list[int], norm: Any):
                bbox_reg = nn.ModuleList()
                for ch, anc in zip(channels, anchors):
                    bbox_reg.append(_prediction_block(ch, 4 * anc, 3, norm))
                _normal_init(bbox_reg)
                super().__init__(bbox_reg, 4)

        super().__init__()
        self.classification_head = SSDLiteClassificationHead(in_channels, num_anchors, num_classes, norm_layer)
        self.regression_head = SSDLiteRegressionHead(in_channels, num_anchors, norm_layer)

    def forward(self, x: list[Any]) -> dict[str, Any]:
        return {
            "bbox_regression": self.regression_head(x),
            "cls_logits": self.classification_head(x),
        }


class SSDLiteFeatureExtractorMobileNetV2(_require_training_stack()[1].Module):
    def __init__(
        self,
        backbone: Any,
        split_index: int,
        norm_layer: Any,
        width_mult: float = 1.0,
        min_depth: int = 16,
    ) -> None:
        super().__init__()
        _, nn, _ = _require_training_stack()

        self.features = nn.Sequential(
            nn.Sequential(*backbone[:split_index]),
            nn.Sequential(*backbone[split_index:]),
        )

        get_depth = lambda d: max(min_depth, int(d * width_mult))  # noqa: E731
        extra = nn.ModuleList(
            [
                _extra_block(backbone[-1].out_channels, get_depth(512), norm_layer),
                _extra_block(get_depth(512), get_depth(256), norm_layer),
                _extra_block(get_depth(256), get_depth(256), norm_layer),
                _extra_block(get_depth(256), get_depth(128), norm_layer),
            ]
        )
        _normal_init(extra)
        self.extra = extra

    def forward(self, x: Any) -> Any:
        outputs = []
        for block in self.features:
            x = block(x)
            outputs.append(x)
        for block in self.extra:
            x = block(x)
            outputs.append(x)
        return OrderedDict((str(i), v) for i, v in enumerate(outputs))


def _mobilenet_v2_ssdlite_extractor(backbone: Any, trainable_layers: int, norm_layer: Any, width_mult: float) -> Any:
    backbone = backbone.features
    stage_indices = [0] + [i for i, b in enumerate(backbone) if getattr(b, "_is_cn", False)] + [len(backbone) - 1]
    num_stages = len(stage_indices)
    if not 0 <= trainable_layers <= num_stages:
        raise ValueError(f"trainable_layers should be in [0, {num_stages}], got {trainable_layers}")

    freeze_before = len(backbone) if trainable_layers == 0 else stage_indices[num_stages - trainable_layers]
    for block in backbone[:freeze_before]:
        for parameter in block.parameters():
            parameter.requires_grad_(False)

    split_index = stage_indices[-2]
    return SSDLiteFeatureExtractorMobileNetV2(backbone, split_index, norm_layer, width_mult=width_mult)


def _retrieve_out_channels_gray(backbone: Any, input_height: int, input_width: int) -> list[int]:
    torch, _, _ = _require_training_stack()
    was_training = backbone.training
    backbone.eval()
    with torch.no_grad():
        dummy = torch.zeros((1, 1, input_height, input_width), dtype=torch.float32)
        outputs = backbone(dummy)
    if was_training:
        backbone.train()
    return [tensor.shape[1] for tensor in outputs.values()]


def build_ssdlite_mobilenetv2_ir(
    num_classes_with_background: int,
    input_width: int = 160,
    input_height: int = 128,
    width_mult: float = 0.35,
    input_contract: str = FIXED_NCHW_INPUT_CONTRACT,
    pretrained_backbone: bool = True,
    trainable_backbone_layers: int = 6,
    score_thresh: float = 0.20,
    nms_thresh: float = 0.45,
    detections_per_img: int = 50,
) -> Any:
    torch, nn, torchvision = _require_training_stack()
    from torchvision.models import MobileNet_V2_Weights, mobilenet_v2
    from torchvision.models.detection.anchor_utils import DefaultBoxGenerator
    from torchvision.models.detection.ssd import SSD

    if pretrained_backbone and width_mult != 1.0:
        warnings.warn(
            "ImageNet pretrained MobileNetV2 weights in torchvision are only available for width_mult=1.0. "
            "Falling back to random backbone initialization for width_mult != 1.0.",
            stacklevel=2,
        )
        pretrained_backbone = False

    weights = MobileNet_V2_Weights.IMAGENET1K_V1 if pretrained_backbone else None
    norm_layer = partial(nn.BatchNorm2d, eps=0.001, momentum=0.03)

    backbone = mobilenet_v2(weights=weights, width_mult=width_mult)
    _convert_first_conv_to_grayscale(backbone, use_pretrained_weights=weights is not None)
    backbone = _mobilenet_v2_ssdlite_extractor(backbone, trainable_backbone_layers, norm_layer, width_mult)

    input_contract = normalize_input_contract_name(input_contract)
    input_size = get_ssd_fixed_size_from_contract(input_width, input_height, input_contract)
    anchor_generator = DefaultBoxGenerator([[2, 3] for _ in range(6)], min_ratio=0.2, max_ratio=0.95)
    out_channels = _retrieve_out_channels_gray(backbone, input_height=input_height, input_width=input_width)
    num_anchors = anchor_generator.num_anchors_per_location()

    if len(out_channels) != len(num_anchors):
        raise ValueError(
            f"Backbone returned {len(out_channels)} feature maps, but anchor generator expects {len(num_anchors)}."
        )

    model = SSD(
        backbone=backbone,
        anchor_generator=anchor_generator,
        size=input_size,
        num_classes=num_classes_with_background,
        head=SSDLiteHeadV2(out_channels, num_anchors, num_classes_with_background, norm_layer),
        score_thresh=score_thresh,
        nms_thresh=nms_thresh,
        detections_per_img=detections_per_img,
        topk_candidates=100,
        image_mean=[0.5],
        image_std=[0.5],
    )
    model.input_contract = input_contract
    return model


class Batch1DetectorExportWrapper(_require_training_stack()[1].Module):
    """Wrap torchvision detection model into a single-tensor batch=1 export interface."""

    def __init__(self, detector: Any) -> None:
        _, nn, _ = _require_training_stack()
        super().__init__()
        self.detector = detector

    def forward(self, x: Any) -> tuple[Any, Any, Any]:
        outputs = self.detector([x[0]])
        det = outputs[0]
        return det["boxes"], det["scores"], det["labels"]


def extract_raw_ssd_head_outputs(detector: Any, batched_input: Any) -> tuple[Any, Any, Any]:
    """Run SSD up to raw head outputs and anchors without postprocess/NMS."""

    _, _, _ = _require_training_stack()

    images, _ = detector.transform([batched_input[0]], None)
    features = detector.backbone(images.tensors)
    if isinstance(features, dict):
        feature_list = list(features.values())
    else:
        feature_list = [features]

    head_outputs = detector.head(feature_list)
    anchors = detector.anchor_generator(images, feature_list)
    return head_outputs["bbox_regression"], head_outputs["cls_logits"], anchors[0]


class Batch1RawHeadExportWrapper(_require_training_stack()[1].Module):
    """Expose raw SSD head tensors for export-friendly deployment artifacts."""

    def __init__(self, detector: Any) -> None:
        super().__init__()
        self.detector = detector

    def forward(self, x: Any) -> tuple[Any, Any, Any]:
        return extract_raw_ssd_head_outputs(self.detector, x)


class Batch1TransformFreeRawHeadExportWrapper(_require_training_stack()[1].Module):
    """Expose raw SSD heads for an already-resized and already-normalized tensor."""

    def __init__(self, backbone: Any, head: Any, anchors_xyxy: Any) -> None:
        super().__init__()
        self.backbone = backbone
        self.head = head
        self.register_buffer("anchors_xyxy", anchors_xyxy.detach().clone())

    def forward(self, x: Any) -> tuple[Any, Any, Any]:
        features = self.backbone(x)
        feature_list = list(features.values()) if isinstance(features, dict) else [features]
        head_outputs = self.head(feature_list)
        return head_outputs["bbox_regression"], head_outputs["cls_logits"], self.anchors_xyxy


def build_transform_free_raw_head_export_wrapper(
    detector: Any,
    input_height: int,
    input_width: int,
) -> Any:
    """Build an export wrapper that bypasses torchvision's SSD transform.

    The caller is responsible for providing the tensor in the same pixel space
    that the detector backbone expects, including resize and normalization.
    """

    torch, _, _ = _require_training_stack()
    from torchvision.models.detection.image_list import ImageList

    was_training = detector.training
    detector.eval()
    with torch.no_grad():
        dummy = torch.zeros((1, 1, input_height, input_width), dtype=torch.float32)
        features = detector.backbone(dummy)
        feature_list = list(features.values()) if isinstance(features, dict) else [features]
        image_list = ImageList(dummy, [(input_height, input_width)])
        anchors = detector.anchor_generator(image_list, feature_list)[0]
    if was_training:
        detector.train()

    return Batch1TransformFreeRawHeadExportWrapper(detector.backbone, detector.head, anchors)


def save_label_map(path: str | Path, class_names: list[str]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as fp:
        for idx, name in enumerate(class_names):
            fp.write(f"{idx}:{name}\n")
