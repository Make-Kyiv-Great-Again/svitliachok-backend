from pydantic import BaseModel

class BusinessCreate(BaseModel):
  name: str
  has_generator: bool
  lat: float
  lon: float

class BusinessResponse(BaseModel):
  id: int
  name: str
  has_generator: bool
    
  class Config:
    from_attributes = True