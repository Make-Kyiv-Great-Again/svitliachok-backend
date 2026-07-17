"""
Lighting service — dynamic_cost scheduler logic.

Runs every 2 hours via APScheduler (configured in main.py).

Update pipeline (single atomic transaction):

  Layer 0 — Reset
      dynamic_cost = cost, is_blackout = false for every edge.
      Clean slate so subsequent layers compose correctly.

  Layer 1 — External lighting API  (stub — all lights nominal)
      Placeholder for the real outage API (Feature 6).
      When LIGHTING_API_URL is set, outage zones will be applied here
      with dynamic_cost × 5.0, is_blackout = true.
      Currently skipped → no extra penalty from this layer.

  Layer 2 — OSM lamp density
      Any street edge whose midpoint (ST_Centroid) has no lamp within
      LAMP_RADIUS_M metres is structurally dark.
      Penalty: dynamic_cost = GREATEST(current, cost × DARK_MULTIPLIER).
      GREATEST preserves a higher penalty from Layer 1 if present.

  Layer 3 — Crowdsource override  (stub — table exists but no data yet)
      Placeholder for Feature 5.  Will adjust per-edge costs based on
      recent user light reports.  Currently skipped.

  Layer 4 — Safe-haven bonus
      Street edges within SAFE_HAVEN_RADIUS_M of a business that has
      its generator running receive a strong reward multiplier, making
      the router strongly prefer those corridors for the 'safe' route.
"""

import logging

from sqlalchemy import text

from app.core.database import SessionLocal

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tuneable constants
# ---------------------------------------------------------------------------

LAMP_RADIUS_M:       float = 30.0   # metres from edge midpoint to nearest lamp
DARK_MULTIPLIER:     float = 3.0    # penalty when no lamp within LAMP_RADIUS_M
SAFE_HAVEN_RADIUS_M: float = 100.0  # metres from edge to a running-generator biz
SAFE_HAVEN_REWARD:   float = 0.1    # multiplier for safe-haven edges (lower = preferred)

# ---------------------------------------------------------------------------
# SQL — Layer 0: Reset
# ---------------------------------------------------------------------------

_SQL_RESET = text(
    """
    UPDATE svitliachok_2po_4pgr
    SET    dynamic_cost = cost,
           is_blackout  = false
    """
)

# ---------------------------------------------------------------------------
# SQL — Layer 2: OSM lamp density
#
# For every edge whose ST_Centroid has no street lamp within LAMP_RADIUS_M:
#   • dynamic_cost = GREATEST(current dynamic_cost, cost × DARK_MULTIPLIER)
#   • is_blackout  = true
#
# GREATEST preserves a higher penalty set by Layer 1 if that layer is active.
# ST_Centroid on the edge geometry is a fast approximation; for very long
# edges the true closest point could differ, but city-block edges are short
# enough that centroid works well.
# ---------------------------------------------------------------------------

_SQL_LAMP_DENSITY = text(
    f"""
    UPDATE svitliachok_2po_4pgr AS e
    SET    dynamic_cost = GREATEST(e.dynamic_cost, e.cost * {DARK_MULTIPLIER}),
           is_blackout  = true
    WHERE  NOT EXISTS (
        SELECT 1
        FROM   street_lamps sl
        WHERE  ST_DWithin(
                   sl.geom::geography,
                   ST_Centroid(e.geom_way)::geography,
                   {LAMP_RADIUS_M}
               )
    )
    """
)

# ---------------------------------------------------------------------------
# SQL — Layer 4: Safe-haven bonus
#
# Edges near a business whose generator is running get a strong reward so
# the 'safe' routing mode strongly prefers those corridors.
# ---------------------------------------------------------------------------

_SQL_SAFE_HAVEN = text(
    f"""
    UPDATE svitliachok_2po_4pgr AS e
    SET    dynamic_cost = e.dynamic_cost * {SAFE_HAVEN_REWARD}
    WHERE  EXISTS (
        SELECT 1
        FROM   businesses b
        WHERE  b.generator_is_running = true
        AND    ST_DWithin(
                   e.geom_way::geography,
                   b.geom::geography,
                   {SAFE_HAVEN_RADIUS_M}
               )
    )
    """
)


# ---------------------------------------------------------------------------
# Scheduler entry point
# ---------------------------------------------------------------------------

async def run_cost_update() -> None:
    """
    Execute the lighting cost pipeline inside a single atomic transaction.

    Called by APScheduler every 2 hours (and once on startup).
    Opens its own DB session so it runs outside any request context.

    Pipeline:
      L0  Reset
      L1  External API stub (skipped until LIGHTING_API_URL is configured)
      L2  OSM lamp density — real data from street_lamps table
      L3  Crowdsource stub (skipped until Feature 5 is wired in)
      L4  Safe-haven bonus
    """
    logger.info("Lighting cost update starting…")
    async with SessionLocal() as db:
        try:
            async with db.begin():
                # L0 — clean slate
                await db.execute(_SQL_RESET)
                logger.debug("L0 reset done")

                # L1 — external API (stub: no outages reported)
                logger.debug("L1 external API skipped (not configured)")

                # L2 — OSM lamp density
                result = await db.execute(_SQL_LAMP_DENSITY)
                logger.info(
                    "L2 lamp density: %d dark edges marked (no lamp within %.0f m)",
                    result.rowcount,
                    LAMP_RADIUS_M,
                )

                # L3 — crowdsource (stub: table exists but no data yet)
                logger.debug("L3 crowdsource skipped (no reports yet)")

                # L4 — safe-haven bonus
                await db.execute(_SQL_SAFE_HAVEN)
                logger.debug("L4 safe-haven done")

            logger.info("Lighting cost update completed successfully")
        except Exception:
            logger.exception("Lighting cost update failed — transaction rolled back")
            raise
