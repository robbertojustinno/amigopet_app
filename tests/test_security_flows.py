from __future__ import annotations

import pytest
from starlette.requests import Request
from starlette.websockets import WebSocketDisconnect

from conftest import auth_headers, csrf_headers, login, register_client, register_walker


class FakeRedisPipeline:
    def __init__(self, client):
        self.client = client
        self.commands = []

    def incr(self, key):
        self.commands.append(("incr", key))
        return self

    def expire(self, key, seconds):
        self.commands.append(("expire", key, seconds))
        return self

    def execute(self):
        results = []
        for command in self.commands:
            if command[0] == "incr":
                key = command[1]
                self.client.values[key] = self.client.values.get(key, 0) + 1
                results.append(self.client.values[key])
            elif command[0] == "expire":
                _, key, seconds = command
                self.client.ttls[key] = seconds
                results.append(True)
        return results


class FakeRedis:
    def __init__(self):
        self.values = {}
        self.ttls = {}

    def pipeline(self, transaction=True):
        assert transaction is True
        return FakeRedisPipeline(self)

    def ttl(self, key):
        return self.ttls.get(key, -1)


class BrokenRedis:
    def pipeline(self, transaction=True):
        raise RuntimeError("redis indisponivel")


def fake_request(ip: str = "203.0.113.10") -> Request:
    return Request({
        "type": "http",
        "method": "POST",
        "path": "/test",
        "headers": [(b"x-forwarded-for", ip.encode("utf-8"))],
        "client": (ip, 12345),
    })


def pet_payload(owner_id: int, name: str = "Bolt") -> dict:
    return {
        "owner_id": owner_id,
        "name": name,
        "species": "Cachorro",
        "breed": "SRD",
        "size": "Médio",
        "age": "2 anos",
        "photo": "https://api.dicebear.com/8.x/bottts/svg?seed=bolt",
        "notes": "Dócil",
        "dog_count": 1,
    }


