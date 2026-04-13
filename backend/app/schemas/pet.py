from pydantic import BaseModel, Field
from typing import Optional

class PetCreate(BaseModel):
    owner_id: int
    name: str = Field(min_length=1, max_length=80)
    breed: Optional[str] = None
    size: Optional[str] = None
    notes: Optional[str] = None
    photo_url: Optional[str] = None
    dog_count: int = 1

class PetOut(BaseModel):
    id: int
    owner_id: int
    name: str
    breed: Optional[str] = None
    size: Optional[str] = None
    notes: Optional[str] = None
    photo_url: Optional[str] = None
    dog_count: int = 1

    class Config:
        from_attributes = True
