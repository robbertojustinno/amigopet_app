from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, EmailStr
from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text, create_engine, text
from sqlalchemy.orm import Session, declarative_base, relationship, sessionmaker
import requests
import smtplib
from email.message import EmailMessage
from urllib.parse import urlencode, quote

BASE_DIR = Path(__file__).resolve().parents[2]
FRONTEND_DIR = BASE_DIR / "frontend"
ASAAS_ENV = os.getenv("ASAAS_ENV", "production").strip().lower()
ASAAS_API_KEY = os.getenv("ASAAS_API_KEY", "").strip()
ASAAS_WEBHOOK_TOKEN = os.getenv("ASAAS_WEBHOOK_TOKEN", "").strip()
ASAAS_DEFAULT_CPF_CNPJ = os.getenv("ASAAS_DEFAULT_CPF_CNPJ", "").strip()
ASAAS_BASE_URL = os.getenv("ASAAS_BASE_URL", "https://api.asaas.com/v3").strip().rstrip("/")
if ASAAS_ENV in {"sandbox", "test", "testing"} and "asaas.com" in ASAAS_BASE_URL and "sandbox" not in ASAAS_BASE_URL:
    ASAAS_BASE_URL = "https://api-sandbox.asaas.com/v3"
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", os.getenv("RENDER_EXTERNAL_URL", "")).rstrip("/")
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "").strip()
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "").strip()
GOOGLE_REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI", "").strip()
if not GOOGLE_REDIRECT_URI and PUBLIC_BASE_URL:
    GOOGLE_REDIRECT_URI = f"{PUBLIC_BASE_URL}/api/auth/google/callback"
SMTP_HOST = os.getenv("SMTP_HOST", "").strip()
SMTP_PORT = int(os.getenv("SMTP_PORT", "587") or "587")
SMTP_USER = os.getenv("SMTP_USER", "").strip()
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "").strip()
SMTP_FROM = os.getenv("SMTP_FROM", SMTP_USER).strip()
SMTP_USE_TLS = str(os.getenv("SMTP_USE_TLS", "true")).lower() in ["1", "true", "yes", "sim"]

# E-mail por API HTTP (recomendado no Render).
# O SMTP pode falhar no Render com [Errno 101] Network is unreachable.
RESEND_API_KEY = os.getenv("RESEND_API_KEY", "").strip()
EMAIL_FROM = os.getenv("EMAIL_FROM", "AmigoPet <onboarding@resend.dev>").strip()
WALKER_TERMS_VERSION = os.getenv("WALKER_TERMS_VERSION", "1.0").strip() or "1.0"
CLIENT_TERMS_VERSION = os.getenv("CLIENT_TERMS_VERSION", "1.0").strip() or "1.0"

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./amigopet_v6.db")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()

app = FastAPI(title="AmigoPet V6 Uber", version="6.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    full_name = Column(String(120), nullable=False)
    email = Column(String(180), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(30), nullable=False, default="client")
    phone = Column(String(30), default="")
    photo = Column(Text, default="")
    document = Column(String(40), default="")
    pix_key_type = Column(String(30), default="")
    pix_key = Column(String(180), default="")
    pix_holder_name = Column(String(160), default="")
    pix_holder_document = Column(String(40), default="")
    address = Column(Text, default="")
    neighborhood = Column(String(120), default="")
    city = Column(String(120), default="")
    lat = Column(Float, default=-22.5884)
    lng = Column(Float, default=-43.1847)
    rating = Column(Float, default=5.0)
    available = Column(Boolean, default=True)
    bio = Column(Text, default="")
    zip_code = Column(String(20), default="")
    street = Column(String(160), default="")
    number = Column(String(30), default="")
    complement = Column(String(120), default="")
    state = Column(String(60), default="RJ")
    active = Column(Boolean, default=True, nullable=False)
    email_verified = Column(Boolean, default=True, nullable=False)
    phone_verified = Column(Boolean, default=True, nullable=False)
    verification_code_hash = Column(String(255), default="")
    verification_expires_at = Column(DateTime, nullable=True)
    verified_at = Column(DateTime, nullable=True)
    accepted_terms = Column(Boolean, default=False, nullable=False)
    accepted_terms_at = Column(DateTime, nullable=True)
    terms_version = Column(String(20), default="", nullable=False)
    accepted_terms_ip = Column(String(80), default="")
    accepted_terms_user_agent = Column(Text, default="")
    client_terms_accepted = Column(Boolean, default=False, nullable=False)
    client_terms_accepted_at = Column(DateTime, nullable=True)
    client_terms_version = Column(String(20), default="", nullable=False)
    client_terms_ip = Column(String(80), default="")
    client_terms_user_agent = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)

class Pet(Base):
    __tablename__ = "pets"
    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    name = Column(String(100), nullable=False)
    species = Column(String(60), default="Cachorro")
    breed = Column(String(100), default="")
    size = Column(String(50), default="Médio")
    age = Column(String(50), default="")
    photo = Column(Text, default="")
    notes = Column(Text, default="")
    dog_count = Column(Integer, default=1, nullable=False)
    owner = relationship("User")

class WalkRequest(Base):
    __tablename__ = "walk_requests"
    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    walker_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    pet_id = Column(Integer, ForeignKey("pets.id"), nullable=True)
    address = Column(Text, nullable=False)
    pickup_lat = Column(Float, default=-22.5884)
    pickup_lng = Column(Float, default=-43.1847)
    walker_lat = Column(Float, default=-22.5900)
    walker_lng = Column(Float, default=-43.1810)
    duration_minutes = Column(Integer, default=30)
    dogs_count = Column(Integer, default=1)
    estimated_price = Column(Float, default=25.0)
    distance_km = Column(Float, default=1.8)
    status = Column(String(40), default="pendente")
    payment_status = Column(String(40), default="aguardando")
    pix_code = Column(Text, default="")
    mp_payment_id = Column(String(80), default="")
    mp_status = Column(String(60), default="")
    mp_status_detail = Column(String(120), default="")
    mp_qr_code = Column(Text, default="")
    mp_qr_code_base64 = Column(Text, default="")
    mp_ticket_url = Column(Text, default="")
    payout_status = Column(String(40), default="aguardando", nullable=False)
    payout_transfer_id = Column(String(120), default="")
    payout_amount = Column(Float, default=0.0)
    payout_error = Column(Text, default="")
    notes = Column(Text, default="")
    expires_at = Column(DateTime, nullable=True)
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    client = relationship("User", foreign_keys=[client_id])
    walker = relationship("User", foreign_keys=[walker_id])
    pet = relationship("Pet")

class Message(Base):
    __tablename__ = "messages"
    id = Column(Integer, primary_key=True, index=True)
    request_id = Column(Integer, ForeignKey("walk_requests.id"), nullable=False)
    sender_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    text = Column(Text, nullable=False)
    message_type = Column(String(30), default="text", nullable=False)
    read_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    sender = relationship("User")

class UserNotification(Base):
    __tablename__ = "notifications"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    title = Column(String(160), nullable=False)
    body = Column(Text, default="")
    type = Column(String(60), default="system", index=True)
    link = Column(String(240), default="")
    is_read = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    user = relationship("User")

class UserRating(Base):
    __tablename__ = "ratings"
    id = Column(Integer, primary_key=True, index=True)
    walk_id = Column(Integer, ForeignKey("walk_requests.id"), nullable=False, index=True)
    rater_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    target_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    rating = Column(Integer, nullable=False)
    comment = Column(Text, default="")
    role = Column(String(30), default="")
    created_at = Column(DateTime, default=datetime.utcnow)
    walk = relationship("WalkRequest")
    rater = relationship("User", foreign_keys=[rater_id])
    target = relationship("User", foreign_keys=[target_id])

