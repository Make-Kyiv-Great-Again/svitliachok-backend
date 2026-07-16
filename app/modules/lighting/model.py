from sqlalchemy import Column, Integer, String, Float, DateTime
from app.core.database import Base

class BlackoutZone(Base):
    __tablename__ = "blackout_zones"

    id = Column(Integer, primary_key=True)
    # Define columns for zones, groups, status, etc.
    group_id = Column(String)
    status = Column(String)
