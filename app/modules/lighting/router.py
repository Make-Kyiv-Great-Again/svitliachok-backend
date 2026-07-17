from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db

router = APIRouter()


# Streets whose dynamic_cost has been penalised (i.e. they are in a blackout zone).
# We return a GeoJSON FeatureCollection so the frontend can render them directly
# on a Leaflet/Mapbox layer without any extra transformation.
_SQL_DARK_STREETS = text(
    """
    SELECT jsonb_build_object(
        'type', 'FeatureCollection',
        'features', COALESCE(
            jsonb_agg(
                jsonb_build_object(
                    'type', 'Feature',
                    'geometry',   ST_AsGeoJSON(geom_way)::jsonb,
                    'properties', jsonb_build_object(
                        'id',           id,
                        'name',         osm_name,
                        'cost',         cost,
                        'dynamic_cost', dynamic_cost,
                        'penalty',      ROUND((dynamic_cost / NULLIF(cost, 0))::numeric, 2)
                    )
                )
            ),
            '[]'::jsonb
        )
    ) AS geojson
    FROM svitliachok_2po_4pgr
    WHERE is_blackout = true
    AND ST_DWithin(
        geom_way::geography,
        ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography,
        20000
    )
    """
)


@router.get(
    "/dark-streets",
    summary="Get GeoJSON of street segments currently in a blackout / low-light zone within 20km",
)
async def get_dark_streets(
    lat: float = Query(..., description="Latitude"),
    lon: float = Query(..., description="Longitude"),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Returns a **GeoJSON FeatureCollection** containing every street edge
    within 20km whose `dynamic_cost` has been raised above its base `cost` value by
    the lighting scheduler.

    Each Feature's `properties` include:
    - `id` — edge id
    - `name` — OSM street name (may be null)
    - `cost` — base physical cost
    - `dynamic_cost` — current penalised cost
    - `penalty` — ratio `dynamic_cost / cost` (e.g. 5.0 = full blackout)
    """
    result = await db.execute(
        _SQL_DARK_STREETS,
        {"lat": lat, "lon": lon}
    )
    row = result.one_or_none()
    if row is None:
        return {"type": "FeatureCollection", "features": []}
    return row.geojson


# ---------------------------------------------------------------------------
# Point lighting check
# ---------------------------------------------------------------------------
# Finds the nearest street edge to the given coordinate and returns its
# current lighting status based on dynamic_cost / is_blackout.
# Search radius is capped at 150 m — beyond that we report "unknown".
# ---------------------------------------------------------------------------

_SQL_POINT_CHECK = text(
    """
    SELECT
        id,
        osm_name                                                          AS street_name,
        COALESCE(is_blackout, false)                                      AS is_blackout,
        ROUND(
            (COALESCE(dynamic_cost, cost) / NULLIF(cost, 0))::numeric, 2
        )                                                                 AS penalty_ratio,
        ROUND(
            ST_Distance(
                geom_way::geography,
                ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography
            )::numeric, 1
        )                                                                 AS distance_m
    FROM svitliachok_2po_4pgr
    ORDER BY geom_way <-> ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)
    LIMIT 1
    """
)

_MAX_SNAP_DISTANCE_M = 150.0


@router.get(
    "/point",
    summary="Check lighting status at a specific lat/lon",
)
async def get_point_lighting(
    lat: float = Query(..., ge=-90, le=90, description="Latitude"),
    lon: float = Query(..., ge=-180, le=180, description="Longitude"),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Returns the lighting status at the given coordinate by snapping to the
    nearest street edge within **150 m**.

    Response fields:
    - `has_light` — `true` / `false` / `null` (null = no street found nearby)
    - `source` — `"street_edge"` or `"none"`
    - `street_name` — OSM name of the nearest street, may be null
    - `distance_m` — metres to the nearest street edge
    - `penalty_ratio` — `dynamic_cost / cost`; 1.0 = no penalty, 5.0 = full blackout
    """
    result = await db.execute(_SQL_POINT_CHECK, {"lat": lat, "lon": lon})
    row = result.one_or_none()

    if row is None or row.distance_m > _MAX_SNAP_DISTANCE_M:
        return {
            "has_light": None,
            "source": "none",
            "street_name": None,
            "distance_m": float(row.distance_m) if row else None,
            "penalty_ratio": None,
        }

    return {
        "has_light": not row.is_blackout,
        "source": "street_edge",
        "street_name": row.street_name,
        "distance_m": float(row.distance_m),
        "penalty_ratio": float(row.penalty_ratio) if row.penalty_ratio else 1.0,
    }


