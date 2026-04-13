from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr, Field

router = APIRouter()

orders_db = {}


class Order(BaseModel):
    user_email: EmailStr
    amount: float = Field(..., gt=0)
    description: str = "Passeio AmigoPet"


@router.post("/create")
def create_order(order: Order):
    order_id = len(orders_db) + 1

    orders_db[order_id] = {
        "id": order_id,
        "status": "pending_payment",
        "amount": float(order.amount),
        "user": order.user_email,
        "description": order.description,
        "payment_id": None,
    }

    return {
        "order_id": order_id,
        "status": "pending_payment",
        "amount": float(order.amount),
        "description": order.description,
    }


@router.post("/paid/{order_id}")
def mark_paid(order_id: int):
    if order_id not in orders_db:
        raise HTTPException(status_code=404, detail="order not found")

    orders_db[order_id]["status"] = "paid"
    return {"status": "paid", "order_id": order_id}


@router.get("/{order_id}")
def get_order(order_id: int):
    if order_id not in orders_db:
        raise HTTPException(status_code=404, detail="order not found")
    return orders_db[order_id]


@router.get("")
def list_orders(user_email: str | None = None):
    items = list(orders_db.values())

    if user_email:
      items = [item for item in items if item.get("user") == user_email]

    items.sort(key=lambda item: item["id"], reverse=True)
    return items