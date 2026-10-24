"""Sweet detector: prompt-free YOLOE exported to ONNX (with NMS), run on CPU via ONNX Runtime.

The prompt-free model detects generic objects with arbitrary labels ("baozi", "egg tart"...), so
labels are ignored: we keep boxes by geometry (drop the box/container and toppings, keep the
cluster of similarly-sized objects). Identification is CLIP's job.
"""

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import onnxruntime as ort
from PIL import Image


@dataclass(frozen=True, slots=True)
class Detection:
    x1: float
    y1: float
    x2: float
    y2: float
    conf: float

    @property
    def area(self) -> float:
        return max(0.0, self.x2 - self.x1) * max(0.0, self.y2 - self.y1)

    @property
    def center(self) -> tuple[float, float]:
        return (self.x1 + self.x2) / 2, (self.y1 + self.y2) / 2

    def contains_point(self, x: float, y: float) -> bool:
        return self.x1 <= x <= self.x2 and self.y1 <= y <= self.y2


class SweetDetector:
    def __init__(self, model_path: Path, imgsz: int = 640, conf: float = 0.25) -> None:
        self.imgsz = imgsz
        self.conf = conf
        self.session = ort.InferenceSession(str(model_path), providers=["CPUExecutionProvider"])
        self.input_name = self.session.get_inputs()[0].name

    def _letterbox(self, image: Image.Image) -> tuple[np.ndarray, float, float, float]:
        w, h = image.size
        scale = min(self.imgsz / w, self.imgsz / h)
        nw, nh = round(w * scale), round(h * scale)
        pad_x, pad_y = (self.imgsz - nw) / 2, (self.imgsz - nh) / 2
        canvas = Image.new("RGB", (self.imgsz, self.imgsz), (114, 114, 114))
        canvas.paste(
            image.resize((nw, nh), Image.Resampling.BILINEAR), (round(pad_x), round(pad_y))
        )
        tensor = np.asarray(canvas, dtype=np.float32).transpose(2, 0, 1)[None] / 255.0
        return tensor, scale, round(pad_x), round(pad_y)

    def detect(self, image: Image.Image) -> list[Detection]:
        image = image.convert("RGB")
        tensor, scale, pad_x, pad_y = self._letterbox(image)
        # Output 0: (1, 300, 6 + 32) = x1, y1, x2, y2, score, class, mask coefficients.
        raw = self.session.run(None, {self.input_name: tensor})[0][0]
        w, h = image.size
        dets = []
        for x1, y1, x2, y2, score in raw[:, :5]:
            if score < self.conf:
                continue
            dets.append(
                Detection(
                    x1=float(np.clip((x1 - pad_x) / scale, 0, w)),
                    y1=float(np.clip((y1 - pad_y) / scale, 0, h)),
                    x2=float(np.clip((x2 - pad_x) / scale, 0, w)),
                    y2=float(np.clip((y2 - pad_y) / scale, 0, h)),
                    conf=float(score),
                )
            )
        return filter_sweets(dets)


def iou(a: Detection, b: Detection) -> float:
    ix = max(0.0, min(a.x2, b.x2) - max(a.x1, b.x1))
    iy = max(0.0, min(a.y2, b.y2) - max(a.y1, b.y1))
    inter = ix * iy
    return inter / (a.area + b.area - inter + 1e-9)


def agnostic_nms(dets: list[Detection], iou_thr: float = 0.5) -> list[Detection]:
    """The exported NMS is per-class; the same sweet often comes back under several labels."""
    kept: list[Detection] = []
    for d in sorted(dets, key=lambda d: d.conf, reverse=True):
        if all(iou(d, k) < iou_thr for k in kept):
            kept.append(d)
    return kept


def filter_sweets(dets: list[Detection]) -> list[Detection]:
    """Keep one box per sweet: drop containers, nested parts and size outliers."""
    dets = agnostic_nms(dets)
    # Containers (the box, the tray) hold the centers of several other detections.
    dets = [d for d in dets if sum(d.contains_point(*o.center) for o in dets if o is not d) < 2]
    # Parts (a hazelnut on top of a praline) sit inside a clearly larger detection.
    dets = [
        d
        for d in dets
        if not any(o.area > 1.8 * d.area and o.contains_point(*d.center) for o in dets)
    ]
    if not dets:
        return []
    median = float(np.median([d.area for d in dets]))
    dets = [d for d in dets if 0.35 * median <= d.area <= 2.8 * median]
    # Reading order: top-to-bottom rows, then left-to-right.
    row_h = np.sqrt(median)
    return sorted(dets, key=lambda d: (round(d.center[1] / row_h), d.center[0]))
