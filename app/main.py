"""
FastAPI application entrypoint for Svitliachok API.

Lifespan:
  - Runs Base.metadata.create_all to ensure application-managed tables exist.
  - Starts an APScheduler AsyncIOScheduler that updates dynamic_cost every 2 min.
  - Gracefully shuts down the scheduler and DB engine on exit.
"""

import logging
from contextlib import asynccontextmanager
from datetime import datetime
from typing import AsyncGenerator

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from sqlalchemy import text
from app.core.database import engine, Base, SessionLocal

# Import all ORM models so Base.metadata is fully populated before create_all
from app.modules.auth.model import User  # noqa: F401
from app.modules.business.model import Business  # noqa: F401
from app.modules.routing.model import StreetEdge  # noqa: F401

# Routers
from app.modules.auth.router import router as auth_router
from app.modules.business.router import router as business_router
from app.modules.lighting.router import router as lighting_router
from app.modules.routing.router import router as routing_router

# Lighting scheduler task
from app.modules.lighting.service import run_cost_update

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    # ── Startup ──────────────────────────────────────────────────────────
    logger.info("Starting APScheduler — lighting cost update every 2 hours")
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        run_cost_update,
        trigger="interval",
        hours=2,
        id="lighting_cost_update",
        replace_existing=True,
        next_run_time=datetime.now(),   # fire immediately on startup (non-blocking)
    )
    scheduler.start()
    logger.info("Initial lighting cost update queued (runs in background)…")

    yield  # ── Application running ──────────────────────────────────────

    # ── Shutdown ─────────────────────────────────────────────────────────
    logger.info("Shutting down scheduler…")
    scheduler.shutdown(wait=False)
    logger.info("Disposing database engine…")
    await engine.dispose()


# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Svitliachok API",
    description=(
        "Pedestrian routing based on street lighting data. "
        "Safe havens are businesses with running generators."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

# ---------------------------------------------------------------------------
# CORS — allow the standalone HTML demo and any mobile dev origin
# ---------------------------------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Router registration
# ---------------------------------------------------------------------------

API_V1 = "/api/v1"

app.include_router(auth_router,     prefix=f"{API_V1}/auth",       tags=["Auth"])
app.include_router(business_router, prefix=f"{API_V1}/businesses",  tags=["Businesses"])
app.include_router(lighting_router, prefix=f"{API_V1}/lighting",    tags=["Lighting"])
app.include_router(routing_router,  prefix=f"{API_V1}/routing",     tags=["Routing"])


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get("/health", tags=["Health"])
async def health() -> dict:
    return {"status": "ok"}

# ---------------------------------------------------------------------------
# Demo UI
# ---------------------------------------------------------------------------

@app.get("/demo", tags=["Demo"])
async def serve_demo():
    """Serves the frontend Svitliachok Demo HTML file."""
    return FileResponse("static/demo.html")