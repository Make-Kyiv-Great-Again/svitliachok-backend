from sqlalchemy import Column, Integer, String, Boolean, ForeignKey
from geoalchemy2 import Geometry

from app.core.database import Base


class Business(Base):
    __tablename__ = "businesses"

    id: int = Column(Integer, primary_key=True, index=True)
    owner_id: int = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name: str = Column(String(255), nullable=False)
    biz_type: str | None = Column(String(100), nullable=True)
    has_generator: bool = Column(Boolean, default=False, nullable=False)
    has_wifi: bool = Column(Boolean, default=False, nullable=False)
    can_charge_phone: bool = Column(Boolean, default=False, nullable=False)
    is_open: bool = Column(Boolean, default=True, nullable=False)
    generator_is_running: bool = Column(Boolean, default=False, nullable=False)
    geom = Column(Geometry("POINT", srid=4326), nullable=True)