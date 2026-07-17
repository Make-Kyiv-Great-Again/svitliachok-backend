from fastapi import HTTPException, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.business.model import Business
from app.modules.business.schema import BusinessCreate, BusinessResponse, BusinessStatusUpdate


def _row_to_response(row: Business, lat: float, lon: float) -> BusinessResponse:
    return BusinessResponse(
        id=row.id,
        owner_id=row.owner_id,
        name=row.name,
        biz_type=row.biz_type,
        has_generator=row.has_generator,
        has_wifi=row.has_wifi,
        can_charge_phone=row.can_charge_phone,
        is_open=row.is_open,
        generator_is_running=row.generator_is_running,
        lat=lat,
        lon=lon,
    )


async def create_business(
    db: AsyncSession,
    data: BusinessCreate,
    owner_id: int,
) -> BusinessResponse:
    """Insert a new Business record and return the response DTO."""
    biz = Business(
        owner_id=owner_id,
        name=data.name,
        biz_type=data.biz_type,
        has_generator=data.has_generator,
        has_wifi=data.has_wifi,
        can_charge_phone=data.can_charge_phone,
        geom=f"SRID=4326;POINT({data.lon} {data.lat})",
    )
    db.add(biz)
    await db.commit()
    await db.refresh(biz)
    return _row_to_response(biz, lat=data.lat, lon=data.lon)


async def update_status(
    db: AsyncSession,
    business_id: int,
    data: BusinessStatusUpdate,
    current_user_id: int,
) -> BusinessResponse:
    """Update is_open / generator_is_running. Only the owner may do this."""
    result = await db.execute(select(Business).where(Business.id == business_id))
    biz: Business | None = result.scalar_one_or_none()

    if biz is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Business not found")
    if biz.owner_id != current_user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your business")

    biz.is_open = data.is_open
    biz.generator_is_running = data.generator_is_running
    await db.commit()
    await db.refresh(biz)

    # Extract coordinates using ST_X / ST_Y
    coords_q = await db.execute(
        select(
            func.ST_X(Business.geom).label("lon"),
            func.ST_Y(Business.geom).label("lat"),
        ).where(Business.id == business_id)
    )
    coords = coords_q.one()
    return _row_to_response(biz, lat=coords.lat, lon=coords.lon)


async def list_businesses(db: AsyncSession) -> list[BusinessResponse]:
    """Return all businesses with their coordinates."""
    result = await db.execute(
        select(
            Business,
            func.ST_X(Business.geom).label("lon"),
            func.ST_Y(Business.geom).label("lat"),
        )
    )
    rows = result.all()
    return [_row_to_response(row.Business, lat=row.lat, lon=row.lon) for row in rows]
