from sqlalchemy import Column, Integer, String, ForeignKey, Float, DateTime, func, Text
from app.db.session import Base


class WalkRequest(Base):
    __tablename__ = "walk_requests"

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    walker_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    pet_id = Column(Integer, ForeignKey("pets.id"), nullable=True, index=True)

    pickup_address = Column(String(255), nullable=False)
    neighborhood = Column(String(100), nullable=True)
    city = Column(String(100), nullable=True)
    scheduled_at = Column(String(60), nullable=True)

    duration_minutes = Column(Integer, default=30, nullable=False)
    dog_count = Column(Integer, default=1, nullable=False)
    price = Column(Float, default=0, nullable=False)

    status = Column(String(30), default="pending", nullable=False)
    invite_expires_at = Column(DateTime(timezone=True), nullable=True)

    payment_status = Column(String(30), default="unpaid", nullable=False)
    payment_id = Column(String(80), nullable=True, index=True)
    payment_provider = Column(String(30), nullable=True, default="mercado_pago")
    payment_link = Column(Text, nullable=True)
    paid_at = Column(DateTime(timezone=True), nullable=True)
    payment_updated_at = Column(DateTime(timezone=True), nullable=True)

    notes = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)