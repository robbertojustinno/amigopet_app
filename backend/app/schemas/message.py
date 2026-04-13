from pydantic import BaseModel, Field
from typing import Optional

class MessageCreate(BaseModel):
    walk_request_id: int
    sender_id: int
    text: str = Field(min_length=1, max_length=1000)

class MessageOut(BaseModel):
    id: int
    walk_request_id: int
    sender_id: int
    sender_name: Optional[str] = None
    sender_role: Optional[str] = None
    sender_photo: Optional[str] = None
    text: str
    created_at: str | None = None

    class Config:
        from_attributes = True
