"""FastAPI application (Architecture Spec: backend/api/main.py).

The backend only calls `PaulouPipeline` (Decision Log D13); `core/` and
`stages/` know nothing about it. Run (from the package directory):

    uvicorn backend.api.main:create_default_app --factory --port 8000
"""

import logging
import threading
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.dependencies import AppState
from backend.api.routers import attempts, health, sentences
from backend.api.settings import Settings
from backend.api.store import SentenceStore

if TYPE_CHECKING:
    from pipeline import PaulouPipeline

logger = logging.getLogger("paulou.api")


def create_app(
    pipeline: "PaulouPipeline",
    settings: Settings,
    calibrated: bool,
    warm_up: bool = True,
) -> FastAPI:
    """`calibrated` says whether `pipeline.phone_stats` is a real table. The
    warm-up runs in a background thread so the server accepts requests at
    once and `/api/health` reports `warming_up` until the model is loaded."""
    state = AppState(
        pipeline=pipeline,
        settings=settings,
        store=SentenceStore(settings.store_capacity),
        calibrated=calibrated,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if warm_up:
            threading.Thread(target=state.warm_up, name="warm-up", daemon=True).start()
        else:
            state.ready.set()
        yield

    app = FastAPI(title="Paulou API", lifespan=lifespan)
    app.state.paulou = state
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )
    for router in (health.router, sentences.router, attempts.router):
        app.include_router(router, prefix="/api")
    return app


def create_default_app() -> FastAPI:
    from backend.api.phone_stats import load_phone_stats
    from backend.api.pipeline_factory import build_pipeline

    logging.basicConfig(level=logging.INFO)
    settings = Settings.from_env()
    calibrated = settings.phone_stats_path is not None
    phone_stats = load_phone_stats(settings.phone_stats_path) if calibrated else {}
    if not calibrated:
        logger.warning(
            "No PAULOU_PHONE_STATS_PATH: scoring uses PLACEHOLDER calibration; "
            "the API reports calibrated=false and no numeric scores (D24, D50, D53)."
        )
    pipeline = build_pipeline(settings, phone_stats)
    return create_app(pipeline, settings, calibrated=calibrated)
