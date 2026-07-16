from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.modules.auth.model import User
from app.modules.business import service
from app.modules.business.schema import BusinessCreate, BusinessResponse, BusinessStatusUpdate

router = APIRouter()


@router.post(
    "/",
    response_model=BusinessResponse,
    status_code=201,
    summary="Register a new safe haven business",
)
async def create_business(
    data: BusinessCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
) -> BusinessResponse:
    return await service.create_business(db, data, owner_id=current_user.id)


@router.patch(
    "/{business_id}/status",
    response_model=BusinessResponse,
    summary="Update business open/generator status",
)
async def update_status(
    business_id: int,
    data: BusinessStatusUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
) -> BusinessResponse:
    return await service.update_status(db, business_id, data, current_user_id=current_user.id)


@router.get(
    "/",
    response_model=list[BusinessResponse],
    summary="List all registered safe haven businesses",
)
async def list_businesses(
    db: AsyncSession = Depends(get_db),
) -> list[BusinessResponse]:
    return await service.list_businesses(db)
