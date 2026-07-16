"""
Lighting service — dynamic_cost scheduler logic.

Runs every 2 minutes via APScheduler (configured in main.py).

Update strategy (applied in a single atomic transaction):
  1. Reset:   dynamic_cost = cost for ALL edges (clean slate).
  2. Blackout ×5:
       - Geographic zone: Podil neighbourhood bounding box.
       - ID-based fallback: every edge whose id % 5 IN (1,2) — guarantees
         ~40% of streets appear dark even if the Podil bbox misses the data.
  3. Safe-haven reward ×0.5: edges within 50 m of a business where
     generator_is_running = true.
"""

import logging

from sqlalchemy import text

from app.core.database import SessionLocal

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# SQL statements (raw, parameterless — all values are literals we control)
# ---------------------------------------------------------------------------

# 1. Reset — always run first so each cycle is a clean slate.
_SQL_RESET = text(
    """
    UPDATE svitliachok_2po_4pgr
    SET    dynamic_cost = cost,
           is_blackout = false
    """
)

# 2a. Geographic blackout zone (Podil, Kyiv).
_SQL_BLACKOUT_GEO = text(
    """
    UPDATE svitliachok_2po_4pgr
    SET    dynamic_cost = cost * 5.0,
           is_blackout = true
    WHERE  geom_way && ST_MakeEnvelope(30.500, 50.460, 30.510, 50.475, 4326)
    """
)

# 2b. Geographic blackout zone (Obolon, Kyiv).
_SQL_BLACKOUT_GEO_OBOLON = text(
    """
    UPDATE svitliachok_2po_4pgr
    SET    dynamic_cost = cost * 5.0,
           is_blackout = true
    WHERE  geom_way && ST_MakeEnvelope(30.490, 50.495, 30.510, 50.510, 4326)
    """
)

# 3. Safe-haven reward — streets near a running generator get a 0.1× bonus.
_SQL_SAFE_HAVEN = text(
    """
    UPDATE svitliachok_2po_4pgr AS e
    SET    dynamic_cost = e.dynamic_cost * 0.1
    WHERE  EXISTS (
        SELECT 1
        FROM   businesses b
        WHERE  b.generator_is_running = true
        AND    ST_DWithin(
                   e.geom_way::geography,
                   b.geom::geography,
                   100         -- metres
               )
    )
    """
)


async def run_cost_update() -> None:
    """
    Execute the three-step dynamic_cost update inside a single transaction.

    Called directly by APScheduler — opens its own session so it can run
    outside of a request context.
    """
    async with SessionLocal() as db:
        try:
            async with db.begin():          # auto-commits or rolls back
                await db.execute(_SQL_RESET)
                await db.execute(_SQL_BLACKOUT_GEO)   # geographic zone (Podil)
                await db.execute(_SQL_BLACKOUT_GEO_OBOLON) # geographic zone (Obolon)
                await db.execute(_SQL_SAFE_HAVEN)
            logger.info("dynamic_cost updated successfully")
        except Exception:
            logger.exception("Failed to update dynamic_cost")
            raise
