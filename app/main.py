from fastapi import FastAPI
from contextlib import asynccontextmanager
from app.core.database import engine, Base
from app.api.v1 import businesses

@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    yield
    
    await engine.dispose()

app = FastAPI(
    title="Svitkiachok API",
    lifespan=lifespan
)

app.include_router(businesses.router, prefix="/api/v1/businesses", tags=["Businesses"])