from __future__ import annotations

import hashlib
import hmac
import json
import base64
import asyncio
import logging
import os
import secrets
import threading
import time
import uuid
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, EmailStr
from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text, create_engine
from sqlalchemy.orm import Session, declarative_base, relationship, sessionmaker
import requests
import smtplib
try:
    import bcrypt
except ImportError:
    bcrypt = None
try:
    import redis
except ImportError:
    redis = None
from email.message import EmailMessage
from urllib.parse import urlencode, quote

logger = logging.getLogger("amigopet")

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
APP_ENV = os.getenv("APP_ENV", os.getenv("ENV", "development")).strip().lower()
IS_PRODUCTION = APP_ENV in {"production", "prod"} or bool(os.getenv("RENDER_EXTERNAL_URL", "").strip())
DEV_SEED_PASSWORD = os.getenv("DEV_SEED_PASSWORD", "123456")
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
REDIS_URL = os.getenv("REDIS_URL", "").strip()
WS_REDIS_CHANNEL = os.getenv("WS_REDIS_CHANNEL", "amigopet:ws-events").strip() or "amigopet:ws-events"
INSTANCE_ID = os.getenv("INSTANCE_ID", uuid.uuid4().hex)
SESSION_COOKIE_NAME = "amigopet_session"
CSRF_COOKIE_NAME = "amigopet_csrf"
CSRF_HEADER_NAME = "x-csrf-token"
SESSION_MAX_AGE_SECONDS = 60 * 60 * 24 * 180
SESSION_SECRET = os.getenv("SESSION_SECRET", "").strip()
if IS_PRODUCTION:
    if len(SESSION_SECRET) < 32:
        raise RuntimeError("SESSION_SECRET deve estar definido com pelo menos 32 caracteres em producao")
else:
    SESSION_SECRET = SESSION_SECRET or "amigopet-dev-session-secret"

CORS_ORIGINS = [origin.strip().rstrip("/") for origin in os.getenv("CORS_ORIGINS", "").split(",") if origin.strip()]
if IS_PRODUCTION:
    if not CORS_ORIGINS:
        raise RuntimeError("CORS_ORIGINS deve estar definido em producao com origens explicitas")
    if any("*" in origin for origin in CORS_ORIGINS):
        raise RuntimeError("CORS_ORIGINS nao pode usar wildcard em producao")
else:
    CORS_ORIGINS = CORS_ORIGINS or ["*"]

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
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


SECURITY_CSP = "; ".join([
    "default-src 'self'",
    "script-src 'self' 'unsafe-inline' https://unpkg.com",
    "style-src 'self' 'unsafe-inline' https://unpkg.com",
    "img-src 'self' data: blob: https://unpkg.com https://api.dicebear.com https://api.qrserver.com https://*.tile.openstreetmap.org",
    "connect-src 'self' http: https: ws: wss:",
    "font-src 'self' data:",
    "manifest-src 'self'",
    "worker-src 'self'",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
])

SECURITY_PERMISSIONS_POLICY = ", ".join([
    "accelerometer=()",
    "autoplay=()",
    "camera=(self)",
    "clipboard-read=()",
    "clipboard-write=(self)",
    "geolocation=(self)",
    "gyroscope=()",
    "magnetometer=()",
    "microphone=()",
    "payment=()",
    "usb=()",
])


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("Content-Security-Policy", SECURITY_CSP)
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", SECURITY_PERMISSIONS_POLICY)
    response.headers.setdefault("X-Permitted-Cross-Domain-Policies", "none")
    response.headers.setdefault("Cross-Origin-Resource-Policy", "same-origin")
    if IS_PRODUCTION:
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    return response


@app.on_event("startup")
async def start_websocket_bus():
    manager.set_loop(asyncio.get_running_loop())
    websocket_bus.start()

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