class AppSetting(Base):
    __tablename__ = "app_settings"
    key = Column(String(80), primary_key=True, index=True)
    value = Column(Text, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class RegisterIn(BaseModel):
    full_name: str
    email: EmailStr
    password: str
    role: str = "client"
    phone: str = ""
    photo: str = ""
    document: str = ""
    pix_key_type: str = ""
    pix_key: str = ""
    pix_holder_name: str = ""
    pix_holder_document: str = ""
    address: str = ""
    neighborhood: str = ""
    city: str = ""
    bio: str = ""

class LoginIn(BaseModel):
    email: EmailStr
    password: str


class PasswordResetRequestIn(BaseModel):
    email: EmailStr

class PasswordResetConfirmIn(BaseModel):
    email: EmailStr
    code: str
    new_password: str

class ClientUpdateIn(BaseModel):
    full_name: str
    phone: str = ""
    photo: str = ""
    document: str = ""
    address: str = ""
    zip_code: str = ""
    street: str = ""
    number: str = ""
    complement: str = ""
    neighborhood: str = ""
    city: str = ""
    state: str = "RJ"
    bio: str = ""

class WalkerUpdateIn(BaseModel):
    full_name: str
    phone: str = ""
    photo: str = ""
    document: str = ""
    pix_key_type: str = ""
    pix_key: str = ""
    pix_holder_name: str = ""
    pix_holder_document: str = ""
    neighborhood: str = ""
    city: str = ""
    bio: str = ""

class PetIn(BaseModel):
    owner_id: int
    name: str
    species: str = "Cachorro"
    breed: str = ""
    size: str = "Médio"
    age: str = ""
    photo: str = ""
    notes: str = ""
    dog_count: int = 1

class WalkIn(BaseModel):
    client_id: int
    walker_id: Optional[int] = None
    pet_id: Optional[int] = None
    address: str
    pickup_lat: float = -22.5884
    pickup_lng: float = -43.1847
    duration_minutes: int = 30
    dogs_count: int = 1
    notes: str = ""

class PricingIn(BaseModel):
    price_30: float = 30.0
    price_45: float = 38.0
    price_60: float = 46.0
    extra_dog: float = 9.0

class PayoutSettingsIn(BaseModel):
    walker_percent: float = 80.0
    platform_percent: float = 20.0

class MessageIn(BaseModel):
    request_id: int
    sender_id: int
    text: str
    message_type: str = "text"

class LocationIn(BaseModel):
    lat: float
    lng: float

class AvailabilityIn(BaseModel):
    available: bool = True

class RatingIn(BaseModel):
    rater_id: int
    target_id: int
    rating: int
    comment: str = ""

class ConnectionManager:
    def __init__(self):
        self.active: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active:
            self.active.remove(websocket)

    async def broadcast(self, payload: dict):
        dead = []
        for ws in self.active:
            try:
                await ws.send_json(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)

manager = ConnectionManager()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def pydantic_dump(model: BaseModel, **kwargs) -> dict:
    """Compatibilidade entre Pydantic v1 e v2."""
    if hasattr(model, "model_dump"):
        return model.model_dump(**kwargs)
    return model.dict(**kwargs)

def client_ip_from_request(request: Request) -> str:
    forwarded = (request.headers.get("x-forwarded-for") or "").split(",")[0].strip()
    if forwarded:
        return forwarded[:80]
    if request.client and request.client.host:
        return str(request.client.host)[:80]
    return ""


def hash_password(password: str) -> str:
    """Hash estável compatível com Python 3.14 no Render."""
    salt = secrets.token_hex(16)
    digest = hashlib.sha256(f"{salt}:{password}".encode("utf-8")).hexdigest()
    return f"sha256${salt}${digest}"

def verify_password(password: str, password_hash: str) -> bool:
    if not password_hash:
        return False
    if password_hash.startswith("sha256$"):
        try:
            _, salt, digest = password_hash.split("$", 2)
            candidate = hashlib.sha256(f"{salt}:{password}".encode("utf-8")).hexdigest()
            return secrets.compare_digest(candidate, digest)
        except Exception:
            return False
    return False

def user_to_dict(u: User):
    return {
        "id": u.id, "full_name": u.full_name, "email": u.email, "role": u.role,
        "phone": u.phone, "photo": u.photo, "document": u.document, "address": u.address,
        "pix_key_type": getattr(u, "pix_key_type", "") or "",
        "pix_key": getattr(u, "pix_key", "") or "",
        "pix_holder_name": getattr(u, "pix_holder_name", "") or "",
        "pix_holder_document": getattr(u, "pix_holder_document", "") or "",
        "neighborhood": u.neighborhood, "city": u.city, "lat": u.lat, "lng": u.lng,
        "rating": u.rating, "available": u.available, "bio": u.bio,
        "zip_code": u.zip_code, "street": u.street, "number": u.number,
        "complement": u.complement, "state": u.state,
        "accepted_terms": bool(getattr(u, "accepted_terms", False)),
        "accepted_terms_at": getattr(u, "accepted_terms_at", None).isoformat() if getattr(u, "accepted_terms_at", None) else None,
        "terms_version": getattr(u, "terms_version", "") or "",
        "accepted_terms_ip": getattr(u, "accepted_terms_ip", "") or "",
        "client_terms_accepted": bool(getattr(u, "client_terms_accepted", False)),
        "client_terms_accepted_at": getattr(u, "client_terms_accepted_at", None).isoformat() if getattr(u, "client_terms_accepted_at", None) else None,
        "client_terms_version": getattr(u, "client_terms_version", "") or "",
        "client_terms_ip": getattr(u, "client_terms_ip", "") or "",
    }

def pet_to_dict(p: Pet):
    return {
        "id": p.id,
        "owner_id": p.owner_id,
        "name": p.name,
        "species": p.species,
        "breed": p.breed,
        "size": p.size,
        "age": p.age,
        "photo": p.photo,
        "notes": p.notes,
        "dog_count": p.dog_count,
    }


def send_email_message(to_email: str, subject: str, body: str) -> bool:
    """Envia e-mail de recuperação.

    Prioridade:
    1) Resend por HTTPS (RESEND_API_KEY + EMAIL_FROM) — recomendado no Render.
    2) SMTP antigo como fallback, se configurado.

    Variáveis Resend:
    RESEND_API_KEY=re_...
    EMAIL_FROM=AmigoPet <onboarding@resend.dev>  # teste
    """
    # 1) Resend por HTTP/HTTPS: evita bloqueios/erros de SMTP no Render.
    if RESEND_API_KEY:
        payload = {
            "from": EMAIL_FROM or "AmigoPet <onboarding@resend.dev>",
            "to": [to_email],
            "subject": subject,
            "text": body,
        }
        try:
            res = requests.post(
                "https://api.resend.com/emails",
                headers={
                    "Authorization": f"Bearer {RESEND_API_KEY}",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                json=payload,
                timeout=30,
            )
            if 200 <= res.status_code < 300:
                print("[RESEND OK] E-mail enviado para", to_email)
                return True

            try:
                err_data = res.json()
            except Exception:
                err_data = {"raw": (res.text or "").strip()}

            print("[RESEND ERROR]", {
                "status_code": res.status_code,
                "response": err_data,
                "from": payload["from"],
                "to": to_email,
            })
            return False
        except Exception as e:
            print("[RESEND ERROR]", str(e))
            return False

    # 2) Fallback SMTP antigo.
    if not SMTP_HOST or not SMTP_USER or not SMTP_PASSWORD or not SMTP_FROM:
        print("[SMTP WARNING] SMTP não configurado e RESEND_API_KEY ausente. E-mail não enviado.")
        return False

    msg = EmailMessage()
    msg["From"] = SMTP_FROM
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.set_content(body)

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20) as server:
            if SMTP_USE_TLS:
                server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.send_message(msg)
        print("[SMTP OK] E-mail enviado para", to_email)
        return True
    except Exception as e:
        print("[SMTP ERROR]", str(e))
        return False

def make_pix_code(walk_id: int, amount: float) -> str:
    token = secrets.token_hex(8).upper()
    return f"000201-AMIGOPET-PIX-SIMULADO-ID{walk_id}-VALOR{amount:.2f}-TOKEN{token}"

DEFAULT_PRICING = {
    "price_30": 30.0,
    "price_45": 38.0,
    "price_60": 46.0,
    "extra_dog": 9.0,
}

DEFAULT_PAYOUT = {
    "walker_percent": 80.0,
    "platform_percent": 20.0,
}

def get_setting(db: Session, key: str, default: str = "") -> str:
    item = db.get(AppSetting, key)
    return item.value if item else default

def set_setting(db: Session, key: str, value: str):
    item = db.get(AppSetting, key)
    if item:
        item.value = value
        item.updated_at = datetime.utcnow()
    else:
        db.add(AppSetting(key=key, value=value))

def get_pricing_config(db: Session) -> dict:
    config = {}
    for key, default in DEFAULT_PRICING.items():
        try:
            config[key] = float(get_setting(db, key, str(default)))
        except Exception:
            config[key] = default
    return config

def get_payout_config(db: Session) -> dict:
    config = {}
    for key, default in DEFAULT_PAYOUT.items():
        try:
            value = float(get_setting(db, key, str(default)))
        except Exception:
            value = default
        config[key] = round(max(0.0, min(100.0, value)), 2)

    total = round(config["walker_percent"] + config["platform_percent"], 2)
    if total != 100.0:
        config["platform_percent"] = round(100.0 - config["walker_percent"], 2)
    return config

def calculate_walk_price(db: Session, duration_minutes: int, dogs_count: int) -> float:
    pricing = get_pricing_config(db)
    duration = int(duration_minutes or 30)
    base_by_duration = {
        30: pricing["price_30"],
        45: pricing["price_45"],
        60: pricing["price_60"],
    }
    base_price = base_by_duration.get(duration, pricing["price_30"])
    extra_dogs = max(int(dogs_count or 1) - 1, 0) * pricing["extra_dog"]
    return round(base_price + extra_dogs, 2)

def seed_pricing_settings():
    db = SessionLocal()
    try:
        for key, value in DEFAULT_PRICING.items():
            if not db.get(AppSetting, key):
                db.add(AppSetting(key=key, value=str(value)))
        db.commit()
    finally:
        db.close()

def seed_payout_settings():
    db = SessionLocal()
    try:
        for key, value in DEFAULT_PAYOUT.items():
            if not db.get(AppSetting, key):
                db.add(AppSetting(key=key, value=str(value)))
        db.commit()
    finally:
        db.close()

def _asaas_idempotency_key(prefix: str, unique_value: str) -> str:
    """
    O Asaas aceita Idempotency-Key com no máximo 48 caracteres.
    Mantemos uma chave curta e estável o suficiente para evitar erro 400.
    """
    prefix = "".join(ch for ch in str(prefix or "asaas") if ch.isalnum() or ch in "-_")[:16] or "asaas"
    digest = hashlib.sha256(str(unique_value or uuid.uuid4().hex).encode("utf-8")).hexdigest()[:24]
    return f"{prefix}-{digest}"[:48]


def asaas_headers(idempotency_key: Optional[str] = None) -> dict:
    if not ASAAS_API_KEY:
        raise RuntimeError("ASAAS_API_KEY não configurada no Render")
    headers = {
        "access_token": ASAAS_API_KEY,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    if idempotency_key:
        headers["Idempotency-Key"] = str(idempotency_key)[:48]
    return headers


def asaas_webhook_url() -> Optional[str]:
    if not PUBLIC_BASE_URL:
        return None
    return f"{PUBLIC_BASE_URL}/api/asaas/webhook"


def _only_digits(value: str) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def _asaas_response_data(res: requests.Response) -> dict:
    """Retorna resposta do Asaas com detalhes úteis para depuração no Render."""
    try:
        data = res.json()
    except Exception:
        data = {"raw": (res.text or "").strip()}
    if isinstance(data, dict):
        data.setdefault("http_status", res.status_code)
        data.setdefault("reason", getattr(res, "reason", ""))
    return data


def create_asaas_customer(walk: WalkRequest) -> str:
    if not walk.client:
        raise RuntimeError("Cliente do pedido não encontrado para criar cobrança no Asaas")

    customer_payload = {
        "name": walk.client.full_name or f"Cliente AmigoPet {walk.client_id}",
        "email": walk.client.email or f"cliente{walk.client_id}@amigopet.com.br",
    }

    phone = _only_digits(getattr(walk.client, "phone", ""))
    if phone:
        customer_payload["mobilePhone"] = phone

    cpf_cnpj = _only_digits(getattr(walk.client, "document", ""))
    if len(cpf_cnpj) not in (11, 14):
        # Produção do Asaas exige CPF/CNPJ para criar cobrança PIX.
        # Use o CPF/CNPJ salvo no cadastro do cliente. Para testes internos,
        # também é possível configurar ASAAS_DEFAULT_CPF_CNPJ no Render.
        cpf_cnpj = _only_digits(ASAAS_DEFAULT_CPF_CNPJ)
    if len(cpf_cnpj) in (11, 14):
        customer_payload["cpfCnpj"] = cpf_cnpj
    else:
        raise RuntimeError(
            "Cliente sem CPF/CNPJ válido. Informe o CPF/CNPJ no cadastro do cliente "
            "ou configure ASAAS_DEFAULT_CPF_CNPJ no Render para testes."
        )

    # Não enviamos Idempotency-Key aqui. Ela é opcional no Asaas e estava causando
    # recusas/intermitências. Para o fluxo atual do AmigoPet, criar um customer por
    # pedido é aceitável e evita travar o PIX.
    res = requests.post(
        f"{ASAAS_BASE_URL}/customers",
        json=customer_payload,
        headers=asaas_headers(),
        timeout=30,
    )
    data = _asaas_response_data(res)

    if res.status_code >= 400:
        print("[ASAAS CUSTOMER DEBUG V3]", {
            "url": f"{ASAAS_BASE_URL}/customers",
            "status_code": res.status_code,
            "reason": getattr(res, "reason", ""),
            "response_text": (res.text or "")[:1000],
            "payload_keys": list(customer_payload.keys()),
            "api_key_prefix": ASAAS_API_KEY[:12] if ASAAS_API_KEY else "",
            "env": ASAAS_ENV,
            "base_url": ASAAS_BASE_URL,
        })
        raise RuntimeError(f"Asaas recusou criação do cliente: {data}")

    customer_id = data.get("id")
    if not customer_id:
        raise RuntimeError(f"Asaas não retornou ID do cliente: {data}")
    return str(customer_id)


def create_asaas_pix_payment(walk: WalkRequest) -> dict:
    if not ASAAS_API_KEY:
        raise RuntimeError("ASAAS_API_KEY não configurada no Render")

    customer_id = create_asaas_customer(walk)
    value = float(round(walk.estimated_price or 0, 2))
    if value <= 0:
        value = 1.0

    payment_payload = {
        "customer": customer_id,
        "billingType": "PIX",
        "value": value,
        "dueDate": datetime.utcnow().date().isoformat(),
        "description": f"AmigoPet - Passeio #{walk.id}",
        "externalReference": f"walk_{walk.id}",
    }

    res = requests.post(
        f"{ASAAS_BASE_URL}/payments",
        json=payment_payload,
        headers=asaas_headers(),
        timeout=30,
    )
    payment = _asaas_response_data(res)

    if res.status_code >= 400:
        raise RuntimeError(f"Asaas recusou criação do PIX: {payment}")

    payment_id = payment.get("id")
    if not payment_id:
        raise RuntimeError(f"Asaas não retornou ID do pagamento: {payment}")

    qr_res = requests.get(
        f"{ASAAS_BASE_URL}/payments/{payment_id}/pixQrCode",
        headers=asaas_headers(),
        timeout=30,
    )
    pix = _asaas_response_data(qr_res)

    if qr_res.status_code >= 400:
        raise RuntimeError(f"Asaas criou a cobrança, mas não retornou QR Code PIX: {pix}")

    payment["pixQrCode"] = pix
    return payment


def get_asaas_payment(payment_id: str) -> dict:
    if not ASAAS_API_KEY:
        raise RuntimeError("ASAAS_API_KEY não configurada no Render")
    res = requests.get(
        f"{ASAAS_BASE_URL}/payments/{payment_id}",
        headers=asaas_headers(),
        timeout=30,
    )
    try:
        data = res.json()
    except Exception:
        data = {"raw": res.text}
    if res.status_code >= 400:
        raise RuntimeError(f"Erro ao consultar pagamento Asaas: {data}")
    return data


def validate_asaas_webhook_token(request: Request) -> bool:
    if not ASAAS_WEBHOOK_TOKEN:
        return True
    received = request.headers.get("asaas-access-token", "")
    return secrets.compare_digest(received, ASAAS_WEBHOOK_TOKEN)


def apply_asaas_payment_to_walk(walk: WalkRequest, asaas_payment: dict) -> bool:
    before = walk.payment_status
    status = str(asaas_payment.get("status") or "").upper()

    walk.mp_payment_id = str(asaas_payment.get("id") or walk.mp_payment_id or "")
    walk.mp_status = status
    walk.mp_status_detail = str(asaas_payment.get("event") or asaas_payment.get("billingType") or "")[:120]

    pix_data = asaas_payment.get("pixQrCode") or {}
    qr_code = pix_data.get("payload") or ""
    qr_code_base64 = pix_data.get("encodedImage") or ""
    invoice_url = asaas_payment.get("invoiceUrl") or asaas_payment.get("bankSlipUrl") or asaas_payment.get("transactionReceiptUrl") or ""

    if qr_code:
        walk.mp_qr_code = qr_code
        walk.pix_code = qr_code
    if qr_code_base64:
        walk.mp_qr_code_base64 = qr_code_base64
    if invoice_url:
        walk.mp_ticket_url = invoice_url

    if status in {"RECEIVED", "CONFIRMED", "RECEIVED_IN_CASH"}:
        walk.payment_status = "pago"
        if walk.status in ["pendente", "convite_enviado"]:
            walk.status = "pagamento_confirmado"
    elif status in {"DELETED", "REFUNDED", "CANCELLED", "CHARGEBACK_REQUESTED", "CHARGEBACK_DISPUTE"}:
        walk.payment_status = "recusado"
    elif status in {"PENDING", "AWAITING_RISK_ANALYSIS", "OVERDUE"}:
        walk.payment_status = "aguardando"

    return before != walk.payment_status


def normalize_asaas_pix_key_type(value: str) -> str:
    raw = str(value or "").strip().upper()
    raw = raw.replace("CPF/CNPJ", "CPF").replace("CELULAR", "PHONE").replace("TELEFONE", "PHONE")
    mapping = {"CPF":"CPF","CNPJ":"CNPJ","EMAIL":"EMAIL","E-MAIL":"EMAIL","PHONE":"PHONE","TELEFONE":"PHONE","CELULAR":"PHONE","EVP":"EVP","ALEATORIA":"EVP","ALEATÓRIA":"EVP"}
    return mapping.get(raw, raw)


def calculate_walker_payout_amount(db: Session, walk: WalkRequest) -> float:
    payout = get_payout_config(db)
    percent = float(payout.get("walker_percent", 80.0) or 80.0)
    return round(max(float(walk.estimated_price or 0) * (percent / 100.0), 0.0), 2)


def create_asaas_pix_transfer_to_walker(db: Session, walk: WalkRequest) -> dict:
    if not ASAAS_API_KEY:
        raise RuntimeError("ASAAS_API_KEY não configurada no Render")
    if not walk.walker:
        raise RuntimeError("Passeador não vinculado ao passeio")
    pix_key = str(getattr(walk.walker, "pix_key", "") or "").strip()
    pix_key_type = normalize_asaas_pix_key_type(getattr(walk.walker, "pix_key_type", "") or "")
    if not pix_key:
        raise RuntimeError("Passeador sem chave PIX cadastrada")
    if pix_key_type not in {"CPF", "CNPJ", "EMAIL", "PHONE", "EVP"}:
        raise RuntimeError("Tipo da chave PIX do passeador inválido")
    amount = calculate_walker_payout_amount(db, walk)
    if amount <= 0:
        raise RuntimeError("Valor de repasse inválido")
    payload = {
        "value": amount,
        "operationType": "PIX",
        "pixAddressKey": pix_key,
        "pixAddressKeyType": pix_key_type,
        "description": f"Repasse AmigoPet - Passeio #{walk.id}",
        "externalReference": f"amigopet_payout_walk_{walk.id}",
    }
    res = requests.post(
        f"{ASAAS_BASE_URL}/transfers",
        json=payload,
        headers=asaas_headers(_asaas_idempotency_key("payout", f"walk-{walk.id}-{amount}")),
        timeout=30,
    )
    data = _asaas_response_data(res)
    if res.status_code >= 400:
        raise RuntimeError(f"Asaas recusou transferência PIX ao passeador: {data}")
    return data


def get_system_sender_id(db: Session, walk: WalkRequest) -> int:
    admin = db.query(User).filter(User.role == "admin").order_by(User.id.asc()).first()
    return admin.id if admin else walk.client_id


def add_walk_system_message(db: Session, walk: WalkRequest, text_value: str) -> Optional[Message]:
    if not walk or not text_value:
        return None
    exists = db.query(Message).filter(Message.request_id == walk.id, Message.text == text_value).first()
    if exists:
        return None
    msg = Message(request_id=walk.id, sender_id=get_system_sender_id(db, walk), text=text_value)
    db.add(msg)
    db.flush()
    return msg


def message_to_dict(msg: Message) -> dict:
    sender = getattr(msg, "sender", None) or None
    return {
        "id": msg.id,
        "request_id": msg.request_id,
        "sender_id": msg.sender_id,
        "sender_name": sender.full_name if sender else "Sistema",
        "sender_role": sender.role if sender else "system",
        "sender_photo": sender.photo if sender else "",
        "text": msg.text,
        "message_type": getattr(msg, "message_type", "text") or "text",
        "read_at": msg.read_at.isoformat() if getattr(msg, "read_at", None) else None,
        "created_at": msg.created_at.isoformat() if msg.created_at else None,
    }

def notification_to_dict(item: UserNotification) -> dict:
    return {
        "id": item.id,
        "user_id": item.user_id,
        "title": item.title,
        "body": item.body or "",
        "type": item.type or "system",
        "link": item.link or "",
        "is_read": bool(item.is_read),
        "created_at": item.created_at.isoformat() if item.created_at else None,
    }

def add_user_notification(db: Session, user_id: int, title: str, body: str = "", type_value: str = "system", link: str = "") -> Optional[UserNotification]:
    if not user_id or not title:
        return None
    item = UserNotification(
        user_id=int(user_id),
        title=str(title)[:160],
        body=str(body or "")[:1000],
        type=str(type_value or "system")[:60],
        link=str(link or "")[:240],
        is_read=False,
    )
    db.add(item)
    db.flush()
    return item

def rating_to_dict(item: UserRating) -> dict:
    return {
        "id": item.id,
        "walk_id": item.walk_id,
        "rater_id": item.rater_id,
        "target_id": item.target_id,
        "rating": item.rating,
        "comment": item.comment or "",
        "role": item.role or "",
        "created_at": item.created_at.isoformat() if item.created_at else None,
        "rater": item.rater.full_name if item.rater else "",
        "target": item.target.full_name if item.target else "",
    }

def recalculate_user_rating(db: Session, user_id: int) -> None:
    items = db.query(UserRating).filter(UserRating.target_id == user_id).all()
    user = db.get(User, user_id)
    if not user or not items:
        return
    avg = sum(max(1, min(5, int(item.rating or 5))) for item in items) / len(items)
    user.rating = round(avg, 2)


# Aliases mantidos para compatibilidade interna com chamadas antigas do código.
mp_headers = asaas_headers
create_mercadopago_pix_payment = create_asaas_pix_payment
get_mercadopago_payment = get_asaas_payment
validate_mp_webhook_signature = lambda request, payment_id=None: validate_asaas_webhook_token(request)
apply_mp_payment_to_walk = apply_asaas_payment_to_walk

def walk_to_dict(w: WalkRequest):
    now = datetime.utcnow()
    seconds_left = max(0, int((w.expires_at - now).total_seconds())) if w.expires_at else 0
    return {
        "id": w.id, "client_id": w.client_id, "walker_id": w.walker_id, "pet_id": w.pet_id,
        "client": w.client.full_name if w.client else "", "walker": w.walker.full_name if w.walker else "Aguardando",
        "pet": w.pet.name if w.pet else "", "address": w.address,
        "pickup_lat": w.pickup_lat, "pickup_lng": w.pickup_lng, "walker_lat": w.walker_lat, "walker_lng": w.walker_lng,
        "duration_minutes": w.duration_minutes, "dogs_count": w.dogs_count,
        "estimated_price": w.estimated_price, "distance_km": w.distance_km,
        "status": w.status, "payment_status": w.payment_status, "pix_code": w.pix_code,
        "mp_payment_id": w.mp_payment_id, "mp_status": w.mp_status, "mp_status_detail": w.mp_status_detail,
        "mp_qr_code": w.mp_qr_code, "mp_qr_code_base64": w.mp_qr_code_base64, "mp_ticket_url": w.mp_ticket_url,
        "payout_status": getattr(w, "payout_status", "") or "aguardando",
        "payout_transfer_id": getattr(w, "payout_transfer_id", "") or "",
        "payout_amount": getattr(w, "payout_amount", 0) or 0,
        "payout_error": getattr(w, "payout_error", "") or "",
        "notes": w.notes, "seconds_left": seconds_left,
        "expires_at": w.expires_at.isoformat() if w.expires_at else None,
        "started_at": w.started_at.isoformat() if w.started_at else None,
        "finished_at": w.finished_at.isoformat() if w.finished_at else None,
        "created_at": w.created_at.isoformat(),
    }

def seed_data():
    db = SessionLocal()
    try:
        seed_users = [
            dict(full_name="Administrador AmigoPet", email="admin@amigopet.com", role="admin", city="Magé", available=True, active=True, email_verified=True, phone_verified=True, bio="Gestão operacional da plataforma."),
            dict(full_name="Cliente Teste", email="cliente@amigopet.com", role="client", phone="(21) 98888-1111", address="Rua Mirabel, 49 Piabetá - Magé - RJ", neighborhood="Piabetá", city="Magé", lat=-22.5884, lng=-43.1847, photo="https://api.dicebear.com/8.x/initials/svg?seed=Cliente", active=True, email_verified=True, phone_verified=True),
            dict(full_name="Passeador Profissional", email="passeador@amigopet.com", role="walker", phone="(21) 99999-0000", neighborhood="Piabetá", city="Magé", lat=-22.5900, lng=-43.1810, rating=4.9, available=True, active=True, email_verified=True, phone_verified=True, photo="https://api.dicebear.com/8.x/initials/svg?seed=Passeador%20Profissional&backgroundColor=ccfbf1", bio="Passeador verificado, experiência com cães pequenos e grandes."),
            dict(full_name="Ana Walker Premium", email="ana@amigopet.com", role="walker", phone="(21) 97777-2222", neighborhood="Centro", city="Magé", lat=-22.5852, lng=-43.1881, rating=4.8, available=True, active=True, email_verified=True, phone_verified=True, photo="https://api.dicebear.com/8.x/initials/svg?seed=Ana%20Walker%20Premium&backgroundColor=dbeafe", bio="Rotas seguras, envio de fotos e cuidado especial."),
        ]

        for data in seed_users:
            user = db.query(User).filter(User.email == data["email"]).first()
            if not user:
                user = User(**data, password_hash=hash_password("123456"))
                db.add(user)
            else:
                user.password_hash = hash_password("123456")
                for k, v in data.items():
                    if hasattr(user, k):
                        setattr(user, k, v)

        db.commit()

        cliente = db.query(User).filter(User.email == "cliente@amigopet.com").first()
        if cliente and db.query(Pet).filter(Pet.owner_id == cliente.id).count() == 0:
            pet = Pet(
                owner_id=cliente.id,
                name="Thor",
                breed="SRD",
                size="Médio",
                age="3 anos",
                photo="https://api.dicebear.com/8.x/bottts/svg?seed=Thor",
                notes="Gosta de passeios tranquilos.",
                dog_count=1,
            )
            db.add(pet)
            db.commit()
    finally:
        db.close()


def run_lightweight_migrations():
    """Corrige banco antigo sem precisar de Shell no Render Free.

    Importante:
    - NÃO apaga usuários, pets ou pedidos.
    - Mantém compatibilidade com banco antigo do Render.
    - Remove NOT NULL legado em colunas que não são mais usadas pelo código atual,
      evitando erro 500 / {} na criação do convite.
    """
    Base.metadata.create_all(bind=engine)

    with engine.begin() as conn:
        if engine.dialect.name != "postgresql":
            return

        def safe(sql: str, label: str = ""):
            try:
                conn.execute(text(sql))
            except Exception as e:
                print(f"[MIGRATION WARNING] {label or sql}:", e)

        for old_col in ["password", "online"]:
            safe(f"ALTER TABLE users DROP COLUMN IF EXISTS {old_col}", f"drop old users.{old_col}")

        user_columns_sql = [
            ("password_hash", "VARCHAR(255)"),
            ("phone", "VARCHAR(30) DEFAULT ''"),
            ("photo", "TEXT DEFAULT ''"),
            ("document", "VARCHAR(40) DEFAULT ''"),
            ("pix_key_type", "VARCHAR(30) DEFAULT ''"),
            ("pix_key", "VARCHAR(180) DEFAULT ''"),
            ("pix_holder_name", "VARCHAR(160) DEFAULT ''"),
            ("pix_holder_document", "VARCHAR(40) DEFAULT ''"),
            ("address", "TEXT DEFAULT ''"),
            ("neighborhood", "VARCHAR(120) DEFAULT ''"),
            ("city", "VARCHAR(120) DEFAULT ''"),
            ("zip_code", "VARCHAR(20) DEFAULT ''"),
            ("street", "VARCHAR(160) DEFAULT ''"),
            ("number", "VARCHAR(30) DEFAULT ''"),
            ("complement", "VARCHAR(120) DEFAULT ''"),
            ("state", "VARCHAR(60) DEFAULT 'RJ'"),
            ("lat", "DOUBLE PRECISION DEFAULT -22.5884"),
            ("lng", "DOUBLE PRECISION DEFAULT -43.1847"),
            ("rating", "DOUBLE PRECISION DEFAULT 5"),
            ("available", "BOOLEAN DEFAULT TRUE"),
            ("bio", "TEXT DEFAULT ''"),
            ("active", "BOOLEAN DEFAULT TRUE"),
            ("email_verified", "BOOLEAN DEFAULT TRUE"),
            ("phone_verified", "BOOLEAN DEFAULT TRUE"),
            ("verification_code_hash", "VARCHAR(255) DEFAULT ''"),
            ("verification_expires_at", "TIMESTAMP NULL"),
            ("verified_at", "TIMESTAMP NULL"),
            ("accepted_terms", "BOOLEAN DEFAULT FALSE"),
            ("accepted_terms_at", "TIMESTAMP NULL"),
            ("terms_version", "VARCHAR(20) DEFAULT ''"),
            ("accepted_terms_ip", "VARCHAR(80) DEFAULT ''"),
            ("accepted_terms_user_agent", "TEXT DEFAULT ''"),
            ("client_terms_accepted", "BOOLEAN DEFAULT FALSE"),
            ("client_terms_accepted_at", "TIMESTAMP NULL"),
            ("client_terms_version", "VARCHAR(20) DEFAULT ''"),
            ("client_terms_ip", "VARCHAR(80) DEFAULT ''"),
            ("client_terms_user_agent", "TEXT DEFAULT ''"),
            ("created_at", "TIMESTAMP DEFAULT NOW()"),
        ]

        for col, ddl in user_columns_sql:
            safe(f"ALTER TABLE users ADD COLUMN IF NOT EXISTS {col} {ddl}", f"add users.{col}")

        for col in ["available", "active", "email_verified", "phone_verified"]:
            safe(f"ALTER TABLE users ALTER COLUMN {col} SET DEFAULT TRUE", f"default users.{col}")
            safe(f"UPDATE users SET {col}=TRUE WHERE {col} IS NULL", f"normalize users.{col}")
            safe(f"ALTER TABLE users ALTER COLUMN {col} SET NOT NULL", f"not null users.{col}")

        safe("ALTER TABLE users ALTER COLUMN accepted_terms SET DEFAULT FALSE", "default users.accepted_terms")
        safe("UPDATE users SET accepted_terms=FALSE WHERE accepted_terms IS NULL", "normalize users.accepted_terms")
        safe("ALTER TABLE users ALTER COLUMN accepted_terms SET NOT NULL", "not null users.accepted_terms")
        safe("UPDATE users SET terms_version='' WHERE terms_version IS NULL", "normalize users.terms_version")
        safe("ALTER TABLE users ALTER COLUMN terms_version SET DEFAULT ''", "default users.terms_version")
        safe("ALTER TABLE users ALTER COLUMN terms_version SET NOT NULL", "not null users.terms_version")
        safe("ALTER TABLE users ALTER COLUMN client_terms_accepted SET DEFAULT FALSE", "default users.client_terms_accepted")
        safe("UPDATE users SET client_terms_accepted=FALSE WHERE client_terms_accepted IS NULL", "normalize users.client_terms_accepted")
        safe("ALTER TABLE users ALTER COLUMN client_terms_accepted SET NOT NULL", "not null users.client_terms_accepted")
        safe("UPDATE users SET client_terms_version='' WHERE client_terms_version IS NULL", "normalize users.client_terms_version")
        safe("ALTER TABLE users ALTER COLUMN client_terms_version SET DEFAULT ''", "default users.client_terms_version")
        safe("ALTER TABLE users ALTER COLUMN client_terms_version SET NOT NULL", "not null users.client_terms_version")

        safe("UPDATE users SET password_hash='sha256$legacy$invalid' WHERE password_hash IS NULL", "normalize users.password_hash")
        safe("ALTER TABLE users ALTER COLUMN password_hash SET NOT NULL", "not null users.password_hash")

        pet_columns_sql = [
            ("species", "VARCHAR(60) DEFAULT 'Cachorro'"),
            ("breed", "VARCHAR(100) DEFAULT ''"),
            ("size", "VARCHAR(50) DEFAULT 'Médio'"),
            ("age", "VARCHAR(50) DEFAULT ''"),
            ("photo", "TEXT DEFAULT ''"),
            ("notes", "TEXT DEFAULT ''"),
            ("dog_count", "INTEGER DEFAULT 1"),
        ]

        for col, ddl in pet_columns_sql:
            safe(f"ALTER TABLE pets ADD COLUMN IF NOT EXISTS {col} {ddl}", f"add pets.{col}")

        safe("ALTER TABLE pets ALTER COLUMN dog_count SET DEFAULT 1", "default pets.dog_count")
        safe("UPDATE pets SET dog_count=1 WHERE dog_count IS NULL", "normalize pets.dog_count")
        safe("ALTER TABLE pets ALTER COLUMN dog_count SET NOT NULL", "not null pets.dog_count")

        walk_columns_sql = [
            ("client_id", "INTEGER"),
            ("walker_id", "INTEGER"),
            ("pet_id", "INTEGER"),
            ("address", "TEXT DEFAULT ''"),
            ("pickup_lat", "DOUBLE PRECISION DEFAULT -22.5884"),
            ("pickup_lng", "DOUBLE PRECISION DEFAULT -43.1847"),
            ("walker_lat", "DOUBLE PRECISION DEFAULT -22.5900"),
            ("walker_lng", "DOUBLE PRECISION DEFAULT -43.1810"),
            ("duration_minutes", "INTEGER DEFAULT 30"),
            ("dogs_count", "INTEGER DEFAULT 1"),
            ("estimated_price", "DOUBLE PRECISION DEFAULT 25"),
            ("distance_km", "DOUBLE PRECISION DEFAULT 1.8"),
            ("status", "VARCHAR(40) DEFAULT 'pendente'"),
            ("payment_status", "VARCHAR(40) DEFAULT 'aguardando'"),
            ("pix_code", "TEXT DEFAULT ''"),
            ("mp_payment_id", "VARCHAR(80) DEFAULT ''"),
            ("mp_status", "VARCHAR(60) DEFAULT ''"),
            ("mp_status_detail", "VARCHAR(120) DEFAULT ''"),
            ("mp_qr_code", "TEXT DEFAULT ''"),
            ("mp_qr_code_base64", "TEXT DEFAULT ''"),
            ("mp_ticket_url", "TEXT DEFAULT ''"),
            ("payout_status", "VARCHAR(40) DEFAULT 'aguardando'"),
            ("payout_transfer_id", "VARCHAR(120) DEFAULT ''"),
            ("payout_amount", "DOUBLE PRECISION DEFAULT 0"),
            ("payout_error", "TEXT DEFAULT ''"),
            ("notes", "TEXT DEFAULT ''"),
            ("expires_at", "TIMESTAMP NULL"),
            ("started_at", "TIMESTAMP NULL"),
            ("finished_at", "TIMESTAMP NULL"),
            ("created_at", "TIMESTAMP DEFAULT NOW()"),
        ]

        for col, ddl in walk_columns_sql:
            safe(f"ALTER TABLE walk_requests ADD COLUMN IF NOT EXISTS {col} {ddl}", f"add walk_requests.{col}")

        # Normaliza defaults das colunas atuais.
        walk_defaults_sql = [
            ("address", "''"),
            ("pickup_lat", "-22.5884"),
            ("pickup_lng", "-43.1847"),
            ("walker_lat", "-22.5900"),
            ("walker_lng", "-43.1810"),
            ("duration_minutes", "30"),
            ("dogs_count", "1"),
            ("estimated_price", "25"),
            ("distance_km", "1.8"),
            ("status", "'pendente'"),
            ("payment_status", "'aguardando'"),
            ("pix_code", "''"),
            ("mp_payment_id", "''"),
            ("mp_status", "''"),
            ("mp_status_detail", "''"),
            ("mp_qr_code", "''"),
            ("mp_qr_code_base64", "''"),
            ("mp_ticket_url", "''"),
            ("payout_status", "'aguardando'"),
            ("payout_transfer_id", "''"),
            ("payout_amount", "0"),
            ("payout_error", "''"),
            ("notes", "''"),
            ("created_at", "NOW()"),
        ]

        for col, default in walk_defaults_sql:
            safe(f"ALTER TABLE walk_requests ALTER COLUMN {col} SET DEFAULT {default}", f"default walk_requests.{col}")

        # Backfill de dados atuais e antigos.
        safe("UPDATE walk_requests SET address='' WHERE address IS NULL", "normalize walk_requests.address")
        safe("UPDATE walk_requests SET pickup_lat=-22.5884 WHERE pickup_lat IS NULL", "normalize walk_requests.pickup_lat")
        safe("UPDATE walk_requests SET pickup_lng=-43.1847 WHERE pickup_lng IS NULL", "normalize walk_requests.pickup_lng")
        safe("UPDATE walk_requests SET walker_lat=-22.5900 WHERE walker_lat IS NULL", "normalize walk_requests.walker_lat")
        safe("UPDATE walk_requests SET walker_lng=-43.1810 WHERE walker_lng IS NULL", "normalize walk_requests.walker_lng")
        safe("UPDATE walk_requests SET duration_minutes=30 WHERE duration_minutes IS NULL", "normalize walk_requests.duration_minutes")
        safe("UPDATE walk_requests SET dogs_count=1 WHERE dogs_count IS NULL", "normalize walk_requests.dogs_count")
        safe("UPDATE walk_requests SET estimated_price=25 WHERE estimated_price IS NULL", "normalize walk_requests.estimated_price")
        safe("UPDATE walk_requests SET distance_km=1.8 WHERE distance_km IS NULL", "normalize walk_requests.distance_km")
        safe("UPDATE walk_requests SET status='pendente' WHERE status IS NULL", "normalize walk_requests.status")
        safe("UPDATE walk_requests SET payment_status='aguardando' WHERE payment_status IS NULL", "normalize walk_requests.payment_status")
        safe("UPDATE walk_requests SET pix_code='' WHERE pix_code IS NULL", "normalize walk_requests.pix_code")
        safe("UPDATE walk_requests SET mp_payment_id='' WHERE mp_payment_id IS NULL", "normalize walk_requests.mp_payment_id")
        safe("UPDATE walk_requests SET mp_status='' WHERE mp_status IS NULL", "normalize walk_requests.mp_status")
        safe("UPDATE walk_requests SET mp_status_detail='' WHERE mp_status_detail IS NULL", "normalize walk_requests.mp_status_detail")
        safe("UPDATE walk_requests SET mp_qr_code='' WHERE mp_qr_code IS NULL", "normalize walk_requests.mp_qr_code")
        safe("UPDATE walk_requests SET mp_qr_code_base64='' WHERE mp_qr_code_base64 IS NULL", "normalize walk_requests.mp_qr_code_base64")
        safe("UPDATE walk_requests SET mp_ticket_url='' WHERE mp_ticket_url IS NULL", "normalize walk_requests.mp_ticket_url")
        safe("UPDATE walk_requests SET payout_status='aguardando' WHERE payout_status IS NULL", "normalize walk_requests.payout_status")
        safe("UPDATE walk_requests SET payout_transfer_id='' WHERE payout_transfer_id IS NULL", "normalize walk_requests.payout_transfer_id")
        safe("UPDATE walk_requests SET payout_amount=0 WHERE payout_amount IS NULL", "normalize walk_requests.payout_amount")
        safe("UPDATE walk_requests SET payout_error='' WHERE payout_error IS NULL", "normalize walk_requests.payout_error")
        safe("UPDATE walk_requests SET notes='' WHERE notes IS NULL", "normalize walk_requests.notes")
        safe("UPDATE walk_requests SET created_at=NOW() WHERE created_at IS NULL", "normalize walk_requests.created_at")

        # Compatibilidade com banco legacy: se existirem colunas antigas que o SQLAlchemy não usa mais,
        # elas não podem continuar NOT NULL sem default, senão todo INSERT novo quebra.
        rows = conn.execute(text("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = 'walk_requests'
              AND is_nullable = 'NO'
              AND column_name <> 'id'
        """)).fetchall()

        for row in rows:
            col = row[0]
            if not col.replace('_', '').isalnum():
                continue
            safe(f"ALTER TABLE walk_requests ALTER COLUMN {col} DROP NOT NULL", f"drop not null walk_requests.{col}")

        # Se algumas colunas legacy específicas existirem, deixamos defaults úteis.
        legacy_defaults = {
            "pickup_address": "''",
            "pickup_time": "NOW()",
            "price": "0",
            "total_price": "0",
            "client_name": "''",
            "walker_name": "''",
            "dog_name": "''",
            "dog_size": "''",
            "request_status": "'convite_enviado'",
        }
        existing_cols = [r[0] for r in conn.execute(text("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = 'walk_requests'
        """)).fetchall()]
        for col, default in legacy_defaults.items():
            if col in existing_cols:
                safe(f"ALTER TABLE walk_requests ALTER COLUMN {col} SET DEFAULT {default}", f"default legacy walk_requests.{col}")

        safe("ALTER TABLE messages ADD COLUMN IF NOT EXISTS message_type VARCHAR(30) DEFAULT 'text'", "add messages.message_type")
        safe("ALTER TABLE messages ADD COLUMN IF NOT EXISTS read_at TIMESTAMP NULL", "add messages.read_at")
        safe("UPDATE messages SET message_type='text' WHERE message_type IS NULL", "normalize messages.message_type")
        safe("ALTER TABLE messages ALTER COLUMN message_type SET DEFAULT 'text'", "default messages.message_type")
        safe("CREATE INDEX IF NOT EXISTS ix_messages_request_created ON messages (request_id, created_at)", "index messages request/created")

        safe("CREATE INDEX IF NOT EXISTS ix_notifications_user_read ON notifications (user_id, is_read)", "index notifications user/read")
        safe("CREATE INDEX IF NOT EXISTS ix_notifications_created_at ON notifications (created_at)", "index notifications created_at")
        safe("CREATE INDEX IF NOT EXISTS ix_ratings_walk_rater ON ratings (walk_id, rater_id)", "index ratings walk/rater")
        safe("CREATE INDEX IF NOT EXISTS ix_ratings_target ON ratings (target_id)", "index ratings target")


run_lightweight_migrations()
seed_data()
seed_pricing_settings()
seed_payout_settings()


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            raw = await websocket.receive_text()
            try:
                payload = json.loads(raw)
            except Exception:
                payload = {"type": "ping"}
            if isinstance(payload, dict) and payload.get("type") == "typing":
                await manager.broadcast({
                    "type": "typing",
                    "request_id": payload.get("request_id"),
                    "sender_id": payload.get("sender_id"),
                    "sender_role": payload.get("sender_role", ""),
                    "is_typing": bool(payload.get("is_typing", True)),
                })
    except WebSocketDisconnect:
        manager.disconnect(websocket)

@app.get("/health")
def health():
    return {"ok": True, "app": "AmigoPet V6 Uber", "version": "6.0.0"}

@app.post("/api/auth/register")
def register(data: RegisterIn, db: Session = Depends(get_db)):
    if db.query(User).filter(User.email == data.email).first():
        raise HTTPException(status_code=400, detail="E-mail já cadastrado")
    user = User(**pydantic_dump(data, exclude={"password"}), password_hash=hash_password(data.password), active=True, email_verified=True, phone_verified=True)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user_to_dict(user)

@app.post("/api/auth/login")
def login(data: LoginIn, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == data.email).first()
    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="E-mail ou senha inválidos")
    return user_to_dict(user)



