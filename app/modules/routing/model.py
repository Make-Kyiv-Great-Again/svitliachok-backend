from sqlalchemy import Column, Integer, String, Float, Index, Boolean
from geoalchemy2 import Geometry

from app.core.database import Base


class StreetEdge(Base):
    """
    Maps to the pre-existing pgRouting topology table created by osm2po.
    SQLAlchemy uses this only for schema awareness; all routing queries
    are executed via raw SQL (session.execute(text(...))).
    """

    __tablename__ = "svitliachok_2po_4pgr"
    __table_args__ = (
        Index("ix_street_edge_dynamic_cost", "dynamic_cost"),
        {"extend_existing": True},  # Table already exists in DB; don't recreate
    )

    id: int = Column(Integer, primary_key=True)
    osm_name: str | None = Column(String, nullable=True)
    source: int = Column(Integer, nullable=False)
    target: int = Column(Integer, nullable=False)
    cost: float = Column(Float, nullable=False)
    reverse_cost: float = Column(Float, nullable=False)
    dynamic_cost: float | None = Column(Float, nullable=True)
    is_blackout: bool | None = Column(Boolean, nullable=True, default=False)
    geom_way = Column(Geometry("LINESTRING", srid=4326), nullable=True)