# ---------------------------------------------------------------------------
# Street lamps within a bounding box
# ---------------------------------------------------------------------------
# Used by the demo to render lamp nodes near a built route.
# Cap is 5 000 — enough to cover any realistic pedestrian-route bbox.
# ---------------------------------------------------------------------------

_SQL_LAMPS_BBOX = text(
    """
    SELECT jsonb_build_object(
        'type', 'FeatureCollection',
        'features', COALESCE(
            jsonb_agg(
                jsonb_build_object(
                    'type',     'Feature',
                    'geometry', ST_AsGeoJSON(geom)::jsonb,
                    'properties', jsonb_build_object(
                        'id',        id,
                        'lamp_type', lamp_type
                    )
                )
            ),
            '[]'::jsonb
        )
    ) AS geojson
    FROM (
        SELECT id, geom, lamp_type
        FROM   street_lamps
        WHERE  geom && ST_MakeEnvelope(:min_lon, :min_lat, :max_lon, :max_lat, 4326)
        LIMIT  5000
    ) sub
    """
)


@router.get(
    "/lamps",
    summary="Get GeoJSON of street lamps within a bounding box",
)
async def get_lamps(
    min_lat: float = Query(..., ge=-90,  le=90,  description="South latitude"),
    min_lon: float = Query(..., ge=-180, le=180, description="West longitude"),
    max_lat: float = Query(..., ge=-90,  le=90,  description="North latitude"),
    max_lon: float = Query(..., ge=-180, le=180, description="East longitude"),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Returns a **GeoJSON FeatureCollection** of street lamp nodes that fall
    within the given bounding box, capped at **5 000** features.

    Intended use: call after a route is rendered with the route's bbox
    (from `layer.getBounds()`) to display nearby lamps on the map.
    """
    result = await db.execute(
        _SQL_LAMPS_BBOX,
        {"min_lat": min_lat, "min_lon": min_lon, "max_lat": max_lat, "max_lon": max_lon},
    )
    row = result.one_or_none()
    if row is None:
        return {"type": "FeatureCollection", "features": []}
    return row.geojson


# ---------------------------------------------------------------------------
# Lamps near a specific route path
# ---------------------------------------------------------------------------
# The frontend sends the GeoJSON features it received from /routing/path.
# PostGIS collects those LineStrings into one geometry and runs ST_DWithin
# against the street_lamps table — only lamps within `radius_m` metres of
# the actual path are returned (not just inside the bounding box).
# ---------------------------------------------------------------------------

import json as _json
from pydantic import BaseModel, Field


class LampsNearRouteRequest(BaseModel):
    features: list[dict] = Field(..., description="GeoJSON Feature objects from /routing/path")
    radius_m: float = Field(default=40.0, ge=1, le=500, description="Corridor width in metres")



@router.post(
    "/lamps-near-route",
    summary="Get street lamps within N metres of a route path",
)
async def get_lamps_near_route(
    body: LampsNearRouteRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Accepts the **GeoJSON features** returned by `POST /routing/path` and
    returns every street lamp within `radius_m` metres of the actual route
    geometry (not just its bounding box).

    - `features` — array of GeoJSON Feature objects (LineString geometries)
    - `radius_m` — corridor half-width in metres (default 40 m)
    """
    if not body.features:
        return {"type": "FeatureCollection", "features": []}

    # Embed the GeoJSON as a PostgreSQL dollar-quoted literal so SQLAlchemy
    # doesn't try to bind it as a parameter (the array can be arbitrarily large).
    features_json = _json.dumps(body.features).replace("$$", "''")
    sql = text(
        f"""
        WITH route_geom AS (
            SELECT ST_Collect(
                ARRAY(
                    SELECT ST_GeomFromGeoJSON(feat->>'geometry')
                    FROM   jsonb_array_elements($${features_json}$$::jsonb) AS feat
                    WHERE  feat->>'geometry' IS NOT NULL
                )
            ) AS geom
        )
        SELECT jsonb_build_object(
            'type', 'FeatureCollection',
            'features', COALESCE(
                jsonb_agg(
                    jsonb_build_object(
                        'type',     'Feature',
                        'geometry', ST_AsGeoJSON(sl.geom)::jsonb,
                        'properties', jsonb_build_object(
                            'id',        sl.id,
                            'lamp_type', sl.lamp_type
                        )
                    )
                ),
                '[]'::jsonb
            )
        ) AS geojson
        FROM   street_lamps sl
        CROSS  JOIN route_geom r
        WHERE  r.geom IS NOT NULL
        AND    ST_DWithin(sl.geom::geography, r.geom::geography, :radius_m)
        LIMIT  5000
        """
    )

    result = await db.execute(sql, {"radius_m": body.radius_m})
    row = result.one_or_none()
    if row is None:
        return {"type": "FeatureCollection", "features": []}
    return row.geojson
