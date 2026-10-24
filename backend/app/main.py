import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from app.agent.graph import Deps, build_graph
from app.agent.llm import LLM
from app.api import router
from app.config import get_settings, google_api_keys
from app.db import Database
from app.logging_setup import setup_logging
from app.vision.detector import SweetDetector
from app.vision.embedder import ClipEmbedder
from app.vision.recognizer import SweetRecognizer
from app.voice import Voice

settings = get_settings()
LOG_FILE = setup_logging(settings.log_dir, settings.log_level)
log = logging.getLogger("app")
http_log = logging.getLogger("app.http")


@asynccontextmanager
async def lifespan(app: FastAPI):
    db = await Database.connect(settings.db_path)
    detector = SweetDetector(
        settings.models_dir / settings.detector_model,
        settings.detector_imgsz,
        settings.detector_conf,
    )
    embedder = ClipEmbedder(
        settings.clip_image_model, settings.clip_text_model, settings.models_dir / "fastembed"
    )
    api_keys = google_api_keys()
    log.info("Gemini API keys configured: %d", len(api_keys))
    llm = LLM(
        api_keys,
        settings.llm_model,
        settings.llm_thinking_level,
        settings.llm_temperature,
        settings.llm_deadline_s,
    )
    log.info(
        "startup: llm=%s thinking=%s tts=%s voice=%s detector=%s log=%s",
        settings.llm_model,
        settings.llm_thinking_level,
        settings.tts_model,
        settings.tts_voice_id,
        settings.detector_model,
        LOG_FILE,
    )
    async with AsyncSqliteSaver.from_conn_string(str(settings.checkpoint_db_path)) as saver:
        app.state.settings = settings
        app.state.db = db
        app.state.recognizer = SweetRecognizer(detector, embedder, db, settings.match_image_weight)
        app.state.voice = Voice(settings)
        app.state.graph = build_graph(Deps(llm=llm, db=db), saver)
        log.info("startup complete")
        yield
    await db.close()
    log.info("shutdown")


app = FastAPI(title="Choco Tasting API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        http_log.exception("%s %s crashed", request.method, request.url.path)
        raise
    ms = (time.perf_counter() - started) * 1000
    # Static media and the client log endpoint are noise at INFO.
    quiet = request.url.path.startswith("/media") or request.url.path == "/api/client-log"
    level = (
        logging.WARNING if response.status_code >= 400 else logging.DEBUG if quiet else logging.INFO
    )
    http_log.log(
        level, "%s %s → %d (%.0f ms)", request.method, request.url.path, response.status_code, ms
    )
    return response


app.include_router(router)
settings.data_dir.joinpath("media").mkdir(parents=True, exist_ok=True)
app.mount("/media", StaticFiles(directory=settings.data_dir / "media"), name="media")
