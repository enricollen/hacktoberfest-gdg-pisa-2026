"""Console + rotating file logging (backend/logs/app.log), uvicorn included.

The file is the place to look after a test run: HTTP requests with timings, every conversation
turn (what was heard, what the agent answered), LLM calls, recognition results, TTS streams and
browser-side events (microphone, transcripts, playback errors) posted to /api/client-log.
"""

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

FORMAT = "%(asctime)s.%(msecs)03d %(levelname)-7s %(name)-14s %(message)s"
DATEFMT = "%Y-%m-%d %H:%M:%S"

# Third-party loggers that are chatty at INFO.
QUIET = ("httpx", "httpcore", "google_genai", "aiosqlite", "watchfiles", "urllib3", "fastembed")


def setup_logging(log_dir: Path, level: str = "INFO") -> Path:
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "app.log"
    formatter = logging.Formatter(FORMAT, DATEFMT)

    file_handler = RotatingFileHandler(
        log_file, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    console = logging.StreamHandler()
    console.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(level)
    # Idempotent across uvicorn --reload re-imports.
    for h in list(root.handlers):
        root.removeHandler(h)
    root.addHandler(file_handler)
    root.addHandler(console)

    # Route uvicorn through our handlers (errors with tracebacks end up in the file too);
    # access logs are replaced by our own request middleware.
    for name in ("uvicorn", "uvicorn.error"):
        lg = logging.getLogger(name)
        lg.handlers.clear()
        lg.propagate = True
    access = logging.getLogger("uvicorn.access")
    access.handlers.clear()
    access.propagate = False

    for name in QUIET:
        logging.getLogger(name).setLevel(logging.WARNING)
    return log_file
