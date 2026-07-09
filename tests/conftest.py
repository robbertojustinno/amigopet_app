from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient


@pytest.fixture(scope="session")
def app_module(tmp_path_factory):
    db_path = tmp_path_factory.mktemp("db") / "amigopet_test.db"
    os.environ.update({
        "APP_ENV": "testing",
        "ENV": "testing",
        "DATABASE_URL": f"sqlite:///{db_path.as_posix()}",
        "SESSION_SECRET": "test-session-secret-with-more-than-32-characters",
        "ASAAS_WEBHOOK_TOKEN": "test-webhook-token",
        "ASAAS_API_KEY": "test-asaas-key",
        "PUBLIC_BASE_URL": "https://testserver",
        "GOOGLE_CLIENT_ID": "google-client-id",
        "GOOGLE_CLIENT_SECRET": "google-client-secret",
        "GOOGLE_REDIRECT_URI": "https://testserver/api/auth/google/callback",
    })

    cfg = Config(str(Path("alembic.ini").resolve()))
    command.upgrade(cfg, "head")

    sys.modules.pop("backend.app.main", None)
    module = importlib.import_module("backend.app.main")
    module.websocket_bus.enabled = False
    return module


@pytest.fixture()
def client(app_module, monkeypatch):
    app_module.RATE_LIMIT_BUCKETS.clear()

    def fake_create_payment(walk):
        return {
            "id": f"pay_{walk.id}",
            "status": "PENDING",
            "billingType": "PIX",
            "externalReference": f"walk_{walk.id}",
            "value": float(walk.estimated_price or 0),
            "currency": "BRL",
            "customer": "cus_test",
            "pixQrCode": {"payload": "pix-code-test", "encodedImage": ""},
            "invoiceUrl": "https://asaas.example/invoice",
        }

    monkeypatch.setattr(app_module, "create_mercadopago_pix_payment", fake_create_payment)
    monkeypatch.setattr(app_module, "create_asaas_pix_transfer_to_walker", lambda db, walk: {"id": "tr_test", "status": "DONE"})

    with TestClient(app_module.app, base_url="https://testserver") as test_client:
        yield test_client


@pytest.fixture()
def db(app_module):
    session = app_module.SessionLocal()
    try:
        yield session
    finally:
        session.close()


def csrf_headers(test_client: TestClient) -> dict[str, str]:
    token = (test_client.cookies.get("amigopet_csrf") or "").strip('"')
    assert token, "CSRF cookie ausente"
    return {"x-csrf-token": token}


def login(test_client: TestClient, email: str, password: str = "123456") -> dict:
    response = test_client.post("/api/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return response.json()


def auth_headers(test_client: TestClient, email: str, password: str = "123456") -> tuple[dict, dict[str, str]]:
    user = login(test_client, email, password)
    return user, csrf_headers(test_client)


def register_client(test_client: TestClient, email: str, role: str = "client") -> dict:
    response = test_client.post("/api/auth/register", json={
        "full_name": f"Cliente {email}",
        "email": email,
        "password": "123456",
        "role": role,
        "phone": "21999990000",
        "address": "Rua Teste, 123",
        "neighborhood": "Centro",
        "city": "Magé",
    })
    assert response.status_code == 200, response.text
    return response.json()


def register_walker(test_client: TestClient, email: str) -> dict:
    response = test_client.post("/api/auth/register/walker", json={
        "full_name": f"Walker {email}",
        "email": email,
        "password": "123456",
        "phone": "21999990001",
        "photo": "https://api.dicebear.com/8.x/initials/svg?seed=walker",
        "document": "12345678900",
        "pix_key_type": "CPF",
        "pix_key": "12345678900",
        "pix_holder_name": "Walker Teste",
        "pix_holder_document": "12345678900",
        "neighborhood": "Centro",
        "city": "Magé",
    })
    assert response.status_code == 200, response.text
    return response.json()
