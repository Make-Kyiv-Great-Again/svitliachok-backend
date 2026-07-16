"""
FastAPI application entrypoint for Svitliachok API.

Lifespan:
  - Runs Base.metadata.create_all to ensure application-managed tables exist.
  - Starts an APScheduler AsyncIOScheduler that updates dynamic_cost every 2 min.
  - Gracefully shuts down the scheduler and DB engine on exit.
"""

import logging
from contextlib import asynccontextmanager
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
    logger.info("Running database migrations (create_all)…")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # -- Ensure dynamic_cost column exists on the pre-existing pgRouting table.
    # osm2po does NOT create this column, so we add it idempotently at startup.
    async with SessionLocal() as db:
        try:
            logger.info("Ensuring dynamic_cost column exists on svitliachok_2po_4pgr…")
            async with db.begin():
                # Add columns if missing
                await db.execute(text(
                    "ALTER TABLE IF EXISTS svitliachok_2po_4pgr "
                    "ADD COLUMN IF NOT EXISTS dynamic_cost float8, "
                    "ADD COLUMN IF NOT EXISTS is_blackout boolean DEFAULT false"
                ))
                # Set initial value to default cost
                await db.execute(text(
                    "UPDATE svitliachok_2po_4pgr "
                    "SET is_blackout = false WHERE is_blackout IS NULL"
                ))
            logger.info("dynamic_cost and is_blackout columns ready.")
        except Exception as e:
            logger.error(f"Failed to prepare svitliachok_2po_4pgr table: {e}")

    logger.info("Starting APScheduler — lighting cost update every 2 minutes")
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        run_cost_update,
        trigger="interval",
        minutes=2,
        id="lighting_cost_update",
        replace_existing=True,
    )
    scheduler.start()

    # Run immediately so dark-streets data is ready without waiting 2 minutes
    logger.info("Running initial lighting cost update…")
    await run_cost_update()

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
    return FileResponse("map-demo.html")