@app.get("/api/auth/google/login")
def google_login():
    return google_login_role("client")


@app.get("/api/auth/google/login/{role}")
def google_login_role(role: str):
    role = (role or "client").strip().lower()
    if role not in ["client", "walker"]:
        role = "client"

    if not GOOGLE_CLIENT_ID or not GOOGLE_REDIRECT_URI:
        raise HTTPException(status_code=500, detail="GOOGLE_CLIENT_ID ou GOOGLE_REDIRECT_URI não configurado no Render")

    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "online",
        "prompt": "select_account",
        "state": role,
    }
    return RedirectResponse("https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(params))


@app.get("/api/auth/google/callback")
def google_callback(code: str = "", error: str = "", state: str = "client", db: Session = Depends(get_db)):
    role = (state or "client").strip().lower()
    if role not in ["client", "walker"]:
        role = "client"

    redirect_base = "/passeador" if role == "walker" else "/"

    if error:
        return RedirectResponse(f"{redirect_base}?google_error={quote(error)}")
    if not code:
        return RedirectResponse(f"{redirect_base}?google_error=missing_code")
    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET or not GOOGLE_REDIRECT_URI:
        return RedirectResponse(f"{redirect_base}?google_error=google_not_configured")

    try:
        token_res = requests.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": code,
                "client_id": GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "redirect_uri": GOOGLE_REDIRECT_URI,
                "grant_type": "authorization_code",
            },
            timeout=30,
        )
        token_data = token_res.json()
        if token_res.status_code >= 400 or not token_data.get("access_token"):
            print("[GOOGLE LOGIN ERROR] token", token_data)
            return RedirectResponse(f"{redirect_base}?google_error=token_error")

        user_res = requests.get(
            "https://www.googleapis.com/oauth2/v3/userinfo",
            headers={"Authorization": f"Bearer {token_data['access_token']}"},
            timeout=30,
        )
        google_user = user_res.json()
        if user_res.status_code >= 400 or not google_user.get("email"):
            print("[GOOGLE LOGIN ERROR] userinfo", google_user)
            return RedirectResponse(f"{redirect_base}?google_error=userinfo_error")

        email = str(google_user.get("email") or "").strip().lower()
        full_name = str(google_user.get("name") or email.split("@", 1)[0]).strip()
        photo = str(google_user.get("picture") or "").strip()

        user = db.query(User).filter(User.email == email).first()
        if not user:
            user = User(
                full_name=full_name,
                email=email,
                password_hash=hash_password(secrets.token_urlsafe(24)),
                role=role,
                photo=photo,
                active=True,
                email_verified=True,
                phone_verified=True,
                verified_at=datetime.utcnow(),
                accepted_terms=False,
                terms_version="",
                client_terms_accepted=False,
                client_terms_version="",
            )
            db.add(user)
        else:
            # Mantém o papel já existente para não transformar cliente em passeador sem querer.
            # Se o usuário já existir com outro papel, ele será redirecionado e o frontend bloqueará o acesso errado.
            user.full_name = user.full_name or full_name
            if photo and not user.photo:
                user.photo = photo
            user.email_verified = True
            user.active = True
            user.verified_at = user.verified_at or datetime.utcnow()

        db.commit()
        db.refresh(user)

        redirect_base = "/passeador" if user.role == "walker" else "/"
        return RedirectResponse(f"{redirect_base}?google_user_id={user.id}")
    except Exception as e:
        print("[GOOGLE LOGIN ERROR]", str(e))
        return RedirectResponse(f"{redirect_base}?google_error=server_error")


