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

BASE_DIR = Path(__file__).resolve().parents[2]
FRONTEND_DIR = BASE_DIR / "frontend"
MERCADOPAGO_ACCESS_TOKEN = (os.getenv("MERCADOPAGO_ACCESS_TOKEN") or os.getenv("MERCADO_PAGO_ACCESS_TOKEN") or "").strip()
MERCADOPAGO_WEBHOOK_SECRET = os.getenv("MERCADOPAGO_WEBHOOK_SECRET", "").strip()
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", os.getenv("RENDER_EXTERNAL_URL", "")).rstrip("/")
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

def make_pix_code(walk_id: int, amount: float) -> str:
    token = secrets.token_hex(8).upper()
    return f"000201-AMIGOPET-PIX-SIMULADO-ID{walk_id}-VALOR{amount:.2f}-TOKEN{token}"

def mp_headers(idempotency_key: Optional[str] = None) -> dict:
    headers = {"Authorization": f"Bearer {MERCADOPAGO_ACCESS_TOKEN}", "Content-Type": "application/json"}
    if idempotency_key:
        headers["X-Idempotency-Key"] = idempotency_key
    return headers

def mp_webhook_url() -> Optional[str]:
    if not PUBLIC_BASE_URL:
        return None
    return f"{PUBLIC_BASE_URL}/api/payments/mercadopago/webhook"

def create_mercadopago_pix_payment(walk: WalkRequest) -> dict:
    if not MERCADOPAGO_ACCESS_TOKEN:
        raise RuntimeError("MERCADOPAGO_ACCESS_TOKEN não configurado no Render")

    payer_email = walk.client.email if walk.client and walk.client.email else f"cliente{walk.client_id}@amigopet.local"
    body = {
        "transaction_amount": float(round(walk.estimated_price or 0, 2)),
        "description": f"AmigoPet - Passeio #{walk.id}",
        "payment_method_id": "pix",
        "payer": {"email": payer_email},
        "external_reference": f"walk_{walk.id}",
        "metadata": {"walk_id": walk.id, "client_id": walk.client_id, "walker_id": walk.walker_id},
    }
    notification_url = mp_webhook_url()
    if notification_url:
        body["notification_url"] = notification_url

    res = requests.post(
        "https://api.mercadopago.com/v1/payments",
        json=body,
        headers=mp_headers(f"amigopet-walk-{walk.id}-{uuid.uuid4().hex}"),
        timeout=20,
    )
    try:
        data = res.json()
    except Exception:
        data = {"raw": res.text}
    if res.status_code >= 400:
        raise RuntimeError(f"Mercado Pago recusou criação do PIX: {data}")
    return data

def get_mercadopago_payment(payment_id: str) -> dict:
    if not MERCADOPAGO_ACCESS_TOKEN:
        raise RuntimeError("MERCADOPAGO_ACCESS_TOKEN não configurado no Render")
    res = requests.get(
        f"https://api.mercadopago.com/v1/payments/{payment_id}",
        headers=mp_headers(),
        timeout=20,
    )
    try:
        data = res.json()
    except Exception:
        data = {"raw": res.text}
    if res.status_code >= 400:
        raise RuntimeError(f"Erro ao consultar pagamento Mercado Pago: {data}")
    return data

def validate_mp_webhook_signature(request: Request, payment_id: Optional[str]) -> bool:
    """Validação opcional da assinatura do webhook do Mercado Pago.
    Configure MERCADOPAGO_WEBHOOK_SECRET no Render para ativar.
    """
    if not MERCADOPAGO_WEBHOOK_SECRET:
        return True
    signature = request.headers.get("x-signature", "")
    request_id = request.headers.get("x-request-id", "")
    if not signature or not request_id:
        return False

    parts = {}
    for item in signature.split(","):
        if "=" in item:
            k, v = item.strip().split("=", 1)
            parts[k] = v
    ts = parts.get("ts", "")
    v1 = parts.get("v1", "")
    if not ts or not v1:
        return False

    data_id = request.query_params.get("data.id") or payment_id or ""
    manifest = f"id:{data_id};request-id:{request_id};ts:{ts};"
    expected = hmac.new(MERCADOPAGO_WEBHOOK_SECRET.encode("utf-8"), manifest.encode("utf-8"), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, v1)

