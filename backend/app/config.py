import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
ROOT_DIR = BACKEND_DIR.parent

# Secrets are exported to the process environment, where the SDKs read them:
# - ELEVENLABS_API_KEY from ../.env.local (managed by `elevenlabs onboard`)
# - GOOGLE_API_KEY from backend/.env (read by google-genai)
load_dotenv(ROOT_DIR / ".env.local")
load_dotenv(BACKEND_DIR / ".env")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="APP_", extra="ignore")

    data_dir: Path = BACKEND_DIR / "data"
    models_dir: Path = BACKEND_DIR / "models"
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]
    default_shop: str = "demo"
    log_dir: Path = BACKEND_DIR / "logs"
    log_level: str = "INFO"

    # LLM — Gemma 4 MoE via Gemini API. thinking "minimal" keeps voice latency ~1 s to first token.
    llm_model: str = "gemma-4-26b-a4b-it"
    llm_thinking_level: str = "minimal"
    llm_temperature: float = 0.7
    llm_deadline_s: float = 20.0  # hedged requests; then the graph falls back to rules

    # Vision
    detector_model: str = "yoloe-26s-seg-pf.onnx"
    detector_imgsz: int = 640
    detector_conf: float = 0.25
    clip_image_model: str = "Qdrant/clip-ViT-B-32-vision"
    clip_text_model: str = "Qdrant/clip-ViT-B-32-text"
    # Weight of the image↔image similarity vs image↔description similarity when matching crops.
    match_image_weight: float = 0.8

    # Voice (ElevenLabs)
    tts_model: str = "eleven_flash_v2_5"
    tts_voice_id: str = "W71zT1VwIFFx3mMGH2uZ"  # MarcoTrox, native Italian; APP_TTS_VOICE_ID
    tts_language: str = "it"
    tts_output_format: str = "mp3_44100_128"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "app.sqlite"

    @property
    def checkpoint_db_path(self) -> Path:
        return self.data_dir / "checkpoints.sqlite"

    @property
    def uploads_dir(self) -> Path:
        return self.data_dir / "uploads"


def google_api_keys() -> list[str]:
    """Primary key first, then the fallbacks used when a key runs out of quota."""
    names = ("GOOGLE_API_KEY", "GOOGLE_API_KEY_FALLBACK")
    return [k for k in (os.environ.get(n, "").strip() for n in names) if k]


@lru_cache
def get_settings() -> Settings:
    return Settings()
