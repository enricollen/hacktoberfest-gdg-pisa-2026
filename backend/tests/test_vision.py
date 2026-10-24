"""Detection + recognition on the demo box photo (needs `scripts.seed_catalog` to have run)."""

import json

import pytest
from PIL import Image, ImageEnhance

from app.config import ROOT_DIR, get_settings
from app.db import Database
from app.vision.detector import SweetDetector
from app.vision.embedder import ClipEmbedder
from app.vision.recognizer import SweetRecognizer

PHOTO = ROOT_DIR / "img" / "scatola_aperta.jpg"
settings = get_settings()
pytestmark = pytest.mark.skipif(not settings.db_path.exists(), reason="catalog not seeded")


@pytest.fixture(scope="module")
def models():
    detector = SweetDetector(settings.models_dir / settings.detector_model)
    embedder = ClipEmbedder(
        settings.clip_image_model, settings.clip_text_model, settings.models_dir / "fastembed"
    )
    return detector, embedder


def expected_codes() -> list[str]:
    spec = json.loads((settings.data_dir / "seed" / "demo" / "catalog.json").read_text())
    return [p["code"] for p in sorted(spec["products"], key=lambda p: p["grid"])]


@pytest.mark.parametrize("variant", ["original", "rotated_darker"])
async def test_recognizes_all_sweets(models, variant):
    image = Image.open(PHOTO).convert("RGB")
    codes = expected_codes()
    if variant == "rotated_darker":
        image = ImageEnhance.Brightness(image.rotate(90, expand=True)).enhance(0.8)
        # 90° CCW: new cell (r, c) holds the old cell (c, 3 - r).
        codes = [codes[c * 4 + (3 - r)] for r in range(4) for c in range(4)]

    db = await Database.connect(settings.db_path)
    try:
        shop = await db.get_shop("demo")
        by_id = {p["id"]: p["code"] for p in await db.list_products(shop["id"])}
        sweets = await SweetRecognizer(*models, db, settings.match_image_weight).recognize(
            image, shop["id"]
        )
    finally:
        await db.close()

    assert len(sweets) == 16
    assert [by_id[s.product_id] for s in sweets] == codes
