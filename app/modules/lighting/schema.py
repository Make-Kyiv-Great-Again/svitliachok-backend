from pydantic import BaseModel

class DTEKStatusPayload(BaseModel):
    # Depending on what the DTEK/Yasno API returns
    group: str
    is_blackout: bool

class LocationRequest(BaseModel):
    lat: float
    lon: float
