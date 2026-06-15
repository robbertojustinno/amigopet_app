from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, EmailStr
from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text, create_engine, text
from sqlalchemy.orm import Session, declarative_base, relationship, sessionmaker
import requests
import smtplib
from email.message import EmailMessage

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
    created_at = Column(DateTime, default=datetime.utcnow)

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

class MessageIn(BaseModel):
    request_id: int
    sender_id: int
    text: str

class LocationIn(BaseModel):
    lat: float
    lng: float

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
        "neighborhood": u.neighborhood, "city": u.city, "lat": u.lat, "lng": u.lng,
        "rating": u.rating, "available": u.available, "bio": u.bio,
        "zip_code": u.zip_code, "street": u.street, "number": u.number,
        "complement": u.complement, "state": u.state,
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
            ("created_at", "TIMESTAMP DEFAULT NOW()"),
        ]

        for col, ddl in user_columns_sql:
            safe(f"ALTER TABLE users ADD COLUMN IF NOT EXISTS {col} {ddl}", f"add users.{col}")

        for col in ["available", "active", "email_verified", "phone_verified"]:
            safe(f"ALTER TABLE users ALTER COLUMN {col} SET DEFAULT TRUE", f"default users.{col}")
            safe(f"UPDATE users SET {col}=TRUE WHERE {col} IS NULL", f"normalize users.{col}")
            safe(f"ALTER TABLE users ALTER COLUMN {col} SET NOT NULL", f"not null users.{col}")

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


run_lightweight_migrations()
seed_data()
seed_pricing_settings()


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
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

    allowed = ["full_name", "phone", "photo", "document", "neighborhood", "city", "bio"]
    for key in allowed:
        if hasattr(user, key):
            value = payload.get(key, "")
            if key == "photo" and not str(value).strip():
                continue
            setattr(user, key, value)

    db.commit()
    db.refresh(user)
    return user_to_dict(user)

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

    db.commit()
    db.refresh(walk)
    payload = walk_to_dict(walk)
    if changed or walk.payment_status == "pago":
        await manager.broadcast({"type": "payment_confirmed", "walk": payload})
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
    db.commit()
    db.refresh(walk)
    payload = walk_to_dict(walk)
    if changed or walk.payment_status == "pago":
        await manager.broadcast({"type": "payment_confirmed", "walk": payload})
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
    db.commit()
    db.refresh(walk)
    payload = walk_to_dict(walk)
    if changed or walk.payment_status == "pago":
        await manager.broadcast({"type": "payment_confirmed", "walk": payload})
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
    walk.status = "finalizado"
    walk.finished_at = datetime.utcnow()
    db.commit()
    payload = walk_to_dict(walk)
    await manager.broadcast({"type": "walk_finished", "walk": payload})
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

@app.post("/api/messages")
async def create_message(data: MessageIn, db: Session = Depends(get_db)):
    msg = Message(**pydantic_dump(data))
    db.add(msg)
    db.commit()
    db.refresh(msg)
    payload = {"id": msg.id, "request_id": msg.request_id, "sender_id": msg.sender_id, "text": msg.text, "created_at": msg.created_at.isoformat()}
    await manager.broadcast({"type": "message", "message": payload})
    return payload

@app.get("/api/messages/{request_id}")
def list_messages(request_id: int, db: Session = Depends(get_db)):
    msgs = db.query(Message).filter(Message.request_id == request_id).order_by(Message.id.asc()).all()
    return [{"id": m.id, "request_id": m.request_id, "sender_id": m.sender_id, "text": m.text, "created_at": m.created_at.isoformat()} for m in msgs]



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
