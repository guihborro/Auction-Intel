from datetime import datetime

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from .database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relacionamento: Um utilizador pode ter muitos imóveis na watchlist
    items = relationship("Watchlist", back_populates="owner")


class Watchlist(Base):
    __tablename__ = "watchlist"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, index=True)
    district = Column(String)
    area_m2 = Column(Float)

    # NOVAS COLUNAS
    bedrooms = Column(Integer, default=0)
    parking_spaces = Column(Integer, default=0)
    bathrooms = Column(Integer, default=0)

    auction_price = Column(Float)
    ml_predicted_price = Column(Float)
    roi_potential = Column(Float)
    itbi_price = Column(Float, nullable=True)
    link = Column(String)
    image_url = Column(String, nullable=True)
    status = Column(String, default="Monitorando")

    owner_id = Column(Integer, ForeignKey("users.id"))
    owner = relationship("User", back_populates="items")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    target_url = Column(String)
    total_properties = Column(Integer)
    execution_time_sec = Column(Float)
    success_rate = Column(Float)
