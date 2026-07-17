from pydantic import BaseModel, Field


class BusinessCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    biz_type: str | None = Field(default=None, max_length=100)
    has_generator: bool = False
    has_wifi: bool = False
    can_charge_phone: bool = False
    lat: float = Field(..., ge=-90, le=90)
    lon: float = Field(..., ge=-180, le=180)


class BusinessStatusUpdate(BaseModel):
    is_open: bool
    generator_is_running: bool


class BusinessResponse(BaseModel):
    id: int
    owner_id: int
    name: str
    biz_type: str | None
    has_generator: bool
    has_wifi: bool
    can_charge_phone: bool
    is_open: bool
    generator_is_running: bool
    lat: float
    lon: float

    model_config = {"from_attributes": True}