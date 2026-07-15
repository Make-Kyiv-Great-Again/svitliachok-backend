from pydantic_settings import BaseSettings

class Settings(BaseSettings):
  DATABASE_URL: str = "postgresql+asyncpg://admin:supersecretpassword@localhost:5432/safepath"

  class Config:
    env_file = ".env"

settings = Settings()