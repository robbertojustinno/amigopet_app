import os
from datetime import datetime

import requests
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, EmailStr, Field

from app.api.orders import orders_db

router = APIRouter()


class PaymentRequest(BaseModel):
    amount: float = Field(..., gt=0)
    email: EmailStr
    order_id: int


def _asaas_base_url() -> str:
    env = os.getenv("ASAAS_ENV", "production").strip().lower()
    base_url = os.getenv("ASAAS_BASE_URL", "https://api.asaas.com/v3").strip().rstrip("/")
    if env in {"sandbox", "test", "testing"} and "sandbox" not in base_url:
        return "https://api-sandbox.asaas.com/v3"
    return base_url


def _asaas_headers() -> dict:
    api_key = os.getenv("ASAAS_API_KEY", "").strip()
    if not api_key:
        raise HTTPException(status_code=500, detail="ASAAS_API_KEY não configurada no Render.")
    return {
        "access_token": api_key,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def _asaas_request(method: str, path: str, **kwargs) -> dict:
    response = requests.request(method, f"{_asaas_base_url()}{path}", headers=_asaas_headers(), timeout=30, **kwargs)
    try:
        data = response.json()
    except Exception:
        data = {"raw": response.text}
    if response.status_code >= 400:
        raise HTTPException(status_code=400, detail=data.get("errors") or data.get("message") or data)
    return data


@router.post("/pay")
def create_payment(payload: PaymentRequest):
    if payload.order_id not in orders_db:
        raise HTTPException(status_code=404, detail="Pedido não encontrado")

    customer = _asaas_request("POST", "/customers", json={
        "name": "Cliente AmigoPet",
        "email": payload.email,
    })

    payment = _asaas_request("POST", "/payments", json={
        "customer": customer["id"],
        "billingType": "PIX",
        "value": float(payload.amount),
        "dueDate": datetime.utcnow().date().isoformat(),
        "description": f"Pedido #{payload.order_id}",
        "externalReference": str(payload.order_id),
    })

    pix = _asaas_request("GET", f"/payments/{payment['id']}/pixQrCode")

    orders_db[payload.order_id]["payment_id"] = payment.get("id")
    orders_db[payload.order_id]["payment_provider"] = "asaas"

    return {
        "payment_id": payment.get("id"),
        "provider": "asaas",
        "qr_code": pix.get("payload"),
        "qr_code_base64": pix.get("encodedImage"),
        "expiration_date": pix.get("expirationDate"),
        "link_pagamento": payment.get("invoiceUrl"),
    }


@router.get("/status/{payment_id}")
def check_payment(payment_id: str):
    data = _asaas_request("GET", f"/payments/{payment_id}")
    status = (data.get("status") or "").upper()
    approved = status in {"RECEIVED", "CONFIRMED", "RECEIVED_IN_CASH"}

    for order_id, order in orders_db.items():
        if str(order.get("payment_id")) == str(payment_id):
            if approved:
                order["status"] = "paid"

    return {
        "provider": "asaas",
        "status": status,
        "approved": approved,
    }


@router.post("/asaas/webhook")
async def asaas_webhook(request: Request):
    token = os.getenv("ASAAS_WEBHOOK_TOKEN", "").strip()
    if token and request.headers.get("asaas-access-token", "") != token:
        raise HTTPException(status_code=401, detail="Token do webhook Asaas inválido.")

    body = await request.json()
    payment = body.get("payment") or {}
    payment_id = payment.get("id")
    status = (payment.get("status") or "").upper()
    event = body.get("event") or ""

    if payment_id and (status in {"RECEIVED", "CONFIRMED", "RECEIVED_IN_CASH"} or event in {"PAYMENT_RECEIVED", "PAYMENT_CONFIRMED"}):
        for order_id, order in orders_db.items():
            if str(order.get("payment_id")) == str(payment_id):
                order["status"] = "paid"

    return {"ok": True, "provider": "asaas"}
