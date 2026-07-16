from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.modules.routing import service
from app.modules.routing.schema import RouteRequest

router = APIRouter()


@router.post(
    "/path",
    summary="Calculate a pedestrian route (quick or safe)",
    response_class=JSONResponse,
)
async def get_route(
    request: RouteRequest,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """
    Returns a raw **GeoJSON FeatureCollection** with the route edges.

    - `route_type = "quick"` — shortest distance (raw OSM cost)
    - `route_type = "safe"`  — avoids dark/blackout zones (dynamic_cost)
    """
    geojson = await service.calculate_route(db, request)
    return JSONResponse(content=geojson)
