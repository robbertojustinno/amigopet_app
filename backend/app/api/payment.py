import os
import requests
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr, Field

from app.api.orders import orders_db  # 🔥 integração com pedidos

router = APIRouter()


class PaymentRequest(BaseModel):
    amount: float = Field(..., gt=0)
    email: EmailStr
    order_id: int  # 🔥 vínculo com pedido


@router.post("/pay")
def create_payment(payload: PaymentRequest):

    access_token = os.getenv("MERCADO_PAGO_ACCESS_TOKEN", "").strip()

    if not access_token:
        raise HTTPException(status_code=500, detail="Token não configurado")

    if payload.order_id not in orders_db:
        raise HTTPException(status_code=404, detail="Pedido não encontrado")

    url = "https://api.mercadopago.com/v1/payments"

    body = {
        "transaction_amount": float(payload.amount),
        "description": f"Pedido #{payload.order_id}",
        "payment_method_id": "pix",
        "payer": {
            "email": payload.email,
            "first_name": "Cliente",
            "last_name": "AmigoPet",
            "identification": {
                "type": "CPF",
                "number": "19119119100"
            }
        }
    }

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    response = requests.post(url, json=body, headers=headers)

    if response.status_code >= 400:
        raise HTTPException(status_code=500, detail=response.text)

    data = response.json()
    transaction_data = data.get("point_of_interaction", {}).get("transaction_data", {})

    # 🔥 salva vínculo
    orders_db[payload.order_id]["payment_id"] = data.get("id")

    return {
        "payment_id": data.get("id"),
        "qr_code": transaction_data.get("qr_code"),
        "qr_code_base64": transaction_data.get("qr_code_base64")
    }


@router.get("/status/{payment_id}")
def check_payment(payment_id: str):

    access_token = os.getenv("MERCADO_PAGO_ACCESS_TOKEN", "").strip()

    url = f"https://api.mercadopago.com/v1/payments/{payment_id}"

    headers = {
        "Authorization": f"Bearer {access_token}"
    }

    response = requests.get(url, headers=headers)
    data = response.json()

    status = data.get("status")

    # 🔥 atualiza pedido automaticamente
    for order_id, order in orders_db.items():
        if order.get("payment_id") == int(payment_id):
            if status == "approved":
                order["status"] = "paid"

    return {
        "status": status,
        "approved": status == "approved"
    }