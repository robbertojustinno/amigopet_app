from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, func
from app.db.session import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    full_name = Column(String(120), nullable=False)
    email = Column(String(160), unique=True, nullable=False, index=True)
    password = Column(String(160), nullable=False)
    role = Column(String(20), nullable=False)  # client | walker
    neighborhood = Column(String(100), nullable=True)
    city = Column(String(100), nullable=True)
    address = Column(String(255), nullable=True)
    profile_photo = Column(Text, nullable=True)
    online = Column(Boolean, default=False, nullable=False)
    active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
