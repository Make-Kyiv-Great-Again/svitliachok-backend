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