def apply_mp_payment_to_walk(walk: WalkRequest, mp_payment: dict) -> bool:
    before = walk.payment_status
    status = str(mp_payment.get("status") or "")
    status_detail = str(mp_payment.get("status_detail") or "")

    walk.mp_payment_id = str(mp_payment.get("id") or walk.mp_payment_id or "")
    walk.mp_status = status
    walk.mp_status_detail = status_detail

    transaction_data = (mp_payment.get("point_of_interaction") or {}).get("transaction_data") or {}
    qr_code = transaction_data.get("qr_code") or ""
    qr_code_base64 = transaction_data.get("qr_code_base64") or ""
    ticket_url = transaction_data.get("ticket_url") or ""

    if qr_code:
        walk.mp_qr_code = qr_code
        walk.pix_code = qr_code
    if qr_code_base64:
        walk.mp_qr_code_base64 = qr_code_base64
    if ticket_url:
        walk.mp_ticket_url = ticket_url

    if status == "approved":
        walk.payment_status = "pago"
        if walk.status in ["pendente", "convite_enviado"]:
            walk.status = "pagamento_confirmado"
    elif status in ["rejected", "cancelled"]:
        walk.payment_status = "recusado"
    elif status in ["pending", "in_process"]:
        walk.payment_status = "aguardando"

    return before != walk.payment_status

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
            dict(full_name="Passeador Profissional", email="passeador@amigopet.com", role="walker", phone="(21) 99999-0000", neighborhood="Piabetá", city="Magé", lat=-22.5900, lng=-43.1810, rating=4.9, available=True, active=True, email_verified=True, phone_verified=True, bio="Passeador verificado, experiência com cães pequenos e grandes."),
            dict(full_name="Ana Walker Premium", email="ana@amigopet.com", role="walker", phone="(21) 97777-2222", neighborhood="Centro", city="Magé", lat=-22.5852, lng=-43.1881, rating=4.8, available=True, active=True, email_verified=True, phone_verified=True, bio="Rotas seguras, envio de fotos e cuidado especial."),
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

@app.get("/api/users")
def users(role: Optional[str] = None, db: Session = Depends(get_db)):
    q = db.query(User)
    if role:
        q = q.filter(User.role == role)
    return [user_to_dict(u) for u in q.order_by(User.rating.desc(), User.id.asc()).all()]

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

    # PREÇO DE TESTE PIX: 5 minutos = R$ 1,00.
    # Mantém a fórmula normal para os demais tempos.
    if int(data.duration_minutes or 30) <= 5:
        price = 1.0
    else:
        price = 14 + (data.duration_minutes / 30) * 16 + max(data.dogs_count - 1, 0) * 9

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

        # Mercado Pago real: cria cobrança PIX e salva QR Code/copia-e-cola no pedido.
        try:
            mp_payment = create_mercadopago_pix_payment(walk)
            apply_mp_payment_to_walk(walk, mp_payment)
            db.commit()
            db.refresh(walk)
        except Exception as mp_error:
            db.rollback()
            walk = db.get(WalkRequest, walk.id)
            if walk:
                walk.pix_code = make_pix_code(walk.id, walk.estimated_price)
                walk.mp_status = "mp_error"
                walk.mp_status_detail = str(mp_error)[:120]
                db.commit()
                db.refresh(walk)
            print("[MERCADO PAGO PIX ERROR]", str(mp_error))
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
        raise HTTPException(status_code=402, detail="Aguardando pagamento PIX confirmado pelo Mercado Pago antes do aceite")
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
        raise HTTPException(status_code=400, detail="Este pedido ainda não tem pagamento Mercado Pago vinculado. Crie um novo pedido para gerar o PIX real.")

    if not MERCADOPAGO_ACCESS_TOKEN:
        raise HTTPException(status_code=500, detail="Token do Mercado Pago não configurado no Render.")

    try:
        mp_payment = get_mercadopago_payment(walk.mp_payment_id)
        changed = apply_mp_payment_to_walk(walk, mp_payment)
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail="Não foi possível consultar o Mercado Pago: " + str(e)[:700])

    db.commit()
    db.refresh(walk)
    payload = walk_to_dict(walk)
    if changed or walk.payment_status == "pago":
        await manager.broadcast({"type": "payment_confirmed", "walk": payload})
    return payload

@app.post("/api/payments/mercadopago/webhook")
@app.post("/api/payments/webhook")
async def mercadopago_webhook(request: Request, db: Session = Depends(get_db)):
    """Webhook real do Mercado Pago. Ele consulta o pagamento e confirma automaticamente o pedido."""
    try:
        body = await request.json()
    except Exception:
        body = {}

    payment_id = None
    data = body.get("data") if isinstance(body, dict) else None
    if isinstance(data, dict):
        payment_id = data.get("id")
    payment_id = payment_id or request.query_params.get("data.id") or request.query_params.get("id")
    topic = body.get("type") or body.get("topic") or request.query_params.get("topic") or request.query_params.get("type")

    if not payment_id:
        return {"ok": True, "ignored": True, "reason": "sem payment_id"}
    if not validate_mp_webhook_signature(request, str(payment_id)):
        raise HTTPException(status_code=401, detail="Assinatura Mercado Pago inválida")
    if topic and str(topic) not in ["payment", "payments"]:
        return {"ok": True, "ignored": True, "topic": topic}

    try:
        mp_payment = get_mercadopago_payment(str(payment_id))
    except Exception as e:
        print("[MP WEBHOOK CONSULT ERROR]", str(e))
        return JSONResponse(status_code=200, content={"ok": False, "error": str(e)[:300]})

    external_reference = str(mp_payment.get("external_reference") or "")
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

@app.post("/api/payments/mercadopago/sync/{walk_id}")
async def sync_mercadopago_payment(walk_id: int, db: Session = Depends(get_db)):
    walk = db.get(WalkRequest, walk_id)
    if not walk:
        raise HTTPException(status_code=404, detail="Solicitação não encontrada")
    if not walk.mp_payment_id:
        raise HTTPException(status_code=400, detail="Este pedido ainda não tem pagamento Mercado Pago vinculado")
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
        raise HTTPException(status_code=402, detail="Pagamento PIX ainda não confirmado pelo Mercado Pago")
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
