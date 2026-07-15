from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.schemas.business import BusinessCreate, BusinessResponse
from app.models.business import Business
from app.api.dependencies import get_db

router = APIRouter()

@router.post("/", response_model=BusinessResponse)
async def create_business(
  business_in: BusinessCreate,
  db: AsyncSession = Depends(get_db)
):
  point_wkt = f"SRID=4326;POINT({business_in.lon} {business_in.lat})"
    
  new_biz = Business(
    name=business_in.name,
    has_generator=business_in.has_generator,
    geom=point_wkt
  )
  
  db.add(new_biz)
  await db.commit()
  await db.refresh(new_biz)
    
  return new_biz