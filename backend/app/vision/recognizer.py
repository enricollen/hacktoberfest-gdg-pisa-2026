"""Box photo → list of recognized sweets.

YOLO finds one box per sweet, each crop is embedded with CLIP and matched against the shop's
catalog in sqlite-vec (reference photos of single sweets, plus their visual descriptions).
"""

import asyncio
import logging
import time
from dataclasses import dataclass

from PIL import Image

from app.db import Database
from app.vision.detector import Detection, SweetDetector
from app.vision.embedder import ClipEmbedder

log = logging.getLogger(__name__)

CROP_MARGIN = 0.08
CANDIDATES = 5


@dataclass(slots=True)
class RecognizedSweet:
    bbox: tuple[float, float, float, float]
    det_conf: float
    product_id: int
    match_score: float


def crop(image: Image.Image, d: Detection, margin: float = CROP_MARGIN) -> Image.Image:
    dx, dy = (d.x2 - d.x1) * margin, (d.y2 - d.y1) * margin
    return image.crop(
        (
            max(0, d.x1 - dx),
            max(0, d.y1 - dy),
            min(image.width, d.x2 + dx),
            min(image.height, d.y2 + dy),
        )
    )


class SweetRecognizer:
    def __init__(
        self, detector: SweetDetector, embedder: ClipEmbedder, db: Database, image_weight: float
    ) -> None:
        self.detector = detector
        self.embedder = embedder
        self.db = db
        self.image_weight = image_weight

    async def recognize(self, image: Image.Image, shop_id: int) -> list[RecognizedSweet]:
        image = image.convert("RGB")
        started = time.perf_counter()
        # CPU-bound inference: keep the event loop free.
        detections = await asyncio.to_thread(self.detector.detect, image)
        detect_ms = (time.perf_counter() - started) * 1000
        if not detections:
            log.warning("no sweets detected in %dx%d photo", image.width, image.height)
            return []
        crops = [crop(image, d) for d in detections]
        embeddings = await asyncio.to_thread(self.embedder.embed_images, crops)
        log.info(
            "detected %d sweets in %dx%d photo (detect %.0f ms, embed %.0f ms)",
            len(detections),
            image.width,
            image.height,
            detect_ms,
            (time.perf_counter() - started) * 1000 - detect_ms,
        )

        # Score every (crop, candidate product) pair: image↔image similarity is the strong
        # signal; image↔description similarity breaks ties and covers products without photos.
        scored: list[tuple[float, int, int]] = []
        for i, emb in enumerate(embeddings):
            img_hits = dict(await self.db.knn("product_image_vec", shop_id, emb, CANDIDATES))
            txt_hits = dict(await self.db.knn("product_text_vec", shop_id, emb, CANDIDATES))
            for pid in img_hits.keys() | txt_hits.keys():
                score = (
                    self.image_weight * img_hits.get(pid, 0.0)
                    # CLIP image↔text cosine lives around 0.2–0.35: rescale to image range.
                    + (1 - self.image_weight) * min(1.0, txt_hits.get(pid, 0.0) * 3)
                )
                scored.append((score, i, pid))

        # Greedy global assignment: an assortment box holds each sweet once, so a product is
        # reused only after every product has been used (more sweets than catalog entries).
        catalog_size = len({pid for _, _, pid in scored})
        max_uses = max(1, -(-len(detections) // max(1, catalog_size)))
        assigned: dict[int, tuple[int, float]] = {}
        uses: dict[int, int] = {}
        for score, i, pid in sorted(scored, reverse=True):
            if i in assigned or uses.get(pid, 0) >= max_uses:
                continue
            assigned[i] = (pid, score)
            uses[pid] = uses.get(pid, 0) + 1

        results = []
        for i, d in enumerate(detections):
            if i not in assigned:  # more sweets than candidates: fall back to best image hit
                pid, score = max(
                    ((p, s) for s, j, p in scored if j == i),
                    key=lambda t: t[1],
                    default=(None, 0.0),
                )
                if pid is None:
                    continue
                assigned[i] = (pid, score)
            pid, score = assigned[i]
            results.append(
                RecognizedSweet(
                    bbox=(d.x1, d.y1, d.x2, d.y2),
                    det_conf=d.conf,
                    product_id=pid,
                    match_score=round(score, 4),
                )
            )
        return results
