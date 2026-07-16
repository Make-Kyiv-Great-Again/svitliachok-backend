from enum import Enum

from pydantic import BaseModel, Field


class RouteType(str, Enum):
    quick = "quick"
    safe = "safe"


class RouteRequest(BaseModel):
    start_lat: float = Field(..., ge=-90, le=90)
    start_lon: float = Field(..., ge=-180, le=180)
    end_lat: float = Field(..., ge=-90, le=90)
    end_lon: float = Field(..., ge=-180, le=180)
    route_type: RouteType = RouteType.quick
