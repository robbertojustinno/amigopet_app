from pydantic import BaseModel, EmailStr, Field
from typing import Optional

class UserCreate(BaseModel):
    full_name: str = Field(min_length=3, max_length=120)
    email: str
    password: str = Field(min_length=4, max_length=160)
    role: str
    neighborhood: Optional[str] = None
    city: Optional[str] = None
    address: Optional[str] = None
    profile_photo: Optional[str] = None

class UserLogin(BaseModel):
    email: str
    password: str

class UserOut(BaseModel):
    id: int
    full_name: str
    email: str
    role: str
    neighborhood: Optional[str] = None
    city: Optional[str] = None
    address: Optional[str] = None
    profile_photo: Optional[str] = None
    online: bool

    class Config:
        from_attributes = True
