"""OpenAI CLIP ViT-B/32 (ONNX export, via fastembed) for image and text embeddings."""

from pathlib import Path

import numpy as np
from fastembed import ImageEmbedding, TextEmbedding
from PIL import Image

EMBEDDING_DIM = 512


class ClipEmbedder:
    def __init__(self, image_model: str, text_model: str, cache_dir: Path) -> None:
        self.image_model = ImageEmbedding(image_model, cache_dir=str(cache_dir))
        self.text_model = TextEmbedding(text_model, cache_dir=str(cache_dir))

    def embed_images(self, images: list[Image.Image]) -> np.ndarray:
        if not images:
            return np.zeros((0, EMBEDDING_DIM), dtype=np.float32)
        return _normalize(np.stack(list(self.image_model.embed(images))))

    def embed_texts(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, EMBEDDING_DIM), dtype=np.float32)
        return _normalize(np.stack(list(self.text_model.embed(texts))))


def _normalize(x: np.ndarray) -> np.ndarray:
    x = x.astype(np.float32)
    return x / np.linalg.norm(x, axis=1, keepdims=True).clip(min=1e-12)
