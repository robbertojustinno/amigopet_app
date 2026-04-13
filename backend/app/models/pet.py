from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Text, func
from app.db.session import Base

class Pet(Base):
    __tablename__ = "pets"

    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String(80), nullable=False)
    breed = Column(String(80), nullable=True)
    size = Column(String(30), nullable=True)
    notes = Column(String(255), nullable=True)
    photo_url = Column(Text, nullable=True)
    dog_count = Column(Integer, default=1, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
