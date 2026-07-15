from sqlalchemy import Column, Integer, String, Boolean
from geoalchemy2 import Geometry
from app.core.database import Base

class Business(Base):
    __tablename__ = "safe_businesses"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    has_generator = Column(Boolean, default=False)
    geom = Column(Geometry('POINT', srid=4326))