class EventLog(Base):
    __tablename__ = "event_logs"
    id = Column(Integer, primary_key=True, index=True)
    walk_id = Column(Integer, ForeignKey("walk_requests.id"), nullable=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    event_type = Column(String(80), default="system", index=True)
    title = Column(String(180), nullable=False)
    details = Column(Text, default="")
    actor_role = Column(String(40), default="system")
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    walk = relationship("WalkRequest")
    user = relationship("User")

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
        self.active: dict[WebSocket, int] = {}
        self.loop: Optional[asyncio.AbstractEventLoop] = None

    def set_loop(self, loop: asyncio.AbstractEventLoop):
        self.loop = loop

    async def connect(self, websocket: WebSocket, user_id: int):
        self.set_loop(asyncio.get_running_loop())
        await websocket.accept()
        self.active[websocket] = user_id

    def disconnect(self, websocket: WebSocket):
        self.active.pop(websocket, None)

    async def deliver_to_users(self, payload: dict, user_ids: set[int]):
        dead = []
        for ws, user_id in list(self.active.items()):
            if user_id not in user_ids:
                continue
            try:
                await ws.send_json(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)

    async def send_to_users(self, payload: dict, user_ids: set[int], publish: bool = True):
        await self.deliver_to_users(payload, user_ids)
        if publish:
            websocket_bus.publish_users(payload, user_ids)

    async def broadcast_authenticated(self, payload: dict, publish: bool = True):
        await self.deliver_to_users(payload, set(self.active.values()))
        if publish:
            websocket_bus.publish_broadcast(payload)

manager = ConnectionManager()


class RedisWebSocketBus:
    def __init__(self):
        self.enabled = bool(REDIS_URL and redis is not None)
        self.client = None
        self.thread: Optional[threading.Thread] = None
        self.started = False

    def start(self):
        if not self.enabled or self.started:
            return
        try:
            self.client = redis.Redis.from_url(REDIS_URL, decode_responses=True)
            self.client.ping()
        except Exception as e:
            print("[REDIS WS WARNING] Redis indisponivel; usando WebSocket local em memoria:", e)
            self.enabled = False
            return
        self.started = True
        self.thread = threading.Thread(target=self._listen, name="amigopet-redis-ws", daemon=True)
        self.thread.start()

    def publish(self, message: dict):
        if not self.enabled or not self.client:
            return
        try:
            payload = {**message, "source": INSTANCE_ID}
            self.client.publish(WS_REDIS_CHANNEL, json.dumps(payload, default=str))
        except Exception as e:
            print("[REDIS WS WARNING] Falha ao publicar evento:", e)

    def publish_users(self, payload: dict, user_ids: set[int]):
        self.publish({"kind": "users", "payload": payload, "user_ids": list(user_ids)})

    def publish_broadcast(self, payload: dict):
        self.publish({"kind": "broadcast", "payload": payload})

    def publish_walk_event(self, payload: dict, walk_id: int, include_admin: bool, include_available_walkers: bool):
        self.publish({
            "kind": "walk",
            "payload": payload,
            "walk_id": int(walk_id),
            "include_admin": bool(include_admin),
            "include_available_walkers": bool(include_available_walkers),
        })

    def _listen(self):
        try:
            pubsub = self.client.pubsub(ignore_subscribe_messages=True)
            pubsub.subscribe(WS_REDIS_CHANNEL)
            for item in pubsub.listen():
                if item.get("type") != "message":
                    continue
                try:
                    message = json.loads(item.get("data") or "{}")
                except Exception:
                    continue
                if message.get("source") == INSTANCE_ID:
                    continue
                loop = manager.loop
                if loop and loop.is_running():
                    asyncio.run_coroutine_threadsafe(handle_redis_ws_message(message), loop)
        except Exception as e:
            print("[REDIS WS WARNING] Listener encerrado; WebSocket remoto indisponivel:", e)


websocket_bus = RedisWebSocketBus()

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


RATE_LIMIT_BUCKETS: dict[str, list[float]] = {}
RATE_LIMIT_LOCK = threading.Lock()
RATE_LIMIT_REDIS_CLIENT = None
RATE_LIMIT_FALLBACK_WARNED: set[str] = set()


def normalize_rate_limit_part(value: object) -> str:
    return str(value or "").strip().lower()[:120]


def rate_limit_key(request: Request, scope: str, identifier: object = "") -> str:
    ip = client_ip_from_request(request) or "unknown"
    return ":".join([
        "amigopet",
        "rate_limit",
        normalize_rate_limit_part(scope),
        normalize_rate_limit_part(ip),
        normalize_rate_limit_part(identifier),
    ])


def get_rate_limit_redis_client():
    global RATE_LIMIT_REDIS_CLIENT
    if RATE_LIMIT_REDIS_CLIENT is not None:
        return RATE_LIMIT_REDIS_CLIENT
    if not REDIS_URL or redis is None:
        return None
    RATE_LIMIT_REDIS_CLIENT = redis.Redis.from_url(REDIS_URL, decode_responses=True)
    return RATE_LIMIT_REDIS_CLIENT


def warn_rate_limit_memory_fallback(reason: str) -> None:
    if reason in RATE_LIMIT_FALLBACK_WARNED:
        return
    RATE_LIMIT_FALLBACK_WARNED.add(reason)
    logger.warning("Rate limit Redis indisponivel; usando fallback em memoria.", extra={"reason": reason})


def enforce_redis_rate_limit(key: str, limit: int, window_seconds: int) -> bool:
    client = get_rate_limit_redis_client()
    if client is None:
        warn_rate_limit_memory_fallback("redis_url_absent_or_client_unavailable")
        return False

    try:
        pipe = client.pipeline(transaction=True)
        pipe.incr(key)
        pipe.expire(key, int(window_seconds))
        count, _ = pipe.execute()
        count = int(count or 0)
        if count > limit:
            ttl = int(client.ttl(key) or window_seconds)
            retry_after = max(1, ttl if ttl > 0 else int(window_seconds))
            raise HTTPException(
                status_code=429,
                detail="Muitas tentativas. Aguarde alguns instantes e tente novamente.",
                headers={"Retry-After": str(retry_after)},
            )
        return True
    except HTTPException:
        raise
    except Exception as e:
        warn_rate_limit_memory_fallback(f"redis_error:{type(e).__name__}")
        return False


def enforce_rate_limit(request: Request, scope: str, limit: int, window_seconds: int, identifier: object = "") -> None:
    now = time.time()
    cutoff = now - window_seconds
    key = rate_limit_key(request, scope, identifier)

    if REDIS_URL:
        if enforce_redis_rate_limit(key, limit, window_seconds):
            return
    else:
        warn_rate_limit_memory_fallback("redis_url_not_configured")

    with RATE_LIMIT_LOCK:
        bucket = [item for item in RATE_LIMIT_BUCKETS.get(key, []) if item > cutoff]
        if len(bucket) >= limit:
            retry_after = max(1, int(window_seconds - (now - bucket[0])))
            RATE_LIMIT_BUCKETS[key] = bucket
            raise HTTPException(
                status_code=429,
                detail="Muitas tentativas. Aguarde alguns instantes e tente novamente.",
                headers={"Retry-After": str(retry_after)},
            )
        bucket.append(now)
        RATE_LIMIT_BUCKETS[key] = bucket

        if len(RATE_LIMIT_BUCKETS) > 10000:
            for old_key, old_bucket in list(RATE_LIMIT_BUCKETS.items()):
                fresh = [item for item in old_bucket if item > cutoff]
                if fresh:
                    RATE_LIMIT_BUCKETS[old_key] = fresh
                else:
                    RATE_LIMIT_BUCKETS.pop(old_key, None)


def hash_password(password: str) -> str:
    """Hash estável compatível com Python 3.14 no Render."""
    if bcrypt is None:
        raise RuntimeError("Dependencia bcrypt nao instalada. Execute pip install -r requirements.txt")
    return bcrypt.hashpw(str(password).encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")

def verify_password(password: str, password_hash: str) -> bool:
    if not password_hash:
        return False
    if password_hash.startswith(("$2a$", "$2b$", "$2y$")):
        if bcrypt is None:
            return False
        try:
            return bcrypt.checkpw(str(password).encode("utf-8"), password_hash.encode("utf-8"))
        except Exception:
            return False
    if password_hash.startswith("sha256$"):
        try:
            _, salt, digest = password_hash.split("$", 2)
            candidate = hashlib.sha256(f"{salt}:{password}".encode("utf-8")).hexdigest()
            return secrets.compare_digest(candidate, digest)
        except Exception:
            return False
    return False


def password_needs_rehash(password_hash: str) -> bool:
    if not password_hash.startswith(("$2a$", "$2b$", "$2y$")):
        return True
    try:
        rounds = int(password_hash.split("$", 3)[2])
        return rounds < 12
    except Exception:
        return True

def make_session_token(user_id: int) -> str:
    issued = str(int(datetime.utcnow().timestamp()))
    payload = f"{int(user_id)}:{issued}"
    signature = hmac.new(SESSION_SECRET.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    raw = f"{payload}:{signature}".encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("utf-8")


def make_csrf_token(user_id: int) -> str:
    issued = str(int(datetime.utcnow().timestamp()))
    nonce = secrets.token_urlsafe(24)
    payload = f"{int(user_id)}:{issued}:{nonce}"
    signature = hmac.new(SESSION_SECRET.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    raw = f"{payload}:{signature}".encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("utf-8")


def read_session_user_id(token: str) -> Optional[int]:
    if not token:
        return None
    try:
        raw = base64.urlsafe_b64decode(token.encode("utf-8")).decode("utf-8")
        user_id, issued, signature = raw.split(":", 2)
        payload = f"{int(user_id)}:{int(issued)}"
        expected = hmac.new(SESSION_SECRET.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()
        if not secrets.compare_digest(signature, expected):
            return None
        if int(datetime.utcnow().timestamp()) - int(issued) > SESSION_MAX_AGE_SECONDS:
            return None
        return int(user_id)
    except Exception:
        return None


def read_csrf_user_id(token: str) -> Optional[int]:
    if not token:
        return None
    try:
        raw = base64.urlsafe_b64decode(token.encode("utf-8")).decode("utf-8")
        user_id, issued, nonce, signature = raw.split(":", 3)
        payload = f"{int(user_id)}:{int(issued)}:{nonce}"
        expected = hmac.new(SESSION_SECRET.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()
        if not secrets.compare_digest(signature, expected):
            return None
        if int(datetime.utcnow().timestamp()) - int(issued) > SESSION_MAX_AGE_SECONDS:
            return None
        return int(user_id)
    except Exception:
        return None


def attach_csrf_cookie(response: Response, user_id: int) -> Response:
    response.set_cookie(
        key=CSRF_COOKIE_NAME,
        value=make_csrf_token(user_id),
        max_age=SESSION_MAX_AGE_SECONDS,
        httponly=False,
        secure=True,
        samesite="lax",
        path="/",
    )
    return response


def attach_session_cookie(response: Response, user_id: int) -> Response:
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=make_session_token(user_id),
        max_age=SESSION_MAX_AGE_SECONDS,
        httponly=True,
        secure=True,
        samesite="lax",
        path="/",
    )
    attach_csrf_cookie(response, user_id)
    return response


def clear_session_cookie(response: Response) -> Response:
    response.delete_cookie(key=SESSION_COOKIE_NAME, path="/")
    response.delete_cookie(key=CSRF_COOKIE_NAME, path="/")
    return response


def session_user_from_request(request: Request, db: Session) -> Optional[User]:
    user_id = read_session_user_id(request.cookies.get(SESSION_COOKIE_NAME, ""))
    if not user_id:
        return None
    user = db.get(User, user_id)
    if not user or not getattr(user, "active", True):
        return None
    return user


def validate_csrf_request(request: Request, user_id: int) -> None:
    if request.method.upper() not in {"POST", "PUT", "PATCH", "DELETE"}:
        return
    cookie_token = request.cookies.get(CSRF_COOKIE_NAME, "")
    header_token = request.headers.get(CSRF_HEADER_NAME, "")
    if not cookie_token or not header_token:
        raise HTTPException(status_code=403, detail="Token CSRF ausente")
    if not secrets.compare_digest(cookie_token, header_token):
        raise HTTPException(status_code=403, detail="Token CSRF invalido")
    if read_csrf_user_id(header_token) != int(user_id):
        raise HTTPException(status_code=403, detail="Token CSRF invalido")


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    user = session_user_from_request(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Autenticação necessária")
    validate_csrf_request(request, user.id)
    return user


def get_current_client(user: User = Depends(get_current_user)) -> User:
    if user.role != "client":
        raise HTTPException(status_code=403, detail="Acesso exclusivo para clientes")
    return user


def get_current_walker(user: User = Depends(get_current_user)) -> User:
    if user.role != "walker":
        raise HTTPException(status_code=403, detail="Acesso exclusivo para passeadores")
    return user


def get_current_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Acesso exclusivo para administradores")
    return user


def walk_event_user_ids(db: Session, walk: WalkRequest, include_admin: bool = True, include_available_walkers: bool = False) -> set[int]:
    user_ids = {user_id for user_id in (walk.client_id, walk.walker_id) if user_id}
    if include_admin:
        user_ids.update(user_id for (user_id,) in db.query(User.id).filter(User.role == "admin", User.active.is_(True)).all())
    if include_available_walkers and not walk.walker_id:
        user_ids.update(user_id for (user_id,) in db.query(User.id).filter(User.role == "walker", User.active.is_(True), User.available.is_(True)).all())
    return user_ids


async def send_walk_event(payload: dict, db: Session, walk: WalkRequest, include_admin: bool = True, include_available_walkers: bool = False, publish: bool = True) -> None:
    user_ids = walk_event_user_ids(db, walk, include_admin, include_available_walkers)
    if "walk" not in payload:
        await manager.send_to_users(payload, user_ids, publish=publish)
        return

    dead = []
    for ws, user_id in list(manager.active.items()):
        if user_id not in user_ids:
            continue
        user = db.get(User, user_id)
        if not user or not user.active:
            dead.append(ws)
            continue
        if user.role == "admin":
            context = "admin"
        elif user.id == walk.client_id:
            context = "client"
        else:
            context = "walker"
        item_payload = dict(payload)
        item_payload["walk"] = walk_to_dict(walk, context)
        try:
            await ws.send_json(item_payload)
        except Exception:
            dead.append(ws)
    for ws in dead:
        manager.disconnect(ws)
    if publish:
        websocket_bus.publish_walk_event(payload, walk.id, include_admin, include_available_walkers)


async def handle_redis_ws_message(message: dict) -> None:
    kind = message.get("kind")
    payload = message.get("payload") if isinstance(message.get("payload"), dict) else {}
    if kind == "users":
        user_ids = {int(user_id) for user_id in message.get("user_ids", []) if str(user_id).isdigit()}
        await manager.send_to_users(payload, user_ids, publish=False)
        return
    if kind == "broadcast":
        await manager.broadcast_authenticated(payload, publish=False)
        return
    if kind == "walk":
        db = SessionLocal()
        try:
            walk = db.get(WalkRequest, int(message.get("walk_id") or 0))
            if walk:
                await send_walk_event(
                    payload,
                    db,
                    walk,
                    include_admin=bool(message.get("include_admin", True)),
                    include_available_walkers=bool(message.get("include_available_walkers", False)),
                    publish=False,
                )
        finally:
            db.close()


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


def public_walker_to_dict(u: User) -> dict:
    return {
        "id": u.id,
        "full_name": u.full_name,
        "role": u.role,
        "photo": u.photo,
        "neighborhood": u.neighborhood,
        "city": u.city,
        "lat": u.lat,
        "lng": u.lng,
        "rating": u.rating,
        "available": u.available,
        "bio": u.bio,
    }


def admin_user_list_to_dict(u: User) -> dict:
    return {
        "id": u.id,
        "full_name": u.full_name,
        "email": u.email,
        "role": u.role,
        "phone": u.phone,
        "city": u.city,
        "available": u.available,
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


ASAAS_PIX_TRANSFER_GENERIC_ERROR = "Não foi possível realizar a transferência PIX. Tente novamente mais tarde."
ASAAS_PIX_TRANSFER_INSUFFICIENT_BALANCE_ERROR = "Transferência PIX não realizada. Saldo insuficiente na conta Asaas."
ASAAS_PIX_PAYMENT_GENERIC_ERROR = "Não foi possível gerar o PIX Asaas agora. Tente novamente em instantes."


class AsaasPayoutError(RuntimeError):
    def __init__(self, public_message: str, raw_response: object):
        super().__init__(public_message)
        self.public_message = public_message
        self.raw_response = raw_response


def _asaas_error_items(data: object) -> list[dict]:
    if isinstance(data, dict):
        errors = data.get("errors")
        if isinstance(errors, list):
            return [item for item in errors if isinstance(item, dict)]
    return []


def friendly_asaas_pix_transfer_error(data: object) -> str:
    for item in _asaas_error_items(data):
        code = str(item.get("code") or "").strip().lower()
        description = str(item.get("description") or item.get("message") or "").strip().lower()
        if code == "invalid_action" and "saldo insuficiente" in description:
            return ASAAS_PIX_TRANSFER_INSUFFICIENT_BALANCE_ERROR
    return ASAAS_PIX_TRANSFER_GENERIC_ERROR


def public_payout_error(error: Exception) -> str:
    if isinstance(error, AsaasPayoutError):
        return error.public_message
    return ASAAS_PIX_TRANSFER_GENERIC_ERROR


def public_asaas_pix_payment_error(error: Exception) -> str:
    text = str(error or "").strip().lower()
    if "cpf/cnpj" in text:
        return "Não foi possível gerar o PIX Asaas. Verifique os dados do CPF/CNPJ do cliente."
    return ASAAS_PIX_PAYMENT_GENERIC_ERROR


def sanitize_public_payout_error_text(value: object) -> str:
    """Converte erros antigos/brutos do Asaas em texto seguro para usuários."""
    text = str(value or "").strip()
    if not text:
        return ""

    lowered = text.lower()
    if "saldo insuficiente" in lowered:
        return ASAAS_PIX_TRANSFER_INSUFFICIENT_BALANCE_ERROR

    raw_markers = [
        "{'errors'",
        '"errors"',
        "http_status",
        "invalid_action",
        "'code'",
        '"code"',
        "'reason'",
        '"reason"',
        "raw_response",
        "traceback",
    ]
    if any(marker in lowered for marker in raw_markers):
        return ASAAS_PIX_TRANSFER_GENERIC_ERROR

    return text[:220]


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
        return not IS_PRODUCTION
    received = request.headers.get("asaas-access-token", "")
    return secrets.compare_digest(received, ASAAS_WEBHOOK_TOKEN)


ASAAS_PAID_STATUSES = {"RECEIVED", "CONFIRMED", "RECEIVED_IN_CASH"}
ASAAS_KNOWN_PAYMENT_STATUSES = {
    "PENDING",
    "RECEIVED",
    "CONFIRMED",
    "OVERDUE",
    "REFUNDED",
    "RECEIVED_IN_CASH",
    "REFUND_REQUESTED",
    "REFUND_IN_PROGRESS",
    "CHARGEBACK_REQUESTED",
    "CHARGEBACK_DISPUTE",
    "AWAITING_CHARGEBACK_REVERSAL",
    "DUNNING_REQUESTED",
    "DUNNING_RECEIVED",
    "AWAITING_RISK_ANALYSIS",
    "DELETED",
    "CANCELLED",
}


def _asaas_str(value) -> str:
    return str(value or "").strip()


def _asaas_external_reference(payment: dict) -> str:
    return _asaas_str(payment.get("externalReference") or payment.get("external_reference"))


def _asaas_customer_id(payment: dict) -> str:
    customer = payment.get("customer")
    if isinstance(customer, dict):
        return _asaas_str(customer.get("id"))
    return _asaas_str(customer)


def _asaas_amount(value) -> Optional[Decimal]:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError):
        return None


def validate_asaas_payment_for_walk(
    walk: WalkRequest,
    asaas_payment: dict,
    payment_id: str,
    webhook_payment: Optional[dict] = None,
) -> None:
    if not isinstance(asaas_payment, dict):
        raise HTTPException(status_code=502, detail="Resposta inválida do Asaas")

    api_payment_id = _asaas_str(asaas_payment.get("id"))
    if not api_payment_id or api_payment_id != _asaas_str(payment_id):
        raise HTTPException(status_code=400, detail="payment_id do Asaas não confere")

    if walk.mp_payment_id and _asaas_str(walk.mp_payment_id) != api_payment_id:
        raise HTTPException(status_code=409, detail="Pagamento não pertence ao pedido")

    external_reference = _asaas_external_reference(asaas_payment)
    if external_reference != f"walk_{walk.id}":
        raise HTTPException(status_code=409, detail="externalReference do Asaas não confere")

    expected_value = _asaas_amount(walk.estimated_price)
    asaas_value = _asaas_amount(asaas_payment.get("value"))
    if expected_value is not None and asaas_value is not None and asaas_value != expected_value:
        raise HTTPException(status_code=409, detail="Valor do pagamento não confere")

    currency = _asaas_str(asaas_payment.get("currency") or asaas_payment.get("currencyCode")).upper()
    if currency and currency != "BRL":
        raise HTTPException(status_code=409, detail="Moeda do pagamento não confere")

    if isinstance(webhook_payment, dict):
        webhook_customer = _asaas_customer_id(webhook_payment)
        api_customer = _asaas_customer_id(asaas_payment)
        if webhook_customer and api_customer and webhook_customer != api_customer:
            raise HTTPException(status_code=409, detail="Customer do pagamento não confere")

    status = _asaas_str(asaas_payment.get("status")).upper()
    if not status:
        raise HTTPException(status_code=400, detail="Status do pagamento ausente")
    if status not in ASAAS_KNOWN_PAYMENT_STATUSES:
        raise HTTPException(status_code=409, detail="Status do pagamento inválido")


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

    if status in ASAAS_PAID_STATUSES:
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
        print("[ASAAS PAYOUT API ERROR]", {
            "walk_id": walk.id,
            "status_code": res.status_code,
            "response": data,
        })
        raise AsaasPayoutError(friendly_asaas_pix_transfer_error(data), data)
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

def event_log_to_dict(item: EventLog) -> dict:
    return {
        "id": item.id,
        "walk_id": item.walk_id,
        "user_id": item.user_id,
        "event_type": item.event_type or "system",
        "title": item.title,
        "details": item.details or "",
        "actor_role": item.actor_role or "system",
        "created_at": item.created_at.isoformat() if item.created_at else None,
    }

def add_event_log(db: Session, title: str, event_type: str = "system", walk: Optional[WalkRequest] = None, user_id: Optional[int] = None, details: str = "", actor_role: str = "system") -> Optional[EventLog]:
    try:
        item = EventLog(
            walk_id=walk.id if walk else None,
            user_id=user_id,
            event_type=str(event_type or "system")[:80],
            title=str(title or "Evento")[:180],
            details=str(details or "")[:1200],
            actor_role=str(actor_role or "system")[:40],
        )
        db.add(item)
        db.flush()
        return item
    except Exception as e:
        print("[EVENT LOG WARNING]", str(e))
        return None

def build_walk_timeline(db: Session, walk: WalkRequest) -> list[dict]:
    events = db.query(EventLog).filter(EventLog.walk_id == walk.id).order_by(EventLog.created_at.asc(), EventLog.id.asc()).all()
    if events:
        return [event_log_to_dict(item) for item in events]

    fallback = []
    def add(title, event_type, created_at, details=""):
        if created_at:
            fallback.append({
                "id": 0,
                "walk_id": walk.id,
                "user_id": None,
                "event_type": event_type,
                "title": title,
                "details": details,
                "actor_role": "system",
                "created_at": created_at.isoformat(),
            })

    add("📨 Convite criado", "walk_created", walk.created_at, "Pedido criado no AmigoPet.")
    if getattr(walk, "mp_payment_id", ""):
        add("💳 PIX Asaas gerado", "pix_created", walk.created_at, f"Pagamento: {walk.mp_payment_id}")
    if walk.payment_status == "pago":
        add("✅ Pagamento confirmado", "payment_confirmed", walk.created_at, "PIX confirmado pelo Asaas.")
    if walk.status in ["aceito", "em_andamento", "finalizado"]:
        add("✅ Passeador aceitou", "walk_accepted", walk.started_at or walk.created_at, "Passeio aceito pelo passeador.")
    add("🚶 Passeio iniciado", "walk_started", walk.started_at, "GPS e acompanhamento liberados.")
    add("🏁 Passeio finalizado", "walk_finished", walk.finished_at, "Atendimento encerrado.")
    if getattr(walk, "payout_status", "") and walk.payout_status not in ["aguardando", "pendente", ""]:
        add("💵 Repasse processado", "payout_updated", walk.finished_at or walk.created_at, f"Status do repasse: {walk.payout_status}")
    return fallback

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

def walk_to_dict(w: WalkRequest, context: str = "admin"):
    now = datetime.utcnow()
    seconds_left = max(0, int((w.expires_at - now).total_seconds())) if w.expires_at else 0
    context = (context or "walker").strip().lower()
    payload = {
        "id": w.id, "client_id": w.client_id, "walker_id": w.walker_id, "pet_id": w.pet_id,
        "client": w.client.full_name if w.client else "", "walker": w.walker.full_name if w.walker else "Aguardando",
        "pet": w.pet.name if w.pet else "", "address": w.address,
        "pickup_lat": w.pickup_lat, "pickup_lng": w.pickup_lng, "walker_lat": w.walker_lat, "walker_lng": w.walker_lng,
        "duration_minutes": w.duration_minutes, "dogs_count": w.dogs_count,
        "estimated_price": w.estimated_price, "distance_km": w.distance_km,
        "status": w.status, "payment_status": w.payment_status,
        "mp_status": w.mp_status,
        "seconds_left": seconds_left,
        "expires_at": w.expires_at.isoformat() if w.expires_at else None,
        "started_at": w.started_at.isoformat() if w.started_at else None,
        "finished_at": w.finished_at.isoformat() if w.finished_at else None,
        "created_at": w.created_at.isoformat(),
    }
    if context in {"client", "admin"}:
        payload.update({
            "pix_code": w.pix_code,
            "mp_status_detail": w.mp_status_detail,
            "mp_qr_code": w.mp_qr_code,
            "mp_qr_code_base64": w.mp_qr_code_base64,
            "mp_ticket_url": w.mp_ticket_url,
        })
    if context == "admin":
        payload.update({
            "mp_payment_id": w.mp_payment_id,
            "payout_status": getattr(w, "payout_status", "") or "aguardando",
            "payout_transfer_id": getattr(w, "payout_transfer_id", "") or "",
            "payout_amount": getattr(w, "payout_amount", 0) or 0,
            "payout_error": getattr(w, "payout_error", "") or "",
            "notes": w.notes,
        })
    return payload


def walk_context_for_user(w: WalkRequest, user: User) -> str:
    if user.role == "admin":
        return "admin"
    if user.id == w.client_id:
        return "client"
    return "walker"

def seed_data():
    if IS_PRODUCTION:
        return

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
                user = User(**data, password_hash=hash_password(DEV_SEED_PASSWORD))
                db.add(user)
            else:
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


seed_data()
seed_pricing_settings()
seed_payout_settings()


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    user_id = read_session_user_id(websocket.cookies.get(SESSION_COOKIE_NAME, ""))
    db = SessionLocal()
    try:
        user = db.get(User, user_id) if user_id else None
        if not user or not user.active:
            await websocket.close(code=1008)
            return
        await manager.connect(websocket, user.id)
    finally:
        db.close()
    try:
        while True:
            raw = await websocket.receive_text()
            try:
                payload = json.loads(raw)
            except Exception:
                payload = {"type": "ping"}
            if isinstance(payload, dict) and payload.get("type") == "typing":
                typing_db = SessionLocal()
                try:
                    walk = typing_db.get(WalkRequest, int(payload.get("request_id") or 0))
                    if walk and user.id in {walk.client_id, walk.walker_id}:
                        await send_walk_event({
                            "type": "typing",
                            "request_id": walk.id,
                            "sender_id": user.id,
                            "sender_role": user.role,
                            "is_typing": bool(payload.get("is_typing", True)),
                        }, typing_db, walk, include_admin=False)
                finally:
                    typing_db.close()
    except WebSocketDisconnect:
        manager.disconnect(websocket)

@app.get("/health")
def health():
    return {"ok": True, "app": "AmigoPet V6 Uber", "version": "6.0.0"}

@app.post("/api/auth/register")
def register(data: RegisterIn, request: Request, db: Session = Depends(get_db)):
    enforce_rate_limit(request, "auth_register_ip", 12, 60 * 60)
    enforce_rate_limit(request, "auth_register_email", 3, 60 * 60, data.email)
    if db.query(User).filter(User.email == data.email).first():
        raise HTTPException(status_code=400, detail="E-mail já cadastrado")
    user = User(**pydantic_dump(data, exclude={"password", "role"}), role="client", password_hash=hash_password(data.password), active=True, email_verified=True, phone_verified=True)
    db.add(user)
    db.commit()
    db.refresh(user)
    response = JSONResponse(user_to_dict(user))
    attach_session_cookie(response, user.id)
    return response

@app.post("/api/auth/register/walker")
def register_walker(data: RegisterIn, request: Request, db: Session = Depends(get_db)):
    enforce_rate_limit(request, "auth_register_walker_ip", 8, 60 * 60)
    enforce_rate_limit(request, "auth_register_walker_email", 3, 60 * 60, data.email)
    if db.query(User).filter(User.email == data.email).first():
        raise HTTPException(status_code=400, detail="E-mail jÃ¡ cadastrado")
    payload = pydantic_dump(data, exclude={"password", "role"})
    required = [
        "full_name", "email", "phone", "photo", "document",
        "pix_key_type", "pix_key", "pix_holder_name", "pix_holder_document",
        "neighborhood", "city",
    ]
    for field in required:
        if not str(payload.get(field, "")).strip():
            raise HTTPException(status_code=400, detail="Preencha todos os dados obrigatÃ³rios do passeador")
    if len(data.password or "") < 6:
        raise HTTPException(status_code=400, detail="A senha deve ter no mÃ­nimo 6 caracteres")
    user = User(**payload, role="walker", password_hash=hash_password(data.password), active=True, email_verified=True, phone_verified=True)
    db.add(user)
    db.commit()
    db.refresh(user)
    response = JSONResponse(user_to_dict(user))
    attach_session_cookie(response, user.id)
    return response

@app.post("/api/auth/login")
def login(data: LoginIn, request: Request, db: Session = Depends(get_db)):
    enforce_rate_limit(request, "auth_login_ip", 40, 15 * 60)
    enforce_rate_limit(request, "auth_login_email", 12, 15 * 60, data.email)
    user = db.query(User).filter(User.email == data.email).first()
    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="E-mail ou senha inválidos")
    if password_needs_rehash(user.password_hash):
        user.password_hash = hash_password(data.password)
        db.commit()
        db.refresh(user)
    response = JSONResponse(user_to_dict(user))
    attach_session_cookie(response, user.id)
    return response



@app.get("/api/auth/google/login")
def google_login(request: Request):
    return google_login_role("client", request)


@app.get("/api/auth/google/login/{role}")
def google_login_role(role: str, request: Request):
    enforce_rate_limit(request, "auth_google_login_ip", 30, 15 * 60)
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
def google_callback(request: Request, code: str = "", error: str = "", state: str = "client", db: Session = Depends(get_db)):
    enforce_rate_limit(request, "auth_google_callback_ip", 60, 15 * 60)
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
        response = RedirectResponse(f"{redirect_base}?google_login=success")
        attach_session_cookie(response, user.id)
        return response
    except Exception as e:
        print("[GOOGLE LOGIN ERROR]", str(e))
        return RedirectResponse(f"{redirect_base}?google_error=server_error")


@app.get("/api/auth/session/current")
def current_session(request: Request, db: Session = Depends(get_db)):
    user = session_user_from_request(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Sessão expirada ou não encontrada")
    response = JSONResponse(user_to_dict(user))
    attach_csrf_cookie(response, user.id)
    return response


@app.post("/api/auth/logout")
def auth_logout(request: Request, db: Session = Depends(get_db)):
    user = session_user_from_request(request, db)
    if user:
        validate_csrf_request(request, user.id)
    response = JSONResponse({"ok": True})
    clear_session_cookie(response)
    return response


@app.post("/api/auth/request-password-reset")
def request_password_reset(data: PasswordResetRequestIn, request: Request, db: Session = Depends(get_db)):
    enforce_rate_limit(request, "password_reset_request_ip", 10, 60 * 60)
    enforce_rate_limit(request, "password_reset_request_email", 3, 60 * 60, data.email)
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
def reset_password(data: PasswordResetConfirmIn, request: Request, db: Session = Depends(get_db)):
    enforce_rate_limit(request, "password_reset_confirm_ip", 20, 60 * 60)
    enforce_rate_limit(request, "password_reset_confirm_email", 6, 60 * 60, data.email)
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
def users(request: Request, role: Optional[str] = None, db: Session = Depends(get_db)):
    session_user = session_user_from_request(request, db)
    q = db.query(User)
    if session_user and session_user.role == "admin":
        if role:
            q = q.filter(User.role == role)
        return [admin_user_list_to_dict(u) for u in q.order_by(User.rating.desc(), User.id.asc()).all()]

    if role not in {None, "walker"}:
        raise HTTPException(status_code=403, detail="A listagem pública está disponível apenas para passeadores")
    q = q.filter(User.role == "walker", User.active.is_(True))
    return [public_walker_to_dict(u) for u in q.order_by(User.rating.desc(), User.id.asc()).all()]

@app.put("/api/users/{user_id}")
def update_user(user_id: int, data: ClientUpdateIn, request: Request, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    enforce_rate_limit(request, "profile_update_user", 30, 15 * 60, current_user.id)
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    if current_user.role != "admin" and current_user.id != user_id:
        raise HTTPException(status_code=403, detail="Acesso negado a este perfil")
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
def accept_client_terms(user_id: int, request: Request, current_user: User = Depends(get_current_client), db: Session = Depends(get_db)):
    enforce_rate_limit(request, "terms_accept_user", 20, 15 * 60, current_user.id)
    if current_user.id != user_id:
        raise HTTPException(status_code=403, detail="Acesso negado a este perfil")
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
def update_walker_profile(user_id: int, data: WalkerUpdateIn, request: Request, current_user: User = Depends(get_current_walker), db: Session = Depends(get_db)):
    enforce_rate_limit(request, "profile_update_user", 30, 15 * 60, current_user.id)
    if current_user.id != user_id:
        raise HTTPException(status_code=403, detail="Acesso negado a este perfil")
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
def accept_walker_terms(user_id: int, request: Request, current_user: User = Depends(get_current_walker), db: Session = Depends(get_db)):
    enforce_rate_limit(request, "terms_accept_user", 20, 15 * 60, current_user.id)
    if current_user.id != user_id:
        raise HTTPException(status_code=403, detail="Acesso negado a este perfil")
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
async def update_walker_availability(user_id: int, data: AvailabilityIn, request: Request, current_user: User = Depends(get_current_walker), db: Session = Depends(get_db)):
    enforce_rate_limit(request, "availability_user", 120, 15 * 60, current_user.id)
    if current_user.id != user_id:
        raise HTTPException(status_code=403, detail="Acesso negado a este perfil")
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Passeador não encontrado")
    if user.role != "walker":
        raise HTTPException(status_code=400, detail="Esta ação é exclusiva para passeadores")

    user.available = bool(data.available)
    db.commit()
    db.refresh(user)

    payload = public_walker_to_dict(user)
    await manager.broadcast_authenticated({
        "type": "walker_availability_changed",
        "walker": payload
    })
    return payload

@app.get("/api/pets")
def pets(owner_id: Optional[int] = None, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    q = db.query(Pet)
    if current_user.role == "admin":
        if owner_id:
            q = q.filter(Pet.owner_id == owner_id)
    elif current_user.role == "client":
        if owner_id and owner_id != current_user.id:
            raise HTTPException(status_code=403, detail="Acesso negado aos pets deste cliente")
        q = q.filter(Pet.owner_id == current_user.id)
    else:
        raise HTTPException(status_code=403, detail="Acesso negado aos pets")
    return [pet_to_dict(p) for p in q.order_by(Pet.id.desc()).all()]

@app.post("/api/pets")
def create_pet(data: PetIn, request: Request, current_user: User = Depends(get_current_client), db: Session = Depends(get_db)):
    enforce_rate_limit(request, "pet_create_user", 30, 60 * 60, current_user.id)
    if data.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Acesso negado a este cliente")
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
def update_pricing(data: PricingIn, request: Request, current_user: User = Depends(get_current_admin), db: Session = Depends(get_db)):
    enforce_rate_limit(request, "sensitive_admin_settings_user", 30, 15 * 60, current_user.id)
    values = pydantic_dump(data)
    for key in DEFAULT_PRICING.keys():
        value = float(values.get(key, DEFAULT_PRICING[key]))
        if value < 0:
            raise HTTPException(status_code=400, detail="Preço não pode ser negativo")
        set_setting(db, key, str(round(value, 2)))
    db.commit()
    return get_pricing_config(db)

@app.get("/api/admin/payout-settings")
def get_payout_settings(current_user: User = Depends(get_current_admin), db: Session = Depends(get_db)):
    return get_payout_config(db)

@app.post("/api/admin/payout-settings")
def update_payout_settings(data: PayoutSettingsIn, request: Request, current_user: User = Depends(get_current_admin), db: Session = Depends(get_db)):
    enforce_rate_limit(request, "sensitive_admin_settings_user", 30, 15 * 60, current_user.id)
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
def walks(status: Optional[str] = None, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    q = db.query(WalkRequest)
    if current_user.role == "client":
        q = q.filter(WalkRequest.client_id == current_user.id)
    elif current_user.role == "walker":
        q = q.filter((WalkRequest.walker_id == current_user.id) | (WalkRequest.walker_id.is_(None)))
    elif current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Acesso negado aos passeios")
    if status:
        q = q.filter(WalkRequest.status == status)
    return [walk_to_dict(w, walk_context_for_user(w, current_user)) for w in q.order_by(WalkRequest.id.desc()).all()]

@app.get("/api/walks/{walk_id}")
def get_walk(walk_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    walk = db.get(WalkRequest, walk_id)
    if not walk:
        raise HTTPException(status_code=404, detail="Solicitação não encontrada")
    if current_user.role != "admin" and current_user.id not in {walk.client_id, walk.walker_id}:
        raise HTTPException(status_code=403, detail="Acesso negado a este passeio")
    return walk_to_dict(walk, walk_context_for_user(walk, current_user))

@app.get("/api/walks/{walk_id}/timeline")
def get_walk_timeline(walk_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    walk = db.get(WalkRequest, walk_id)
    if not walk:
        raise HTTPException(status_code=404, detail="Solicitação não encontrada")
    if current_user.role != "admin" and current_user.id not in {walk.client_id, walk.walker_id}:
        raise HTTPException(status_code=403, detail="Acesso negado a este passeio")
    return build_walk_timeline(db, walk)

@app.post("/api/walks")
async def create_walk(data: WalkIn, request: Request, current_user: User = Depends(get_current_client), db: Session = Depends(get_db)):
    enforce_rate_limit(request, "walk_create_user", 12, 60 * 60, current_user.id)
    if data.client_id != current_user.id:
        raise HTTPException(status_code=403, detail="Acesso negado a este cliente")
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
        add_event_log(db, "📨 Convite criado", "walk_created", walk=walk, user_id=walk.client_id, actor_role="client", details="Cliente criou um novo pedido de passeio.")
        db.commit()

        # Asaas real: cria cobrança PIX e salva QR Code/copia-e-cola no pedido.
        try:
            mp_payment = create_mercadopago_pix_payment(walk)
            apply_mp_payment_to_walk(walk, mp_payment)
            add_event_log(db, "💳 PIX Asaas gerado", "pix_created", walk=walk, user_id=walk.client_id, actor_role="system", details=f"Pagamento Asaas vinculado: {walk.mp_payment_id}")
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
                walk.mp_status_detail = public_asaas_pix_payment_error(mp_error)
                db.commit()
                db.refresh(walk)
            print("[ASAAS PIX ERROR]", {"walk_id": getattr(walk, "id", None), "error": str(mp_error)})
    except Exception as e:
        db.rollback()
        msg = str(e)
        print("[CREATE WALK ERROR]", msg)
        if "NotNullViolation" in msg or "violates not-null constraint" in msg:
            raise HTTPException(
                status_code=500,
                detail="Banco antigo com coluna obrigatória incompatível em walk_requests. Execute `alembic upgrade head` antes de iniciar o backend. Erro técnico: " + msg[:700],
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

    payload = walk_to_dict(walk, "client")
    await send_walk_event({"type": "walk_created", "walk": payload}, db, walk, include_available_walkers=True)
    return payload

@app.post("/api/walks/{walk_id}/accept")
async def accept_walk(walk_id: int, walker_id: int, request: Request, current_user: User = Depends(get_current_walker), db: Session = Depends(get_db)):
    enforce_rate_limit(request, "walk_state_user", 60, 15 * 60, current_user.id)
    walk = db.get(WalkRequest, walk_id)
    if not walk:
        raise HTTPException(status_code=404, detail="Solicitação não encontrada")
    if walker_id != current_user.id or walk.walker_id not in {None, current_user.id}:
        raise HTTPException(status_code=403, detail="Ação exclusiva do passeador autorizado")
    if walk.status in ["finalizado", "cancelado"]:
        raise HTTPException(status_code=400, detail="Pedido já encerrado")
    if walk.payment_status != "pago":
        raise HTTPException(status_code=402, detail="Aguardando pagamento PIX confirmado pelo Asaas antes do aceite")
    walk.walker_id = walker_id
    walk.status = "aceito"
    walk.expires_at = None
    add_event_log(db, "✅ Passeador aceitou", "walk_accepted", walk=walk, user_id=walker_id, actor_role="walker", details="Passeio aceito pelo passeador.")
    db.commit()
    db.refresh(walk)
    payload = walk_to_dict(walk, "walker")
    await send_walk_event({"type": "walk_accepted", "walk": payload}, db, walk)
    return payload

@app.post("/api/walks/{walk_id}/reject")
async def reject_walk(walk_id: int, request: Request, current_user: User = Depends(get_current_walker), db: Session = Depends(get_db)):
    enforce_rate_limit(request, "walk_state_user", 60, 15 * 60, current_user.id)
    walk = db.get(WalkRequest, walk_id)
    if not walk:
        raise HTTPException(status_code=404, detail="Solicitação não encontrada")
    if walk.walker_id != current_user.id:
        raise HTTPException(status_code=403, detail="Ação exclusiva do passeador vinculado ao passeio")
    walk.status = "recusado"
    add_event_log(db, "❌ Pedido recusado", "walk_rejected", walk=walk, user_id=walk.walker_id, actor_role="walker", details="Pedido recusado pelo passeador.")
    db.commit()
    payload = walk_to_dict(walk, "walker")
    await send_walk_event({"type": "walk_rejected", "walk": payload}, db, walk)
    return payload

@app.post("/api/walks/{walk_id}/pay")
async def pay_walk(walk_id: int, request: Request, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Compatível com o botão antigo: se houver Mercado Pago, verifica no gateway; se não houver, confirma manualmente."""
    enforce_rate_limit(request, "payment_user", 30, 15 * 60, current_user.id)
    walk = db.get(WalkRequest, walk_id)
    if not walk:
        raise HTTPException(status_code=404, detail="Solicitação não encontrada")
    if current_user.role != "admin" and current_user.id != walk.client_id:
        raise HTTPException(status_code=403, detail="Pagamento exclusivo do cliente deste passeio")

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
        add_event_log(db, "✅ Pagamento confirmado", "payment_confirmed", walk=walk, user_id=walk.client_id, actor_role="system", details="Pagamento confirmado pelo Asaas.")

    db.commit()
    db.refresh(walk)
    payload = walk_to_dict(walk, walk_context_for_user(walk, current_user))
    if changed or walk.payment_status == "pago":
        await send_walk_event({"type": "payment_confirmed", "walk": payload}, db, walk)
        for msg in messages:
            if msg:
                await send_walk_event({"type": "message", "message": message_to_dict(msg)}, db, walk, include_admin=False)
    return payload

@app.post("/api/asaas/webhook")
@app.post("/api/payments/asaas/webhook")
@app.post("/api/payments/webhook")
async def asaas_webhook(request: Request, db: Session = Depends(get_db)):
    """Webhook real do Asaas. Confirma automaticamente o pedido quando o PIX é pago."""
    enforce_rate_limit(request, "payment_webhook_ip", 120, 60)
    if not validate_mp_webhook_signature(request):
        raise HTTPException(status_code=401, detail="Token do webhook Asaas inválido")

    try:
        body = await request.json()
    except Exception:
        body = {}
    if not isinstance(body, dict):
        body = {}

    topic = body.get("event") or body.get("type") or body.get("topic") or request.query_params.get("topic") or request.query_params.get("type")
    if topic and not str(topic).startswith("PAYMENT_"):
        return {"ok": True, "ignored": True, "topic": topic}

    payment_obj = body.get("payment") if isinstance(body, dict) else None
    if not isinstance(payment_obj, dict):
        payment_obj = {}

    payment_id = payment_obj.get("id") or body.get("id") or request.query_params.get("id") or request.query_params.get("data.id")
    if not payment_id:
        raise HTTPException(status_code=400, detail="payment_id ausente")
    payment_id = _asaas_str(payment_id)

    try:
        mp_payment = get_mercadopago_payment(str(payment_id))
    except Exception as e:
        print("[ASAAS WEBHOOK VALIDATION ERROR]", {"payment_id": payment_id, "error": type(e).__name__})
        raise HTTPException(status_code=502, detail="Não foi possível validar pagamento no Asaas")

    if topic:
        mp_payment["event"] = str(topic)

    external_reference = _asaas_external_reference(mp_payment)
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

    validate_asaas_payment_for_walk(walk, mp_payment, payment_id, payment_obj)
    was_paid = walk.payment_status == "pago"
    changed = apply_mp_payment_to_walk(walk, mp_payment)
    messages = []
    if changed and walk.payment_status == "pago" and not was_paid:
        messages.append(add_walk_system_message(db, walk, "✅ Pagamento confirmado com sucesso. O pedido foi liberado para o passeador aceitar."))
        add_event_log(db, "✅ Pagamento confirmado", "payment_confirmed", walk=walk, user_id=walk.client_id, actor_role="system", details="Pagamento confirmado pelo Asaas/webhook.")

    db.commit()
    db.refresh(walk)
    payload = walk_to_dict(walk, "admin")
    if changed and walk.payment_status == "pago":
        await send_walk_event({"type": "payment_confirmed", "walk": payload}, db, walk)
        for msg in messages:
            if msg:
                await send_walk_event({"type": "message", "message": message_to_dict(msg)}, db, walk, include_admin=False)
    elif changed:
        await send_walk_event({"type": "payment_updated", "walk": payload}, db, walk)
    return {"ok": True, "walk_id": walk.id, "payment_status": walk.payment_status, "mp_status": walk.mp_status, "idempotent": not changed}

@app.post("/api/payments/asaas/sync/{walk_id}")
@app.post("/api/payments/mercadopago/sync/{walk_id}")
async def sync_asaas_payment(walk_id: int, request: Request, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    enforce_rate_limit(request, "payment_sync_user", 30, 15 * 60, current_user.id)
    walk = db.get(WalkRequest, walk_id)
    if not walk:
        raise HTTPException(status_code=404, detail="Solicitação não encontrada")
    if current_user.role != "admin" and current_user.id not in {walk.client_id, walk.walker_id}:
        raise HTTPException(status_code=403, detail="Acesso restrito aos participantes do passeio")
    if not walk.mp_payment_id:
        raise HTTPException(status_code=400, detail="Este pedido ainda não tem pagamento Asaas vinculado")
    mp_payment = get_mercadopago_payment(walk.mp_payment_id)
    changed = apply_mp_payment_to_walk(walk, mp_payment)
    messages = []
    if changed or walk.payment_status == "pago":
        messages.append(add_walk_system_message(db, walk, "✅ Pagamento confirmado com sucesso. O pedido foi liberado para o passeador aceitar."))
        add_event_log(db, "✅ Pagamento confirmado", "payment_confirmed", walk=walk, user_id=walk.client_id, actor_role="system", details="Pagamento confirmado pelo Asaas/webhook.")

    db.commit()
    db.refresh(walk)
    payload = walk_to_dict(walk, walk_context_for_user(walk, current_user))
    if changed or walk.payment_status == "pago":
        await send_walk_event({"type": "payment_confirmed", "walk": payload}, db, walk)
        for msg in messages:
            if msg:
                await send_walk_event({"type": "message", "message": message_to_dict(msg)}, db, walk, include_admin=False)
    return payload

@app.post("/api/walks/{walk_id}/start")
async def start_walk(walk_id: int, request: Request, current_user: User = Depends(get_current_walker), db: Session = Depends(get_db)):
    enforce_rate_limit(request, "walk_state_user", 60, 15 * 60, current_user.id)
    walk = db.get(WalkRequest, walk_id)
    if not walk:
        raise HTTPException(status_code=404, detail="Solicitação não encontrada")
    if walk.walker_id != current_user.id:
        raise HTTPException(status_code=403, detail="Ação exclusiva do passeador vinculado ao passeio")
    if walk.payment_status != "pago":
        raise HTTPException(status_code=402, detail="Pagamento PIX ainda não confirmado pelo Asaas")
    walk.status = "em_andamento"
    walk.started_at = datetime.utcnow()
    add_event_log(db, "🚶 Passeio iniciado", "walk_started", walk=walk, user_id=walk.walker_id, actor_role="walker", details="Passeador iniciou o passeio.")
    db.commit()
    payload = walk_to_dict(walk, "walker")
    await send_walk_event({"type": "walk_started", "walk": payload}, db, walk)
    return payload

@app.post("/api/walks/{walk_id}/finish")
async def finish_walk(walk_id: int, request: Request, current_user: User = Depends(get_current_walker), db: Session = Depends(get_db)):
    enforce_rate_limit(request, "walk_state_user", 60, 15 * 60, current_user.id)
    walk = db.get(WalkRequest, walk_id)
    if not walk:
        raise HTTPException(status_code=404, detail="Solicitação não encontrada")
    if walk.walker_id != current_user.id:
        raise HTTPException(status_code=403, detail="Ação exclusiva do passeador vinculado ao passeio")
    if walk.payment_status != "pago":
        raise HTTPException(status_code=402, detail="Pagamento PIX ainda não confirmado pelo Asaas")
    if walk.status == "finalizado":
        return walk_to_dict(walk, "walker")

    walk.status = "finalizado"
    walk.finished_at = datetime.utcnow()
    add_event_log(db, "🏁 Passeio finalizado", "walk_finished", walk=walk, user_id=walk.walker_id, actor_role="walker", details="Passeio finalizado pelo passeador.")
    messages = [add_walk_system_message(db, walk, "🐶 Passeio finalizado com sucesso. Obrigado por utilizar o AmigoPet.")]

    if not walk.walker_id or not walk.walker:
        walk.payout_status = "pendente"
        walk.payout_error = "Passeador não vinculado ao passeio"
        messages.append(add_walk_system_message(db, walk, "⚠️ Passeio finalizado, mas o repasse ao passeador ficou pendente porque o passeador não foi identificado."))
    elif getattr(walk, "payout_transfer_id", ""):
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
            add_event_log(db, "💵 Repasse solicitado", "payout_requested", walk=walk, user_id=walk.walker_id, actor_role="system", details=f"Valor solicitado: R$ {amount:.2f}")
        except Exception as e:
            payout_message = public_payout_error(e)
            walk.payout_status = "erro"
            walk.payout_error = payout_message
            messages.append(add_walk_system_message(db, walk, "⚠️ Passeio finalizado. O repasse automático ao passeador ficou pendente e precisa ser verificado pela administração."))
            add_event_log(db, "⚠️ Falha no repasse", "payout_error", walk=walk, user_id=walk.walker_id, actor_role="system", details=payout_message)
            print("[ASAAS PAYOUT ERROR]", {
                "walk_id": walk.id,
                "error": str(e),
                "raw_response": getattr(e, "raw_response", None),
            })

    db.commit()
    db.refresh(walk)
    payload = walk_to_dict(walk, "walker")
    await send_walk_event({"type": "walk_finished", "walk": payload}, db, walk)
    for msg in messages:
        if msg:
            await send_walk_event({"type": "message", "message": message_to_dict(msg)}, db, walk, include_admin=False)
    return payload

@app.post("/api/walks/{walk_id}/location")
async def update_location(walk_id: int, data: LocationIn, request: Request, current_user: User = Depends(get_current_walker), db: Session = Depends(get_db)):
    enforce_rate_limit(request, "walk_location_user", 180, 15 * 60, current_user.id)
    walk = db.get(WalkRequest, walk_id)
    if not walk:
        raise HTTPException(status_code=404, detail="Solicitação não encontrada")
    if walk.walker_id != current_user.id:
        raise HTTPException(status_code=403, detail="Ação exclusiva do passeador vinculado ao passeio")
    walk.walker_lat = data.lat
    walk.walker_lng = data.lng
    try:
        exists = db.query(EventLog).filter(EventLog.walk_id == walk.id, EventLog.event_type == "location_updated").first()
        if not exists:
            add_event_log(db, "📍 Localização atualizada", "location_updated", walk=walk, user_id=walk.walker_id, actor_role="walker", details="Primeira atualização de GPS registrada no passeio.")
    except Exception as e:
        print("[EVENT LOG WARNING] location_updated", str(e))
    db.commit()
    payload = walk_to_dict(walk, "walker")
    await send_walk_event({"type": "location_updated", "walk": payload}, db, walk)
    return payload

@app.post("/api/walks/{walk_id}/ratings")
async def rate_walk_user(walk_id: int, data: RatingIn, request: Request, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    enforce_rate_limit(request, "rating_user", 20, 60 * 60, current_user.id)
    walk = db.get(WalkRequest, walk_id)
    if not walk:
        raise HTTPException(status_code=404, detail="Passeio não encontrado")
    if walk.status != "finalizado":
        raise HTTPException(status_code=400, detail="A avaliação só pode ser feita após o passeio ser finalizado")
    if current_user.id not in {walk.client_id, walk.walker_id} or data.rater_id != current_user.id:
        raise HTTPException(status_code=403, detail="Acesso negado a esta avaliação")

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
    add_event_log(
        db,
        "⭐ Avaliação enviada",
        "rating_created",
        walk=walk,
        user_id=rater.id,
        actor_role=rater.role,
        details=f"{rater.full_name} avaliou {target.full_name} com {int(data.rating)} estrela(s)."
    )

    db.commit()
    db.refresh(item)
    payload = rating_to_dict(item)
    await send_walk_event({"type": "rating_created", "rating": payload}, db, walk)
    return payload

@app.get("/api/walks/{walk_id}/ratings")
def list_walk_ratings(walk_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    walk = db.get(WalkRequest, walk_id)
    if not walk:
        raise HTTPException(status_code=404, detail="Passeio não encontrado")
    if current_user.role != "admin" and current_user.id not in {walk.client_id, walk.walker_id}:
        raise HTTPException(status_code=403, detail="Acesso negado a este passeio")
    items = db.query(UserRating).filter(UserRating.walk_id == walk_id).order_by(UserRating.id.desc()).all()
    return [rating_to_dict(item) for item in items]

@app.get("/api/notifications/{user_id}")
def list_user_notifications(user_id: int, unread_only: bool = False, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if current_user.role != "admin" and current_user.id != user_id:
        raise HTTPException(status_code=403, detail="Acesso negado a estas notificações")
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    q = db.query(UserNotification).filter(UserNotification.user_id == user_id)
    if unread_only:
        q = q.filter(UserNotification.is_read == False)
    items = q.order_by(UserNotification.id.desc()).limit(50).all()
    return [notification_to_dict(item) for item in items]

@app.post("/api/notifications/{notification_id}/read")
def mark_notification_read(notification_id: int, request: Request, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    enforce_rate_limit(request, "notification_mutation_user", 120, 15 * 60, current_user.id)
    item = db.get(UserNotification, notification_id)
    if not item:
        raise HTTPException(status_code=404, detail="Notificação não encontrada")
    if current_user.role != "admin" and current_user.id != item.user_id:
        raise HTTPException(status_code=403, detail="Acesso negado a esta notificação")
    item.is_read = True
    db.commit()
    db.refresh(item)
    return notification_to_dict(item)

@app.post("/api/notifications/read-all/{user_id}")
def mark_all_notifications_read(user_id: int, request: Request, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    enforce_rate_limit(request, "notification_mutation_user", 120, 15 * 60, current_user.id)
    if current_user.role != "admin" and current_user.id != user_id:
        raise HTTPException(status_code=403, detail="Acesso negado a estas notificações")
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    db.query(UserNotification).filter(UserNotification.user_id == user_id, UserNotification.is_read == False).update({"is_read": True})
    db.commit()
    return {"ok": True}



@app.get("/api/wallet/{walker_id}")
def get_walker_wallet(walker_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if current_user.role != "admin" and current_user.id != walker_id:
        raise HTTPException(status_code=403, detail="Acesso negado a esta carteira")
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
def get_walker_wallet_history(walker_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if current_user.role != "admin" and current_user.id != walker_id:
        raise HTTPException(status_code=403, detail="Acesso negado a esta carteira")
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
            "payout_error": sanitize_public_payout_error_text(getattr(walk, "payout_error", "") or ""),
            "finished_at": walk.finished_at.isoformat() if walk.finished_at else None,
            "created_at": walk.created_at.isoformat() if walk.created_at else None,
        })
    return items

@app.post("/api/messages")
async def create_message(data: MessageIn, request: Request, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    enforce_rate_limit(request, "message_create_user", 120, 15 * 60, current_user.id)
    walk = db.get(WalkRequest, data.request_id)
    if not walk:
        raise HTTPException(status_code=404, detail="Passeio não encontrado para o chat")
    if data.sender_id != current_user.id or current_user.id not in {walk.client_id, walk.walker_id}:
        raise HTTPException(status_code=403, detail="Você não participa deste chat")

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
    add_event_log(db, "💬 Mensagem enviada", "message_sent", walk=walk, user_id=sender.id, actor_role=sender.role, details=clean_text[:180])

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
    await send_walk_event({"type": "message", "message": payload, "request_id": msg.request_id}, db, walk, include_admin=False)
    return payload

@app.get("/api/messages/{request_id}")
def list_messages(request_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    walk = db.get(WalkRequest, request_id)
    if not walk:
        raise HTTPException(status_code=404, detail="Passeio não encontrado")
    if current_user.id not in {walk.client_id, walk.walker_id}:
        raise HTTPException(status_code=403, detail="Você não participa deste chat")
    msgs = db.query(Message).filter(Message.request_id == request_id).order_by(Message.id.asc()).all()
    return [message_to_dict(m) for m in msgs]

@app.post("/api/messages/{request_id}/read/{user_id}")
async def mark_messages_read(request_id: int, user_id: int, request: Request, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    enforce_rate_limit(request, "message_read_user", 120, 15 * 60, current_user.id)
    walk = db.get(WalkRequest, request_id)
    if not walk:
        raise HTTPException(status_code=404, detail="Passeio não encontrado")
    if current_user.id != user_id:
        raise HTTPException(status_code=403, detail="Acesso negado a este chat")
    if user_id not in [walk.client_id, walk.walker_id]:
        raise HTTPException(status_code=403, detail="Usuário não participa deste chat")
    now = datetime.utcnow()
    db.query(Message).filter(
        Message.request_id == request_id,
        Message.sender_id != user_id,
        Message.read_at == None,
    ).update({"read_at": now}, synchronize_session=False)
    db.commit()
    walk = db.get(WalkRequest, request_id)
    if walk:
        await send_walk_event({"type": "messages_read", "request_id": request_id, "reader_id": user_id}, db, walk, include_admin=False)
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
