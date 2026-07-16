from sqlalchemy import Column, Integer, String, Boolean

from app.core.database import Base


class User(Base):
    __tablename__ = "users"

    id: int = Column(Integer, primary_key=True, index=True)
    email: str = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password: str = Column(String(255), nullable=False)
    is_active: bool = Column(Boolean, default=True, nullable=False)
