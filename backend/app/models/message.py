from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Text, func
from app.db.session import Base

class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)
    walk_request_id = Column(Integer, ForeignKey("walk_requests.id"), nullable=False, index=True)
    sender_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    sender_name = Column(String(120), nullable=True)
    sender_role = Column(String(20), nullable=True)
    sender_photo = Column(Text, nullable=True)
    text = Column(String(1000), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