@app.get("/api/auth/google/session/{user_id}")
def google_session(user_id: int, db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Usuário Google não encontrado")
    return user_to_dict(user)


@app.post("/api/auth/request-password-reset")
def request_password_reset(data: PasswordResetRequestIn, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == data.email).first()

    # Por segurança, não revelamos se o e-mail existe ou não.
    generic_response = {
        "ok": True,
        "message": "Se o e-mail estiver cadastrado, enviaremos um código de recuperação."
    }

    if not user:
        return generic_response

    code = f"{secrets.randbelow(1000000):06d}"
    user.verification_code_hash = hash_password(code)
    user.verification_expires_at = datetime.utcnow() + timedelta(minutes=15)
    db.commit()

    body = f"""Olá, {user.full_name}.

Recebemos uma solicitação para recuperar sua senha no AmigoPet.

Seu código de recuperação é: {code}

Este código expira em 15 minutos.

Se você não solicitou essa recuperação, ignore este e-mail.

AmigoPet
Powered by ROVIX
"""

    sent = send_email_message(
        user.email,
        "Código de recuperação de senha - AmigoPet",
        body
    )

    if not sent:
        raise HTTPException(
            status_code=500,
            detail="Não foi possível enviar o código por e-mail. Verifique as configurações SMTP no Render."
        )

    return generic_response

@app.post("/api/auth/reset-password")
def reset_password(data: PasswordResetConfirmIn, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == data.email).first()
    if not user:
        raise HTTPException(status_code=404, detail="E-mail não encontrado")

    if not data.new_password or len(data.new_password) < 6:
        raise HTTPException(status_code=400, detail="A nova senha deve ter no mínimo 6 caracteres")

    if not user.verification_code_hash or not user.verification_expires_at:
        raise HTTPException(status_code=400, detail="Solicite um novo código de recuperação")

    if datetime.utcnow() > user.verification_expires_at:
        raise HTTPException(status_code=400, detail="Código expirado. Solicite um novo código")

    if not verify_password(data.code.strip(), user.verification_code_hash):
        raise HTTPException(status_code=400, detail="Código inválido")

    user.password_hash = hash_password(data.new_password)
    user.verification_code_hash = ""
    user.verification_expires_at = None
    db.commit()

    return {"ok": True, "message": "Senha alterada com sucesso. Faça login com a nova senha."}

@app.get("/api/users")
def users(role: Optional[str] = None, db: Session = Depends(get_db)):
    q = db.query(User)
    if role:
        q = q.filter(User.role == role)
    return [user_to_dict(u) for u in q.order_by(User.rating.desc(), User.id.asc()).all()]

@app.put("/api/users/{user_id}")
def update_user(user_id: int, data: ClientUpdateIn, db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    if user.role != "client":
        raise HTTPException(status_code=400, detail="Esta edição é exclusiva para clientes")

    payload = pydantic_dump(data)
    required = ["full_name", "phone", "street", "number", "neighborhood", "city"]
    for field in required:
        if not str(payload.get(field, "")).strip():
            raise HTTPException(status_code=400, detail="Preencha todos os dados obrigatórios do cliente")

    if not str(payload.get("address", "")).strip():
        parts = [payload.get("street", ""), payload.get("number", ""), payload.get("neighborhood", ""), payload.get("city", ""), payload.get("state", "RJ")]
        payload["address"] = ", ".join([str(x).strip() for x in parts if str(x).strip()])

    allowed = [
        "full_name", "phone", "photo", "document", "address", "zip_code", "street",
        "number", "complement", "neighborhood", "city", "state", "bio"
    ]
    for key in allowed:
        if hasattr(user, key):
            value = payload.get(key, "")
            if key == "state" and not value:
                value = "RJ"
            if key == "photo" and not str(value).strip():
                continue
            setattr(user, key, value)

    db.commit()
    db.refresh(user)
    return user_to_dict(user)


@app.post("/api/clients/{user_id}/accept-terms")
def accept_client_terms(user_id: int, request: Request, db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    if user.role != "client":
        raise HTTPException(status_code=400, detail="Este aceite é exclusivo para clientes")

    user.client_terms_accepted = True
    user.client_terms_accepted_at = datetime.utcnow()
    user.client_terms_version = CLIENT_TERMS_VERSION
    user.client_terms_ip = client_ip_from_request(request)
    user.client_terms_user_agent = (request.headers.get("user-agent") or "")[:1000]
    db.commit()
    db.refresh(user)
    return user_to_dict(user)


@app.put("/api/walkers/{user_id}/profile")
def update_walker_profile(user_id: int, data: WalkerUpdateIn, db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Passeador não encontrado")
    if user.role != "walker":
        raise HTTPException(status_code=400, detail="Esta edição é exclusiva para passeadores")

    payload = pydantic_dump(data)
    if not str(payload.get("full_name", "")).strip():
        raise HTTPException(status_code=400, detail="Informe o nome do passeador")

    allowed = [
        "full_name", "phone", "photo", "document",
        "pix_key_type", "pix_key", "pix_holder_name", "pix_holder_document",
        "neighborhood", "city", "bio"
    ]
    for key in allowed:
        if hasattr(user, key):
            value = payload.get(key, "")
            if key == "photo" and not str(value).strip():
                continue
            setattr(user, key, value)

    db.commit()
    db.refresh(user)
    return user_to_dict(user)


@app.post("/api/walkers/{user_id}/accept-terms")
def accept_walker_terms(user_id: int, request: Request, db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Passeador não encontrado")
    if user.role != "walker":
        raise HTTPException(status_code=400, detail="Este aceite é exclusivo para passeadores")

    user.accepted_terms = True
    user.accepted_terms_at = datetime.utcnow()
    user.terms_version = WALKER_TERMS_VERSION
    user.accepted_terms_ip = client_ip_from_request(request)
    user.accepted_terms_user_agent = (request.headers.get("user-agent") or "")[:1000]
    db.commit()
    db.refresh(user)
    return user_to_dict(user)


@app.put("/api/walkers/{user_id}/availability")
async def update_walker_availability(user_id: int, data: AvailabilityIn, db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Passeador não encontrado")
    if user.role != "walker":
        raise HTTPException(status_code=400, detail="Esta ação é exclusiva para passeadores")

    user.available = bool(data.available)
    db.commit()
    db.refresh(user)

    payload = user_to_dict(user)
    await manager.broadcast({
        "type": "walker_availability_changed",
        "walker": payload
    })
    return payload

@app.get("/api/pets")
def pets(owner_id: Optional[int] = None, db: Session = Depends(get_db)):
    q = db.query(Pet)
    if owner_id:
        q = q.filter(Pet.owner_id == owner_id)
    return [pet_to_dict(p) for p in q.order_by(Pet.id.desc()).all()]

@app.post("/api/pets")
def create_pet(data: PetIn, db: Session = Depends(get_db)):
    if not data.photo or len(data.photo.strip()) < 10:
        raise HTTPException(status_code=400, detail="A foto do pet é obrigatória")
    owner = db.get(User, data.owner_id)
    if not owner or owner.role != "client":
        raise HTTPException(status_code=400, detail="Cliente inválido")
    pet = Pet(**pydantic_dump(data))
    db.add(pet)
    db.commit()
    db.refresh(pet)
    return pet_to_dict(pet)

@app.get("/api/pricing")
def get_pricing(db: Session = Depends(get_db)):
    pricing = get_pricing_config(db)
    return {
        **pricing,
        "durations": [
            {"minutes": 30, "price": pricing["price_30"]},
            {"minutes": 45, "price": pricing["price_45"]},
            {"minutes": 60, "price": pricing["price_60"]},
        ],
    }

@app.post("/api/admin/pricing")
def update_pricing(data: PricingIn, db: Session = Depends(get_db)):
    values = pydantic_dump(data)
    for key in DEFAULT_PRICING.keys():
        value = float(values.get(key, DEFAULT_PRICING[key]))
        if value < 0:
            raise HTTPException(status_code=400, detail="Preço não pode ser negativo")
        set_setting(db, key, str(round(value, 2)))
    db.commit()
    return get_pricing_config(db)

@app.get("/api/admin/payout-settings")
def get_payout_settings(db: Session = Depends(get_db)):
    return get_payout_config(db)

@app.post("/api/admin/payout-settings")
def update_payout_settings(data: PayoutSettingsIn, db: Session = Depends(get_db)):
    walker_percent = float(data.walker_percent or 0)
    platform_percent = float(data.platform_percent or 0)

    if walker_percent < 0 or platform_percent < 0:
        raise HTTPException(status_code=400, detail="Percentuais não podem ser negativos")

    total = round(walker_percent + platform_percent, 2)
    if total != 100.0:
        raise HTTPException(status_code=400, detail="A soma dos percentuais precisa ser 100%")

    set_setting(db, "walker_percent", str(round(walker_percent, 2)))
    set_setting(db, "platform_percent", str(round(platform_percent, 2)))
    db.commit()
    return get_payout_config(db)

@app.get("/api/walks")
def walks(status: Optional[str] = None, db: Session = Depends(get_db)):
    q = db.query(WalkRequest)
    if status:
        q = q.filter(WalkRequest.status == status)
    return [walk_to_dict(w) for w in q.order_by(WalkRequest.id.desc()).all()]

@app.get("/api/walks/{walk_id}")
def get_walk(walk_id: int, db: Session = Depends(get_db)):
    walk = db.get(WalkRequest, walk_id)
    if not walk:
        raise HTTPException(status_code=404, detail="Solicitação não encontrada")
    return walk_to_dict(walk)

@app.post("/api/walks")
async def create_walk(data: WalkIn, db: Session = Depends(get_db)):
    if not data.client_id:
        raise HTTPException(status_code=400, detail="Cliente inválido")
    if not data.address or not data.address.strip():
        raise HTTPException(status_code=400, detail="Informe o endereço")

    client = db.get(User, data.client_id)
    if not client or client.role != "client":
        raise HTTPException(status_code=400, detail="Cliente inválido")

    if data.walker_id:
        walker = db.get(User, data.walker_id)
        if not walker or walker.role != "walker":
            raise HTTPException(status_code=400, detail="Passeador inválido")

    if data.pet_id:
        pet = db.get(Pet, data.pet_id)
        if not pet or pet.owner_id != data.client_id:
            raise HTTPException(status_code=400, detail="Pet inválido para este cliente")

    payload_data = pydantic_dump(data)

    price = calculate_walk_price(db, data.duration_minutes, data.dogs_count)

    distance = 1.2 + max(data.dogs_count - 1, 0) * 0.3

    try:
        walk = WalkRequest(
            **payload_data,
            estimated_price=round(price, 2),
            distance_km=round(distance, 1),
            expires_at=datetime.utcnow() + timedelta(minutes=5),
            status="convite_enviado",
            payment_status="aguardando",
        )
        db.add(walk)
        db.commit()
        walk.pix_code = make_pix_code(walk.id, walk.estimated_price)
        db.commit()
        db.refresh(walk)

        # Asaas real: cria cobrança PIX e salva QR Code/copia-e-cola no pedido.
        try:
            mp_payment = create_mercadopago_pix_payment(walk)
            apply_mp_payment_to_walk(walk, mp_payment)
            db.commit()
            db.refresh(walk)
        except Exception as mp_error:
            db.rollback()
            walk = db.get(WalkRequest, walk.id)
            if walk:
                # Não gerar PIX simulado quando o Asaas falhar. Assim o cliente não copia
                # um código inválido e o erro real aparece no card do pedido/admin.
                walk.pix_code = ""
                walk.mp_qr_code_base64 = ""
                walk.mp_ticket_url = ""
                walk.mp_status = "asaas_error"
                walk.mp_status_detail = str(mp_error)[:240]
                db.commit()
                db.refresh(walk)
            print("[ASAAS PIX ERROR]", str(mp_error))
    except Exception as e:
        db.rollback()
        msg = str(e)
        print("[CREATE WALK ERROR]", msg)
        if "NotNullViolation" in msg or "violates not-null constraint" in msg:
            raise HTTPException(
                status_code=500,
                detail="Banco antigo com coluna obrigatória incompatível em walk_requests. O deploy precisa reiniciar para aplicar a migration automática. Erro técnico: " + msg[:700],
            )
        raise HTTPException(status_code=500, detail="Erro ao criar convite: " + msg[:700])

    notifications_created = []
    try:
        if walk.walker_id:
            targets = db.query(User).filter(User.id == walk.walker_id, User.role == "walker").all()
        else:
            targets = db.query(User).filter(User.role == "walker", User.active == True, User.available == True).all()
        for target in targets:
            notif = add_user_notification(
                db,
                target.id,
                "🐶 Novo passeio disponível",
                f"{walk.client.full_name if walk.client else 'Cliente'} solicitou passeio para {walk.pet.name if walk.pet else 'pet'} • R$ {float(walk.estimated_price or 0):.2f}",
                "walk_created",
                "/passeador"
            )
            if notif:
                notifications_created.append(notif)
        db.commit()
    except Exception as notify_error:
        db.rollback()
        print("[NOTIFICATION WARNING] walk_created", str(notify_error))

    payload = walk_to_dict(walk)
    await manager.broadcast({"type": "walk_created", "walk": payload})
    return payload

@app.post("/api/walks/{walk_id}/accept")
async def accept_walk(walk_id: int, walker_id: int, db: Session = Depends(get_db)):
    walk = db.get(WalkRequest, walk_id)
    if not walk:
        raise HTTPException(status_code=404, detail="Solicitação não encontrada")
    if walk.status in ["finalizado", "cancelado"]:
        raise HTTPException(status_code=400, detail="Pedido já encerrado")
    if walk.payment_status != "pago":
        raise HTTPException(status_code=402, detail="Aguardando pagamento PIX confirmado pelo Asaas antes do aceite")
    walk.walker_id = walker_id
    walk.status = "aceito"
    walk.expires_at = None
    db.commit()
    db.refresh(walk)
    payload = walk_to_dict(walk)
    await manager.broadcast({"type": "walk_accepted", "walk": payload})
    return payload

@app.post("/api/walks/{walk_id}/reject")
async def reject_walk(walk_id: int, db: Session = Depends(get_db)):
    walk = db.get(WalkRequest, walk_id)
    if not walk:
        raise HTTPException(status_code=404, detail="Solicitação não encontrada")
    walk.status = "recusado"
    db.commit()
    payload = walk_to_dict(walk)
    await manager.broadcast({"type": "walk_rejected", "walk": payload})
    return payload

@app.post("/api/walks/{walk_id}/pay")
async def pay_walk(walk_id: int, db: Session = Depends(get_db)):
    """Compatível com o botão antigo: se houver Mercado Pago, verifica no gateway; se não houver, confirma manualmente."""
    walk = db.get(WalkRequest, walk_id)
    if not walk:
        raise HTTPException(status_code=404, detail="Solicitação não encontrada")

    changed = False
    if not walk.mp_payment_id:
        raise HTTPException(status_code=400, detail="Este pedido ainda não tem pagamento Asaas vinculado. Crie um novo pedido para gerar o PIX real.")

    if not ASAAS_API_KEY:
        raise HTTPException(status_code=500, detail="ASAAS_API_KEY não configurada no Render.")

    try:
        mp_payment = get_mercadopago_payment(walk.mp_payment_id)
        changed = apply_mp_payment_to_walk(walk, mp_payment)
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail="Não foi possível consultar o Asaas: " + str(e)[:700])

    messages = []
    if changed or walk.payment_status == "pago":
        messages.append(add_walk_system_message(db, walk, "✅ Pagamento confirmado com sucesso. O pedido foi liberado para o passeador aceitar."))

    db.commit()
    db.refresh(walk)
    payload = walk_to_dict(walk)
    if changed or walk.payment_status == "pago":
        await manager.broadcast({"type": "payment_confirmed", "walk": payload})
        for msg in messages:
            if msg:
                await manager.broadcast({"type": "message", "message": message_to_dict(msg)})
    return payload

@app.post("/api/asaas/webhook")
@app.post("/api/payments/asaas/webhook")
@app.post("/api/payments/webhook")
async def asaas_webhook(request: Request, db: Session = Depends(get_db)):
    """Webhook real do Asaas. Confirma automaticamente o pedido quando o PIX é pago."""
    try:
        body = await request.json()
    except Exception:
        body = {}

    if not validate_mp_webhook_signature(request):
        raise HTTPException(status_code=401, detail="Token do webhook Asaas inválido")

    topic = body.get("event") or body.get("type") or body.get("topic") or request.query_params.get("topic") or request.query_params.get("type")
    if topic and not str(topic).startswith("PAYMENT_"):
        return {"ok": True, "ignored": True, "topic": topic}

    payment_obj = body.get("payment") if isinstance(body, dict) else None
    if not isinstance(payment_obj, dict):
        payment_obj = {}

    payment_id = payment_obj.get("id") or body.get("id") or request.query_params.get("id") or request.query_params.get("data.id")
    if not payment_id:
        return {"ok": True, "ignored": True, "reason": "sem payment_id"}

    try:
        mp_payment = get_mercadopago_payment(str(payment_id))
    except Exception as e:
        print("[ASAAS WEBHOOK CONSULT ERROR]", str(e))
        mp_payment = payment_obj or {"id": payment_id, "status": "PENDING"}

    if topic:
        mp_payment["event"] = str(topic)
        if str(topic) in {"PAYMENT_RECEIVED", "PAYMENT_CONFIRMED", "PAYMENT_RECEIVED_IN_CASH"}:
            mp_payment["status"] = mp_payment.get("status") or "RECEIVED"

    external_reference = str(mp_payment.get("externalReference") or mp_payment.get("external_reference") or "")
    walk = None
    if external_reference.startswith("walk_"):
        try:
            walk = db.get(WalkRequest, int(external_reference.split("_", 1)[1]))
        except Exception:
            walk = None
    if not walk:
        walk = db.query(WalkRequest).filter(WalkRequest.mp_payment_id == str(payment_id)).first()
    if not walk:
        return {"ok": True, "ignored": True, "reason": "pedido não encontrado"}

    changed = apply_mp_payment_to_walk(walk, mp_payment)
    messages = []
    if changed or walk.payment_status == "pago":
        messages.append(add_walk_system_message(db, walk, "✅ Pagamento confirmado com sucesso. O pedido foi liberado para o passeador aceitar."))

    db.commit()
    db.refresh(walk)
    payload = walk_to_dict(walk)
    if changed or walk.payment_status == "pago":
        await manager.broadcast({"type": "payment_confirmed", "walk": payload})
        for msg in messages:
            if msg:
                await manager.broadcast({"type": "message", "message": message_to_dict(msg)})
    else:
        await manager.broadcast({"type": "payment_updated", "walk": payload})
    return {"ok": True, "walk_id": walk.id, "payment_status": walk.payment_status, "mp_status": walk.mp_status}

@app.post("/api/payments/asaas/sync/{walk_id}")
@app.post("/api/payments/mercadopago/sync/{walk_id}")
async def sync_asaas_payment(walk_id: int, db: Session = Depends(get_db)):
    walk = db.get(WalkRequest, walk_id)
    if not walk:
        raise HTTPException(status_code=404, detail="Solicitação não encontrada")
    if not walk.mp_payment_id:
        raise HTTPException(status_code=400, detail="Este pedido ainda não tem pagamento Asaas vinculado")
    mp_payment = get_mercadopago_payment(walk.mp_payment_id)
    changed = apply_mp_payment_to_walk(walk, mp_payment)
    messages = []
    if changed or walk.payment_status == "pago":
        messages.append(add_walk_system_message(db, walk, "✅ Pagamento confirmado com sucesso. O pedido foi liberado para o passeador aceitar."))

    db.commit()
    db.refresh(walk)
    payload = walk_to_dict(walk)
    if changed or walk.payment_status == "pago":
        await manager.broadcast({"type": "payment_confirmed", "walk": payload})
        for msg in messages:
            if msg:
                await manager.broadcast({"type": "message", "message": message_to_dict(msg)})
    return payload

@app.post("/api/walks/{walk_id}/start")
async def start_walk(walk_id: int, db: Session = Depends(get_db)):
    walk = db.get(WalkRequest, walk_id)
    if not walk:
        raise HTTPException(status_code=404, detail="Solicitação não encontrada")
    if walk.payment_status != "pago":
        raise HTTPException(status_code=402, detail="Pagamento PIX ainda não confirmado pelo Asaas")
    walk.status = "em_andamento"
    walk.started_at = datetime.utcnow()
    db.commit()
    payload = walk_to_dict(walk)
    await manager.broadcast({"type": "walk_started", "walk": payload})
    return payload

@app.post("/api/walks/{walk_id}/finish")
async def finish_walk(walk_id: int, db: Session = Depends(get_db)):
    walk = db.get(WalkRequest, walk_id)
    if not walk:
        raise HTTPException(status_code=404, detail="Solicitação não encontrada")
    if walk.payment_status != "pago":
        raise HTTPException(status_code=402, detail="Pagamento PIX ainda não confirmado pelo Asaas")

    walk.status = "finalizado"
    walk.finished_at = datetime.utcnow()
    messages = [add_walk_system_message(db, walk, "🐶 Passeio finalizado com sucesso. Obrigado por utilizar o AmigoPet.")]

    if not walk.walker_id or not walk.walker:
        walk.payout_status = "pendente"
        walk.payout_error = "Passeador não vinculado ao passeio"
        messages.append(add_walk_system_message(db, walk, "⚠️ Passeio finalizado, mas o repasse ao passeador ficou pendente porque o passeador não foi identificado."))
    elif (getattr(walk, "payout_status", "") or "") == "pago" and getattr(walk, "payout_transfer_id", ""):
        messages.append(add_walk_system_message(db, walk, "💵 Repasse do passeador já havia sido processado anteriormente."))
    else:
        amount = calculate_walker_payout_amount(db, walk)
        walk.payout_amount = amount
        try:
            transfer = create_asaas_pix_transfer_to_walker(db, walk)
            transfer_status = str(transfer.get("status") or transfer.get("situation") or "solicitado").lower()
            walk.payout_status = transfer_status or "solicitado"
            walk.payout_transfer_id = str(transfer.get("id") or transfer.get("transfer") or "")
            walk.payout_error = ""
            messages.append(add_walk_system_message(
                db,
                walk,
                f"💵 Repasse PIX solicitado com sucesso. Valor: R$ {amount:.2f}. Aguardando confirmação da instituição financeira."
            ))
        except Exception as e:
            walk.payout_status = "erro"
            walk.payout_error = str(e)[:700]
            messages.append(add_walk_system_message(db, walk, "⚠️ Passeio finalizado. O repasse automático ao passeador ficou pendente e precisa ser verificado pela administração."))
            print("[ASAAS PAYOUT ERROR]", {"walk_id": walk.id, "error": str(e)})

    db.commit()
    db.refresh(walk)
    payload = walk_to_dict(walk)
    await manager.broadcast({"type": "walk_finished", "walk": payload})
    for msg in messages:
        if msg:
            await manager.broadcast({"type": "message", "message": message_to_dict(msg)})
    return payload

@app.post("/api/walks/{walk_id}/location")
async def update_location(walk_id: int, data: LocationIn, db: Session = Depends(get_db)):
    walk = db.get(WalkRequest, walk_id)
    if not walk:
        raise HTTPException(status_code=404, detail="Solicitação não encontrada")
    walk.walker_lat = data.lat
    walk.walker_lng = data.lng
    db.commit()
    payload = walk_to_dict(walk)
    await manager.broadcast({"type": "location_updated", "walk": payload})
    return payload

@app.post("/api/walks/{walk_id}/ratings")
async def rate_walk_user(walk_id: int, data: RatingIn, db: Session = Depends(get_db)):
    walk = db.get(WalkRequest, walk_id)
    if not walk:
        raise HTTPException(status_code=404, detail="Passeio não encontrado")
    if walk.status != "finalizado":
        raise HTTPException(status_code=400, detail="A avaliação só pode ser feita após o passeio ser finalizado")

    rater = db.get(User, data.rater_id)
    target = db.get(User, data.target_id)
    if not rater or not target:
        raise HTTPException(status_code=404, detail="Usuário da avaliação não encontrado")
    if data.rating < 1 or data.rating > 5:
        raise HTTPException(status_code=400, detail="A nota deve ser entre 1 e 5 estrelas")

    valid_pair = False
    role_value = ""
    if rater.id == walk.client_id and target.id == walk.walker_id:
        valid_pair = True
        role_value = "client_to_walker"
    if rater.id == walk.walker_id and target.id == walk.client_id:
        valid_pair = True
        role_value = "walker_to_client"
    if not valid_pair:
        raise HTTPException(status_code=403, detail="Esta avaliação não pertence a este passeio")

    existing = db.query(UserRating).filter(UserRating.walk_id == walk_id, UserRating.rater_id == rater.id).first()
    if existing:
        raise HTTPException(status_code=400, detail="Você já avaliou este passeio")

    item = UserRating(
        walk_id=walk_id,
        rater_id=rater.id,
        target_id=target.id,
        rating=int(data.rating),
        comment=str(data.comment or "")[:1000],
        role=role_value,
    )
    db.add(item)
    db.flush()
    recalculate_user_rating(db, target.id)

    add_user_notification(
        db,
        target.id,
        "⭐ Nova avaliação recebida",
        f"{rater.full_name} avaliou você com {int(data.rating)} estrela(s).",
        "rating_received",
        "/passeador" if target.role == "walker" else "/"
    )

    db.commit()
    db.refresh(item)
    payload = rating_to_dict(item)
    await manager.broadcast({"type": "rating_created", "rating": payload})
    return payload

@app.get("/api/walks/{walk_id}/ratings")
def list_walk_ratings(walk_id: int, db: Session = Depends(get_db)):
    items = db.query(UserRating).filter(UserRating.walk_id == walk_id).order_by(UserRating.id.desc()).all()
    return [rating_to_dict(item) for item in items]

@app.get("/api/notifications/{user_id}")
def list_user_notifications(user_id: int, unread_only: bool = False, db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    q = db.query(UserNotification).filter(UserNotification.user_id == user_id)
    if unread_only:
        q = q.filter(UserNotification.is_read == False)
    items = q.order_by(UserNotification.id.desc()).limit(50).all()
    return [notification_to_dict(item) for item in items]

@app.post("/api/notifications/{notification_id}/read")
def mark_notification_read(notification_id: int, db: Session = Depends(get_db)):
    item = db.get(UserNotification, notification_id)
    if not item:
        raise HTTPException(status_code=404, detail="Notificação não encontrada")
    item.is_read = True
    db.commit()
    db.refresh(item)
    return notification_to_dict(item)

@app.post("/api/notifications/read-all/{user_id}")
def mark_all_notifications_read(user_id: int, db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    db.query(UserNotification).filter(UserNotification.user_id == user_id, UserNotification.is_read == False).update({"is_read": True})
    db.commit()
    return {"ok": True}



@app.get("/api/wallet/{walker_id}")
def get_walker_wallet(walker_id: int, db: Session = Depends(get_db)):
    walker = db.get(User, walker_id)
    if not walker or walker.role != "walker":
        raise HTTPException(status_code=404, detail="Passeador não encontrado")

    walks = db.query(WalkRequest).filter(
        WalkRequest.walker_id == walker_id,
        WalkRequest.status == "finalizado"
    ).order_by(WalkRequest.finished_at.desc().nullslast(), WalkRequest.id.desc()).all()

    paid_statuses = {"pago", "paid", "done", "confirmed", "received", "recebido", "finalizado"}
    requested_statuses = {"solicitado", "requested", "processing", "processando", "pending", "pendente"}

    total_gross = 0.0
    total_platform = 0.0
    total_paid = 0.0
    total_pending = 0.0
    total_error = 0.0

    for walk in walks:
        gross = float(walk.estimated_price or 0)
        payout = float(getattr(walk, "payout_amount", 0) or 0)
        if payout <= 0:
            payout = calculate_walker_payout_amount(db, walk)
        platform = max(gross - payout, 0.0)
        status = str(getattr(walk, "payout_status", "") or "pendente").strip().lower()

        total_gross += gross
        total_platform += platform
        if status in paid_statuses:
            total_paid += payout
        elif status == "erro":
            total_error += payout
            total_pending += payout
        else:
            total_pending += payout

    return {
        "walker_id": walker_id,
        "walker_name": walker.full_name,
        "available_balance": round(total_paid, 2),
        "pending_balance": round(total_pending, 2),
        "error_balance": round(total_error, 2),
        "total_gross": round(total_gross, 2),
        "total_platform_fee": round(total_platform, 2),
        "total_paid": round(total_paid, 2),
        "total_pending": round(total_pending, 2),
        "finished_walks": len(walks),
        "wallet_status": "ok",
    }


@app.get("/api/wallet/{walker_id}/history")
def get_walker_wallet_history(walker_id: int, db: Session = Depends(get_db)):
    walker = db.get(User, walker_id)
    if not walker or walker.role != "walker":
        raise HTTPException(status_code=404, detail="Passeador não encontrado")

    walks = db.query(WalkRequest).filter(
        WalkRequest.walker_id == walker_id,
        WalkRequest.status == "finalizado"
    ).order_by(WalkRequest.finished_at.desc().nullslast(), WalkRequest.id.desc()).limit(80).all()

    items = []
    for walk in walks:
        gross = float(walk.estimated_price or 0)
        payout = float(getattr(walk, "payout_amount", 0) or 0)
        if payout <= 0:
            payout = calculate_walker_payout_amount(db, walk)
        platform = max(gross - payout, 0.0)
        payout_status = str(getattr(walk, "payout_status", "") or "pendente").strip().lower()
        items.append({
            "walk_id": walk.id,
            "pet": walk.pet.name if walk.pet else "Pet",
            "client": walk.client.full_name if walk.client else "Cliente",
            "gross_amount": round(gross, 2),
            "walker_amount": round(payout, 2),
            "platform_fee": round(platform, 2),
            "payout_status": payout_status,
            "payout_transfer_id": getattr(walk, "payout_transfer_id", "") or "",
            "payout_error": getattr(walk, "payout_error", "") or "",
            "finished_at": walk.finished_at.isoformat() if walk.finished_at else None,
            "created_at": walk.created_at.isoformat() if walk.created_at else None,
        })
    return items

@app.post("/api/messages")
async def create_message(data: MessageIn, db: Session = Depends(get_db)):
    walk = db.get(WalkRequest, data.request_id)
    if not walk:
        raise HTTPException(status_code=404, detail="Passeio não encontrado para o chat")

    sender = db.get(User, data.sender_id)
    if not sender:
        raise HTTPException(status_code=404, detail="Usuário da mensagem não encontrado")

    if sender.id not in [walk.client_id, walk.walker_id]:
        raise HTTPException(status_code=403, detail="Você não participa deste chat")

    if walk.status not in ["aceito", "em_andamento", "finalizado"]:
        raise HTTPException(status_code=403, detail="Chat liberado somente após o aceite do passeio")

    clean_text = str(data.text or "").strip()
    if not clean_text:
        raise HTTPException(status_code=400, detail="Digite uma mensagem")
    if len(clean_text) > 2000:
        raise HTTPException(status_code=400, detail="Mensagem muito longa")

    msg = Message(
        request_id=data.request_id,
        sender_id=data.sender_id,
        text=clean_text[:2000],
        message_type=(data.message_type or "text")[:30],
    )
    db.add(msg)
    db.flush()

    target_id = walk.walker_id if sender.id == walk.client_id else walk.client_id
    if target_id:
        add_user_notification(
            db,
            target_id,
            "💬 Nova mensagem no chat",
            f"{sender.full_name}: {clean_text[:120]}",
            "message",
            "/passeador" if sender.id == walk.client_id else "/",
        )

    db.commit()
    db.refresh(msg)
    payload = message_to_dict(msg)
    await manager.broadcast({"type": "message", "message": payload, "request_id": msg.request_id})
    return payload

@app.get("/api/messages/{request_id}")
def list_messages(request_id: int, db: Session = Depends(get_db)):
    msgs = db.query(Message).filter(Message.request_id == request_id).order_by(Message.id.asc()).all()
    return [message_to_dict(m) for m in msgs]

@app.post("/api/messages/{request_id}/read/{user_id}")
async def mark_messages_read(request_id: int, user_id: int, db: Session = Depends(get_db)):
    walk = db.get(WalkRequest, request_id)
    if not walk:
        raise HTTPException(status_code=404, detail="Passeio não encontrado")
    if user_id not in [walk.client_id, walk.walker_id]:
        raise HTTPException(status_code=403, detail="Usuário não participa deste chat")
    now = datetime.utcnow()
    db.query(Message).filter(
        Message.request_id == request_id,
        Message.sender_id != user_id,
        Message.read_at == None,
    ).update({"read_at": now}, synchronize_session=False)
    db.commit()
    await manager.broadcast({"type": "messages_read", "request_id": request_id, "reader_id": user_id})
    return {"ok": True, "read_at": now.isoformat()}



@app.get("/manifest.webmanifest")
def manifest_file():
    return FileResponse(FRONTEND_DIR / "manifest.webmanifest", media_type="application/manifest+json")

@app.get("/sw.js")
def service_worker_file():
    return FileResponse(FRONTEND_DIR / "sw.js", media_type="application/javascript")

@app.get("/passeador")
def walker_page():
    walker_file = FRONTEND_DIR / "passeador.html"
    if walker_file.exists():
        return FileResponse(walker_file)
    return FileResponse(FRONTEND_DIR / "index.html")

@app.get("/admin")
def admin_page():
    admin_file = FRONTEND_DIR / "admin.html"
    if admin_file.exists():
        return FileResponse(admin_file)
    return FileResponse(FRONTEND_DIR / "index.html")

@app.get("/")
def index():
    return FileResponse(FRONTEND_DIR / "index.html")

app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")
# resend-force-deploy
