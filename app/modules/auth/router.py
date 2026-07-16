from fastapi import APIRouter, Depends
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.modules.auth import service
from app.modules.auth.schema import Token, UserRegister, UserResponse

router = APIRouter()


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=201,
    summary="Register a new user account",
)
async def register(
    data: UserRegister,
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    user = await service.register_user(db, data)
    return user


@router.post(
    "/login",
    response_model=Token,
    summary="Log in and receive a JWT access token",
)
async def login(
    form: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
) -> Token:
    """
    Accepts `application/x-www-form-urlencoded` with **username** (email)
    and **password** fields — standard OAuth2 password flow.
    """
    user = await service.authenticate_user(db, email=form.username, password=form.password)
    token = service.issue_token(user)
    return Token(access_token=token)
