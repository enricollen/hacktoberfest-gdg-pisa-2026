"""Seed a shop catalog: shop row, products, reference crops and CLIP vectors.

The demo shop has a single photo of the full box, so reference images of the single sweets are
cut from it: detections are sorted in reading order and mapped to each product's grid cell.

    uv run python -m scripts.seed_catalog            # seeds data/seed/demo
    uv run python -m scripts.seed_catalog --shop demo
"""

import argparse
import asyncio
import json
import shutil

from PIL import Image

from app.config import get_settings
from app.db import Database
from app.vision.detector import SweetDetector
from app.vision.embedder import ClipEmbedder
from app.vision.recognizer import crop


async def seed(shop_slug: str) -> None:
    settings = get_settings()
    seed_dir = settings.data_dir / "seed" / shop_slug
    spec = json.loads((seed_dir / "catalog.json").read_text())
    media_dir = settings.data_dir / "media" / shop_slug
    (media_dir / "products").mkdir(parents=True, exist_ok=True)

    shutil.copy(seed_dir / spec["shop"]["logo"], media_dir / spec["shop"]["logo"])
    db = await Database.connect(settings.db_path)
    shop_id = await db.upsert_shop(
        spec["shop"]["slug"],
        spec["shop"]["name"],
        spec["shop"]["tagline"],
        f"{shop_slug}/{spec['shop']['logo']}",
    )

    detector = SweetDetector(settings.models_dir / settings.detector_model, settings.detector_imgsz)
    embedder = ClipEmbedder(
        settings.clip_image_model, settings.clip_text_model, settings.models_dir / "fastembed"
    )

    photo = Image.open((seed_dir / spec["reference_photo"]).resolve()).convert("RGB")
    detections = detector.detect(photo)  # reading order: row by row, left to right
    products = spec["products"]
    cols = max(p["grid"][1] for p in products) + 1
    if len(detections) != len(products):
        raise SystemExit(
            f"Reference photo has {len(detections)} sweets but catalog lists {len(products)}"
        )

    by_index = {p["grid"][0] * cols + p["grid"][1]: p for p in products}
    crops = {}
    for i, det in enumerate(detections):
        product = by_index[i]
        image = crop(photo, det)
        rel = f"{shop_slug}/products/{product['code']}.jpg"
        image.save(settings.data_dir / "media" / rel, quality=92)
        product["image_path"] = rel
        crops[product["code"]] = image

    codes = [p["code"] for p in products]
    image_vecs = embedder.embed_images([crops[c] for c in codes])
    text_vecs = embedder.embed_texts([p["visual_en"] for p in products])
    for product, img_vec, txt_vec in zip(products, image_vecs, text_vecs, strict=True):
        await db.upsert_product(shop_id, product, img_vec, txt_vec)

    print(f"Seeded shop '{shop_slug}' (id={shop_id}) with {len(products)} products")
    await db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--shop", default="demo")
    asyncio.run(seed(parser.parse_args().shop))
