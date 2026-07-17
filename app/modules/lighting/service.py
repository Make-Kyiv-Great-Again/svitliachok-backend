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

import asyncio
import logging

import httpx
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
# SQL — Layer 1: External API Blackouts
# ---------------------------------------------------------------------------

_SQL_EXTERNAL_API_BLACKOUT = text(
    """
    UPDATE svitliachok_2po_4pgr
    SET    dynamic_cost = cost * 5.0,
           is_blackout  = true
    WHERE  osm_name = ANY(:dark_streets)
    """
)

# ---------------------------------------------------------------------------
# SQL — Layer 2: OSM lamp density
#
# For every edge that has no street lamp within roughly 30m:
#   • dynamic_cost = GREATEST(current dynamic_cost, cost × DARK_MULTIPLIER)
#   • is_blackout  = true
#
# GREATEST preserves a higher penalty set by Layer 1 if that layer is active.
# We use geometry ST_DWithin with 0.0003 degrees (~33m at equator, ~25m in Kyiv) 
# instead of geography/centroids to ensure it uses the GiST spatial indexes.
# ---------------------------------------------------------------------------

_SQL_LAMP_DENSITY = text(
    f"""
    UPDATE svitliachok_2po_4pgr AS e
    SET    dynamic_cost = GREATEST(e.dynamic_cost, e.cost * {DARK_MULTIPLIER})
    WHERE  NOT EXISTS (
        SELECT 1
        FROM   street_lamps sl
        WHERE  ST_DWithin(sl.geom, e.geom_way, 0.0003)
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

                # L1 — external API (DTEK live outages)
                try:
                    dark_streets = await fetch_dtek_outages()
                    if dark_streets:
                        res_l1 = await db.execute(
                            _SQL_EXTERNAL_API_BLACKOUT, 
                            {"dark_streets": list(dark_streets)}
                        )
                        logger.info(
                            "L1 external API: %d dark streets found, %d edges marked", 
                            len(dark_streets), res_l1.rowcount
                        )
                    else:
                        logger.info("L1 external API: no dark streets found (or API failed)")
                except Exception as e:
                    logger.warning("L1 external API failed unexpectedly, skipping: %s", e)

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


async def fetch_dtek_outages() -> set[str]:
    """
    Fetches DTEK live outage data from svitlo-finder.xyz for the Kyiv area.
    Because requesting the entire city at once causes the upstream server
    to timeout, we split Kyiv into a 2x2 grid and fetch them concurrently.
    
    Returns a set of street names where AT LEAST ONE building is reported
    as 'OFF' or 'DISCONNECTED'.
    """
    url = "https://svitlo-finder.xyz/api/v1/dtek/viewport"
    # Approximate bounds for the densely populated areas of Kyiv
    lat_min, lat_max = 50.35, 50.55
    lon_min, lon_max = 30.35, 30.65
    
    grid_size = 2
    tasks = []
    
    async with httpx.AsyncClient() as client:
        for i in range(grid_size):
            for j in range(grid_size):
                l_min = lat_min + (lat_max - lat_min) / grid_size * i
                l_max = lat_min + (lat_max - lat_min) / grid_size * (i + 1)
                ln_min = lon_min + (lon_max - lon_min) / grid_size * j
                ln_max = lon_min + (lon_max - lon_min) / grid_size * (j + 1)
                
                params = {
                    "lat_bottom": l_min, "lat_top": l_max,
                    "lon_left": ln_min, "lon_right": ln_max,
                    "dsoId": 902, "city": "Київ"
                }
                tasks.append(client.get(url, params=params, timeout=30.0))
        
        # return_exceptions=True prevents one timeout from blowing up the whole batch
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
    dark_streets = set()
    for res in results:
        if isinstance(res, Exception):
            logger.warning(f"DTEK API chunk request failed: {res}")
            continue
        if res.status_code != 200:
            logger.warning(f"DTEK API returned status {res.status_code}")
            continue
            
        try:
            data = res.json()
        except ValueError:
            logger.warning("DTEK API returned invalid JSON")
            continue
            
        # JSON structure: {"Street Name": {"12A": {"status": "OFF", ...}, ...}, ...}
        for street, houses in data.items():
            for house_info in houses.values():
                if house_info.get("status") in ("OFF", "DISCONNECTED"):
                    dark_streets.add(street)
                    break  # one offline building is enough to flag the street
                    
    return dark_streets

