from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.routing.schema import RouteRequest, RouteType

# ---------------------------------------------------------------------------
# SQL template
# ---------------------------------------------------------------------------
# {cost_col} is replaced at call time with either "cost" or "dynamic_cost".
# Named bind parameters (:start_lat, :start_lon, :end_lat, :end_lon) are
# passed safely via SQLAlchemy so there is no SQL injection risk.
# ---------------------------------------------------------------------------

_ROUTING_SQL = """
WITH start_node AS (
    SELECT source
    FROM svitliachok_2po_4pgr
    ORDER BY geom_way <-> ST_SetSRID(ST_MakePoint(:start_lon, :start_lat), 4326)
    LIMIT 1
),
end_node AS (
    SELECT target
    FROM svitliachok_2po_4pgr
    ORDER BY geom_way <-> ST_SetSRID(ST_MakePoint(:end_lon, :end_lat), 4326)
    LIMIT 1
)
SELECT jsonb_build_object(
    'type', 'FeatureCollection',
    'features', COALESCE(
        jsonb_agg(
            jsonb_build_object(
                'type', 'Feature',
                'geometry', ST_AsGeoJSON(e.geom_way)::jsonb,
                'properties', jsonb_build_object(
                    'id',   e.id,
                    'cost', p.cost,
                    'km',   e.km,
                    'name', e.osm_name
                )
            )
        ),
        '[]'::jsonb
    )
) AS geojson
FROM pgr_dijkstra(
    'SELECT id, source, target,
            COALESCE({cost_col}, cost) AS cost,
            COALESCE({cost_col}, cost) AS reverse_cost
     FROM svitliachok_2po_4pgr',
    (SELECT source FROM start_node),
    (SELECT target FROM end_node),
    directed := false
) AS p
JOIN svitliachok_2po_4pgr AS e ON p.edge = e.id;
"""


async def calculate_route(db: AsyncSession, request: RouteRequest) -> dict:
    """
    Execute pgr_dijkstra and return a GeoJSON FeatureCollection dict.

    * route_type == "quick"  → uses the ``cost`` column (raw OSM distance)
    * route_type == "safe"   → uses ``dynamic_cost`` (penalty-adjusted by the
                               lighting scheduler)
    """
    cost_col = "cost" if request.route_type == RouteType.quick else "dynamic_cost"

    # Safely interpolate only the column name (a whitelist value we control)
    sql = text(_ROUTING_SQL.format(cost_col=cost_col))

    try:
        result = await db.execute(
            sql,
            {
                "start_lat": request.start_lat,
                "start_lon": request.start_lon,
                "end_lat": request.end_lat,
                "end_lon": request.end_lon,
            },
        )
        row = result.one_or_none()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Routing engine error: {exc}",
        ) from exc

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No route found between the given coordinates",
        )

    return row.geojson
