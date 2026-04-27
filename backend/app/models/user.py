from sqlalchemy import Column, Integer, String, Boolean

from app.db.session import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    full_name = Column(String)
    email = Column(String, unique=True)
    password = Column(String)
    role = Column(String)

    phone = Column(String)  # ✅ NOVO

    neighborhood = Column(String)
    city = Column(String)
    address = Column(String)

    active = Column(Boolean, default=True)