def create_pet(client, owner_id: int, headers: dict[str, str], name: str = "Bolt") -> dict:
    response = client.post("/api/pets", json=pet_payload(owner_id, name), headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def create_walk(client, client_id: int, pet_id: int, headers: dict[str, str], walker_id: int | None = None) -> dict:
    response = client.post("/api/walks", json={
        "client_id": client_id,
        "walker_id": walker_id,
        "pet_id": pet_id,
        "address": "Rua Teste, 123",
        "pickup_lat": -22.58,
        "pickup_lng": -43.18,
        "duration_minutes": 30,
        "dogs_count": 1,
        "notes": "Passeio teste",
    }, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def make_paid_walk(app_module, db, client_id: int, walker_id: int | None = None, pet_id: int | None = None):
    walk = app_module.WalkRequest(
        client_id=client_id,
        walker_id=walker_id,
        pet_id=pet_id,
        address="Rua Teste, 123",
        status="convite_enviado",
        payment_status="pago",
        estimated_price=30.0,
        mp_payment_id="pay_state_test",
    )
    db.add(walk)
    db.commit()
    db.refresh(walk)
    return walk


def test_auth_session_register_and_public_admin_creation_is_blocked(client):
    user = register_client(client, "public-admin-role@example.com", role="admin")
    assert user["role"] == "client"
    assert "password_hash" not in user

    session = client.get("/api/auth/session/current")
    assert session.status_code == 200
    assert session.json()["email"] == "public-admin-role@example.com"

    client.post("/api/auth/logout", headers=csrf_headers(client))
    assert client.get("/api/auth/session/current").status_code == 401


def test_google_session_takeover_endpoint_is_not_available(client):
    response = client.get("/api/auth/google/session/1")
    assert response.status_code in {404, 405}


def test_admin_endpoints_require_real_admin_role(client):
    assert client.get("/api/admin/payout-settings").status_code == 401

    _, client_headers = auth_headers(client, "cliente@amigopet.com")
    assert client.get("/api/admin/payout-settings").status_code == 403
    assert client.post("/api/admin/pricing", json={
        "price_30": 30,
        "price_45": 40,
        "price_60": 50,
        "extra_dog": 10,
    }, headers=client_headers).status_code == 403

    login(client, "admin@amigopet.com")
    admin_headers = csrf_headers(client)
    assert client.get("/api/admin/payout-settings").status_code == 200
    response = client.post("/api/admin/pricing", json={
        "price_30": 31,
        "price_45": 41,
        "price_60": 51,
        "extra_dog": 11,
    }, headers=admin_headers)
    assert response.status_code == 200, response.text


def test_csrf_required_for_cookie_authenticated_state_changes(client):
    user, headers = auth_headers(client, "cliente@amigopet.com")

    without_csrf = client.post("/api/pets", json=pet_payload(user["id"], "Sem CSRF"))
    assert without_csrf.status_code == 403

    with_csrf = client.post("/api/pets", json=pet_payload(user["id"], "Com CSRF"), headers=headers)
    assert with_csrf.status_code == 200, with_csrf.text


def test_rate_limit_uses_redis_atomic_pipeline_when_configured(app_module, monkeypatch):
    fake_redis = FakeRedis()
    monkeypatch.setattr(app_module, "REDIS_URL", "redis://test")
    monkeypatch.setattr(app_module, "RATE_LIMIT_REDIS_CLIENT", fake_redis)

    request = fake_request()
    app_module.enforce_rate_limit(request, "unit_scope", 2, 60, "subject")
    app_module.enforce_rate_limit(request, "unit_scope", 2, 60, "subject")

    key = app_module.rate_limit_key(request, "unit_scope", "subject")
    assert fake_redis.values[key] == 2
    assert fake_redis.ttls[key] == 60

    with pytest.raises(app_module.HTTPException) as exc:
        app_module.enforce_rate_limit(request, "unit_scope", 2, 60, "subject")
    assert exc.value.status_code == 429
    assert exc.value.headers["Retry-After"] == "60"


def test_rate_limit_uses_memory_fallback_in_production_without_redis(app_module, monkeypatch):
    monkeypatch.setattr(app_module, "IS_PRODUCTION", True)
    monkeypatch.setattr(app_module, "REDIS_URL", "")
    app_module.RATE_LIMIT_BUCKETS.clear()
    app_module.RATE_LIMIT_FALLBACK_WARNED.clear()

    request = fake_request("203.0.113.30")
    app_module.enforce_rate_limit(request, "prod_scope", 1, 60)
    with pytest.raises(app_module.HTTPException) as exc:
        app_module.enforce_rate_limit(request, "prod_scope", 1, 60)
    assert exc.value.status_code == 429
    assert "redis_url_not_configured" in app_module.RATE_LIMIT_FALLBACK_WARNED


def test_rate_limit_uses_memory_fallback_in_production_when_redis_fails(app_module, monkeypatch):
    monkeypatch.setattr(app_module, "IS_PRODUCTION", True)
    monkeypatch.setattr(app_module, "REDIS_URL", "redis://test")
    monkeypatch.setattr(app_module, "RATE_LIMIT_REDIS_CLIENT", BrokenRedis())
    app_module.RATE_LIMIT_BUCKETS.clear()
    app_module.RATE_LIMIT_FALLBACK_WARNED.clear()

    request = fake_request("203.0.113.31")
    app_module.enforce_rate_limit(request, "prod_redis_down_scope", 1, 60)
    with pytest.raises(app_module.HTTPException) as exc:
        app_module.enforce_rate_limit(request, "prod_redis_down_scope", 1, 60)
    assert exc.value.status_code == 429
    assert "redis_error:RuntimeError" in app_module.RATE_LIMIT_FALLBACK_WARNED


def test_rate_limit_can_fallback_to_memory_outside_production(app_module, monkeypatch):
    monkeypatch.setattr(app_module, "IS_PRODUCTION", False)
    monkeypatch.setattr(app_module, "REDIS_URL", "redis://test")
    monkeypatch.setattr(app_module, "RATE_LIMIT_REDIS_CLIENT", BrokenRedis())
    app_module.RATE_LIMIT_BUCKETS.clear()
    app_module.RATE_LIMIT_FALLBACK_WARNED.clear()

    request = fake_request("203.0.113.20")
    app_module.enforce_rate_limit(request, "local_scope", 1, 60)
    with pytest.raises(app_module.HTTPException) as exc:
        app_module.enforce_rate_limit(request, "local_scope", 1, 60)
    assert exc.value.status_code == 429


def test_rate_limit_authentication_failures(client):
    statuses = [
        client.post("/api/auth/login", json={"email": "rate-limit@example.com", "password": "errada"}).status_code
        for _ in range(13)
    ]
    assert statuses[:12] == [401] * 12
    assert statuses[-1] == 429


def test_pets_are_restricted_by_owner_and_role(client):
    client_a = register_client(client, "client-a-pets@example.com")
    headers_a = csrf_headers(client)
    pet = create_pet(client, client_a["id"], headers_a, "Pet A")

    client_b = register_client(client, "client-b-pets@example.com")
    headers_b = csrf_headers(client)

    forbidden_create = client.post("/api/pets", json=pet_payload(client_a["id"], "Invasor"), headers=headers_b)
    assert forbidden_create.status_code == 403

    forbidden_list = client.get(f"/api/pets?owner_id={client_a['id']}")
    assert forbidden_list.status_code == 403

    own_list = client.get(f"/api/pets?owner_id={client_b['id']}")
    assert own_list.status_code == 200
    assert all(item["owner_id"] == client_b["id"] for item in own_list.json())

    login(client, "admin@amigopet.com")
    admin_list = client.get(f"/api/pets?owner_id={client_a['id']}")
    assert admin_list.status_code == 200
    assert any(item["id"] == pet["id"] for item in admin_list.json())


def test_walk_creation_and_visibility_are_restricted(client):
    client_user, client_headers = auth_headers(client, "cliente@amigopet.com")
    pet = client.get(f"/api/pets?owner_id={client_user['id']}").json()[0]
    walk = create_walk(client, client_user["id"], pet["id"], client_headers)

    walker_user = register_walker(client, "visibility-walker@example.com")
    walker_headers = csrf_headers(client)

    walker_create = client.post("/api/walks", json={
        "client_id": client_user["id"],
        "pet_id": pet["id"],
        "address": "Rua Teste",
    }, headers=walker_headers)
    assert walker_create.status_code == 403

    walker_view_unassigned = client.get(f"/api/walks/{walk['id']}")
    assert walker_view_unassigned.status_code == 403

    login(client, "cliente@amigopet.com")
    assert client.get(f"/api/walks/{walk['id']}").status_code == 200
    assert client.get("/api/walks").json()[0]["id"] == walk["id"]
    assert walker_user["role"] == "walker"


def test_walk_state_operations_require_walker_participation_and_payment(client, app_module, db):
    client_user, _ = auth_headers(client, "cliente@amigopet.com")
    walker = register_walker(client, "state-walker@example.com")
    other_walker = register_walker(client, "state-other-walker@example.com")
    other_headers = csrf_headers(client)

    unpaid = app_module.WalkRequest(
        client_id=client_user["id"],
        walker_id=walker["id"],
        address="Rua Teste",
        status="convite_enviado",
        payment_status="aguardando",
    )
    db.add(unpaid)
    db.commit()
    db.refresh(unpaid)

    assert client.post(f"/api/walks/{unpaid.id}/location", json={"lat": -22.5, "lng": -43.1}, headers=other_headers).status_code == 403

    login(client, "state-walker@example.com")
    walker_headers = csrf_headers(client)
    assert client.post(f"/api/walks/{unpaid.id}/accept?walker_id={walker['id']}", headers=walker_headers).status_code == 402
    assert client.post(f"/api/walks/{unpaid.id}/start", headers=walker_headers).status_code == 402

    paid = make_paid_walk(app_module, db, client_user["id"], walker["id"])
    assert client.post(f"/api/walks/{paid.id}/start", headers=walker_headers).status_code == 200
    assert client.post(f"/api/walks/{paid.id}/location", json={"lat": -22.51, "lng": -43.11}, headers=walker_headers).status_code == 200

    login(client, "cliente@amigopet.com")
    client_headers = csrf_headers(client)
    assert client.post(f"/api/walks/{paid.id}/finish", headers=client_headers).status_code == 403


def test_finish_walk_is_idempotent_and_does_not_duplicate_payout(client, app_module, db, monkeypatch):
    client_user, _ = auth_headers(client, "cliente@amigopet.com")
    walker = register_walker(client, "idempotent-finish-walker@example.com")
    walk = make_paid_walk(app_module, db, client_user["id"], walker["id"])
    calls = {"count": 0}

    def fake_transfer(db_session, walk_request):
        calls["count"] += 1
        return {"id": "tr_idempotent", "status": "PENDING"}

    monkeypatch.setattr(app_module, "create_asaas_pix_transfer_to_walker", fake_transfer)

    login(client, "idempotent-finish-walker@example.com")
    walker_headers = csrf_headers(client)
    first = client.post(f"/api/walks/{walk.id}/finish", headers=walker_headers)
    assert first.status_code == 200, first.text
    assert calls["count"] == 1

    db.refresh(walk)
    assert walk.status == "finalizado"
    assert walk.payout_transfer_id == "tr_idempotent"
    message_count = db.query(app_module.Message).filter(app_module.Message.request_id == walk.id).count()
    event_count = db.query(app_module.EventLog).filter(app_module.EventLog.walk_id == walk.id).count()

    second = client.post(f"/api/walks/{walk.id}/finish", headers=walker_headers)
    assert second.status_code == 200, second.text
    assert calls["count"] == 1
    assert second.json()["status"] == "finalizado"
    db.refresh(walk)
    assert walk.payout_transfer_id == "tr_idempotent"
    assert walk.payout_status == "pending"
    assert db.query(app_module.Message).filter(app_module.Message.request_id == walk.id).count() == message_count
    assert db.query(app_module.EventLog).filter(app_module.EventLog.walk_id == walk.id).count() == event_count


def test_public_and_contextual_responses_do_not_expose_sensitive_fields(client):
    login(client, "cliente@amigopet.com")
    client_user = client.get("/api/auth/session/current").json()
    pet = client.get(f"/api/pets?owner_id={client_user['id']}").json()[0]
    walk = create_walk(client, client_user["id"], pet["id"], csrf_headers(client))

    walker = register_walker(client, "dto-walker@example.com")
    walker_walks = client.get("/api/walks").json()
    created = next(item for item in walker_walks if item["id"] == walk["id"])
    assert "mp_payment_id" not in created
    assert "payout_transfer_id" not in created
    assert "mp_qr_code" not in created
    assert walker["role"] == "walker"

    login(client, "admin@amigopet.com")
    users = client.get("/api/users").json()
    listed_walker = next(item for item in users if item["role"] == "walker")
    assert "pix_key" not in listed_walker
    assert "document" not in listed_walker


def test_asaas_webhook_validates_token_api_payload_and_is_idempotent(client, app_module, db, monkeypatch):
    client_user, _ = auth_headers(client, "cliente@amigopet.com")
    walk = make_paid_walk(app_module, db, client_user["id"])
    walk.payment_status = "aguardando"
    walk.mp_payment_id = "pay_webhook_test"
    db.commit()
    db.refresh(walk)

    assert client.post("/api/asaas/webhook", json={"payment": {"id": "pay_webhook_test"}}).status_code == 401

    def valid_payment(payment_id: str):
        return {
            "id": payment_id,
            "status": "RECEIVED",
            "externalReference": f"walk_{walk.id}",
            "value": float(walk.estimated_price),
            "currency": "BRL",
            "customer": "cus_1",
        }

    monkeypatch.setattr(app_module, "get_mercadopago_payment", valid_payment)
    headers = {"asaas-access-token": "test-webhook-token"}
    payload = {"event": "PAYMENT_RECEIVED", "payment": {"id": "pay_webhook_test", "customer": "cus_1"}}

    first = client.post("/api/asaas/webhook", json=payload, headers=headers)
    assert first.status_code == 200, first.text
    assert first.json()["payment_status"] == "pago"
    assert first.json()["idempotent"] is False

    second = client.post("/api/asaas/webhook", json=payload, headers=headers)
    assert second.status_code == 200
    assert second.json()["idempotent"] is True

    monkeypatch.setattr(app_module, "get_mercadopago_payment", lambda payment_id: (_ for _ in ()).throw(RuntimeError("asaas down")))
    assert client.post("/api/asaas/webhook", json=payload, headers=headers).status_code == 502

    monkeypatch.setattr(app_module, "get_mercadopago_payment", lambda payment_id: {
        **valid_payment(payment_id),
        "externalReference": "walk_999999",
    })
    assert client.post("/api/asaas/webhook", json=payload, headers=headers).status_code in {400, 409}


def test_websocket_requires_authenticated_session(client):
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws"):
            pass

    login(client, "cliente@amigopet.com")
    session = (client.cookies.get("amigopet_session") or "").strip('"')
    with client.websocket_connect("/ws", headers={"cookie": f"amigopet_session={session}"}) as websocket:
        websocket.send_text('{"type":"ping"}')


def test_admin_panel_file_contains_session_validation_not_localstorage_authority():
    content = open("frontend/admin.html", encoding="utf-8").read()
    assert "/api/auth/session/current" in content
    assert "localStorage.getItem('amigopet_admin_user'" not in content
    assert "JSON.parse(localStorage.getItem" not in content
