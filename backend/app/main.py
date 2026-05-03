from __future__ import annotations

import hashlib
import os
import secrets
import smtplib
from datetime import datetime, timedelta
from email.message import EmailMessage
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text, create_engine, text
from sqlalchemy.orm import Session, declarative_base, relationship, sessionmaker

# ============================================================
# CONFIGURAÇÃO BASE
# ============================================================

THIS_FILE = Path(__file__).resolve()
BACKEND_DIR = THIS_FILE.parents[1]      # backend/app -> backend
REPO_DIR = BACKEND_DIR.parent           # repo root

# Funciona tanto com Root Directory = backend quanto com raiz do repo.
FRONTEND_DIR = BACKEND_DIR / "frontend"
if not FRONTEND_DIR.exists():
    FRONTEND_DIR = REPO_DIR / "frontend"

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./amigopet_v8.db")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
Base = declarative_base()

APP_NAME = os.getenv("APP_NAME", "AmigoPet Pro")
APP_BRAND = os.getenv("APP_BRAND", "ROVIX")
EMAIL_CONFIRMATION_REQUIRED = os.getenv("EMAIL_CONFIRMATION_REQUIRED", "true").lower() in {"1", "true", "yes", "sim"}
VERIFICATION_CODE_MINUTES = int(os.getenv("VERIFICATION_CODE_MINUTES", "15"))

SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM = os.getenv("SMTP_FROM", SMTP_USER or "no-reply@amigopet.local")
SMTP_USE_TLS = os.getenv("SMTP_USE_TLS", "true").lower() in {"1", "true", "yes", "sim"}

app = FastAPI(title="AmigoPet Pro Cliente", version="8.5.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", os.getenv("BACKEND_CORS_ORIGINS", "*")).split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================
# MODELOS
# ============================================================

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

    zip_code = Column(String(20), default="")
    street = Column(String(160), default="")
    number = Column(String(30), default="")
    complement = Column(String(120), default="")
    address = Column(Text, default="")
    neighborhood = Column(String(120), default="")
    city = Column(String(120), default="")
    state = Column(String(60), default="RJ")

    lat = Column(Float, default=-22.5884)
    lng = Column(Float, default=-43.1847)
    rating = Column(Float, default=5.0)
    available = Column(Boolean, default=True)
    bio = Column(Text, default="")

    email_verified = Column(Boolean, default=False)
    phone_verified = Column(Boolean, default=False)
    verification_code_hash = Column(String(255), default="")
    verification_expires_at = Column(DateTime, nullable=True)
    verified_at = Column(DateTime, nullable=True)
    active = Column(Boolean, default=True)

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


# ============================================================
# SCHEMAS
# ============================================================

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


class ClientRegisterIn(BaseModel):
    full_name: str = Field(min_length=3, max_length=120)
    email: EmailStr
    password: str = Field(min_length=6, max_length=80)
    phone: str = Field(min_length=8, max_length=30)
    photo: str = Field(min_length=20)
    document: str = ""
    zip_code: str = ""
    street: str = Field(min_length=2, max_length=160)
    number: str = Field(min_length=1, max_length=30)
    complement: str = ""
    neighborhood: str = Field(min_length=2, max_length=120)
    city: str = Field(min_length=2, max_length=120)
    state: str = "RJ"
    bio: str = ""


class VerifyCodeIn(BaseModel):
    email: EmailStr
    code: str = Field(min_length=4, max_length=10)


class ResendCodeIn(BaseModel):
    email: EmailStr


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class PetIn(BaseModel):
    owner_id: int
    name: str = Field(min_length=1)
    species: str = "Cachorro"
    breed: str = ""
    size: str = "Médio"
    age: str = ""
    photo: str = Field(min_length=10)
    notes: str = ""


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


# ============================================================
# WEBSOCKET
# ============================================================

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


# ============================================================
# BANCO / UTILITÁRIOS
# ============================================================

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def hash_password(password: str) -> str:
    # Hash próprio estável, evita problemas do bcrypt/passlib no Python 3.14.
    salt = secrets.token_hex(16)
    digest = hashlib.sha256(f"{salt}:{password}".encode("utf-8")).hexdigest()
    return f"sha256${salt}${digest}"


def verify_password(password: str, stored_hash: str) -> bool:
    if not stored_hash:
        return False
    if stored_hash.startswith("sha256$"):
        try:
            _, salt, digest = stored_hash.split("$", 2)
            candidate = hashlib.sha256(f"{salt}:{password}".encode("utf-8")).hexdigest()
            return secrets.compare_digest(candidate, digest)
        except Exception:
            return False
    # Compatibilidade emergencial: usuários antigos podem redefinir senha cadastrando novamente em outro e-mail.
    return False


def hash_code(code: str) -> str:
    secret = os.getenv("SECRET_KEY", "amigopet-local-secret")
    return hashlib.sha256(f"{secret}:{code}".encode("utf-8")).hexdigest()


def generate_code() -> str:
    return f"{secrets.randbelow(900000) + 100000}"


def full_address(data: ClientRegisterIn) -> str:
    parts = [
        data.street.strip(),
        data.number.strip(),
        data.complement.strip(),
        data.neighborhood.strip(),
        data.city.strip(),
        data.state.strip(),
        data.zip_code.strip(),
    ]
    return ", ".join([p for p in parts if p])


def user_to_dict(u: User):
    return {
        "id": u.id,
        "full_name": u.full_name,
        "email": u.email,
        "role": u.role,
        "phone": u.phone,
        "photo": u.photo,
        "profile_photo": u.photo,
        "document": u.document,
        "zip_code": u.zip_code,
        "street": u.street,
        "number": u.number,
        "complement": u.complement,
        "address": u.address,
        "neighborhood": u.neighborhood,
        "city": u.city,
        "state": u.state,
        "lat": u.lat,
        "lng": u.lng,
        "rating": u.rating,
        "available": u.available,
        "bio": u.bio,
        "email_verified": bool(u.email_verified),
        "phone_verified": bool(u.phone_verified),
        "active": bool(u.active),
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
    }


def make_pix_code(walk_id: int, amount: float) -> str:
    token = secrets.token_hex(8).upper()
    return f"000201-AMIGOPET-PIX-SIMULADO-ID{walk_id}-VALOR{amount:.2f}-TOKEN{token}"


def walk_to_dict(w: WalkRequest):
    now = datetime.utcnow()
    seconds_left = max(0, int((w.expires_at - now).total_seconds())) if w.expires_at else 0
    return {
        "id": w.id,
        "client_id": w.client_id,
        "walker_id": w.walker_id,
        "pet_id": w.pet_id,
        "client": w.client.full_name if w.client else "",
        "walker": w.walker.full_name if w.walker else "Aguardando",
        "pet": w.pet.name if w.pet else "",
        "address": w.address,
        "pickup_lat": w.pickup_lat,
        "pickup_lng": w.pickup_lng,
        "walker_lat": w.walker_lat,
        "walker_lng": w.walker_lng,
        "duration_minutes": w.duration_minutes,
        "dogs_count": w.dogs_count,
        "estimated_price": w.estimated_price,
        "distance_km": w.distance_km,
        "status": w.status,
        "payment_status": w.payment_status,
        "pix_code": w.pix_code,
        "notes": w.notes,
        "seconds_left": seconds_left,
        "expires_at": w.expires_at.isoformat() if w.expires_at else None,
        "started_at": w.started_at.isoformat() if w.started_at else None,
        "finished_at": w.finished_at.isoformat() if w.finished_at else None,
        "created_at": w.created_at.isoformat(),
    }


def send_verification_email(to_email: str, full_name: str, code: str) -> dict:
    subject = f"{APP_NAME} - código de confirmação"
    body = f"""Olá, {full_name}!

Seu código de confirmação do {APP_NAME} é:

{code}

Esse código expira em {VERIFICATION_CODE_MINUTES} minutos.

Equipe {APP_BRAND}
"""

    if not SMTP_HOST or not SMTP_USER or not SMTP_PASSWORD:
        # Não trava o app em ambiente sem SMTP. No Render, configure SMTP_* para envio real.
        print(f"[DEV EMAIL] Código para {to_email}: {code}")
        return {"sent": False, "dev_code": code, "reason": "SMTP não configurado"}

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = SMTP_FROM
    msg["To"] = to_email
    msg.set_content(body)

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20) as smtp:
            if SMTP_USE_TLS:
                smtp.starttls()
            smtp.login(SMTP_USER, SMTP_PASSWORD)
            smtp.send_message(msg)
        return {"sent": True}
    except Exception as exc:
        print(f"[EMAIL ERROR] {exc}")
        raise HTTPException(status_code=500, detail="Não foi possível enviar o e-mail de confirmação. Verifique as variáveis SMTP no Render.")


def add_column_if_missing(conn, table: str, column: str, ddl: str):
    dialect = engine.dialect.name
    try:
        if dialect == "postgresql":
            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {ddl}"))
        else:
            # SQLite não suporta IF NOT EXISTS em ADD COLUMN em várias versões.
            existing = [row[1] for row in conn.execute(text(f"PRAGMA table_info({table})")).fetchall()]
            if column not in existing:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"))
    except Exception as exc:
        print(f"[MIGRATION WARNING] {table}.{column}: {exc}")


def run_lightweight_migrations():
    Base.metadata.create_all(bind=engine)
    with engine.begin() as conn:
        user_columns = {
            "password_hash": "VARCHAR(255)",
            "photo": "TEXT",
            "document": "VARCHAR(40)",
            "zip_code": "VARCHAR(20)",
            "street": "VARCHAR(160)",
            "number": "VARCHAR(30)",
            "complement": "VARCHAR(120)",
            "address": "TEXT",
            "neighborhood": "VARCHAR(120)",
            "city": "VARCHAR(120)",
            "state": "VARCHAR(60)",
            "lat": "FLOAT",
            "lng": "FLOAT",
            "rating": "FLOAT",
            "available": "BOOLEAN DEFAULT TRUE",
            "bio": "TEXT",
            "email_verified": "BOOLEAN DEFAULT FALSE",
            "phone_verified": "BOOLEAN DEFAULT FALSE",
            "verification_code_hash": "VARCHAR(255)",
            "verification_expires_at": "TIMESTAMP NULL",
            "verified_at": "TIMESTAMP NULL",
            "active": "BOOLEAN DEFAULT TRUE",
        }
        for col, ddl in user_columns.items():
            add_column_if_missing(conn, "users", col, ddl)

        pet_columns = {
            "photo": "TEXT",
            "species": "VARCHAR(60)",
            "breed": "VARCHAR(100)",
            "size": "VARCHAR(50)",
            "age": "VARCHAR(50)",
            "notes": "TEXT",
        }
        for col, ddl in pet_columns.items():
            add_column_if_missing(conn, "pets", col, ddl)


def ensure_seed_data():
    db = SessionLocal()
    try:
        # Garante usuários de teste funcionando com hash estável.
        seed_users = [
            {
                "full_name": "Administrador AmigoPet",
                "email": "admin@amigopet.com",
                "role": "admin",
                "phone": "(21) 90000-0000",
                "city": "Magé",
                "neighborhood": "Piabetá",
                "photo": "https://api.dicebear.com/8.x/initials/svg?seed=Admin",
                "bio": "Gestão operacional da plataforma.",
            },
            {
                "full_name": "Cliente Teste",
                "email": "cliente@amigopet.com",
                "role": "client",
                "phone": "(21) 98888-1111",
                "address": "Rua Mirabel, 49 Piabetá - Magé - RJ",
                "street": "Rua Mirabel",
                "number": "49",
                "neighborhood": "Piabetá",
                "city": "Magé",
                "state": "RJ",
                "photo": "https://api.dicebear.com/8.x/initials/svg?seed=Cliente",
            },
            {
                "full_name": "Passeador Profissional",
                "email": "passeador@amigopet.com",
                "role": "walker",
                "phone": "(21) 99999-0000",
                "neighborhood": "Piabetá",
                "city": "Magé",
                "lat": -22.5900,
                "lng": -43.1810,
                "rating": 4.9,
                "available": True,
                "photo": "https://api.dicebear.com/8.x/initials/svg?seed=Passeador",
                "bio": "Passeador verificado, experiência com cães pequenos e grandes.",
            },
            {
                "full_name": "Ana Walker Premium",
                "email": "ana@amigopet.com",
                "role": "walker",
                "phone": "(21) 97777-2222",
                "neighborhood": "Centro",
                "city": "Magé",
                "lat": -22.5852,
                "lng": -43.1881,
                "rating": 4.8,
                "available": True,
                "photo": "https://api.dicebear.com/8.x/initials/svg?seed=Ana",
                "bio": "Rotas seguras, envio de fotos e cuidado especial.",
            },
        ]

        for data in seed_users:
            user = db.query(User).filter(User.email == data["email"]).first()
            if not user:
                user = User(
                    **data,
                    password_hash=hash_password("123456"),
                    email_verified=True,
                    phone_verified=True,
                    active=True,
                    verified_at=datetime.utcnow(),
                )
                db.add(user)
            else:
                # Atualiza usuários de teste para garantir login funcionando.
                user.password_hash = hash_password("123456")
                user.email_verified = True
                user.phone_verified = True
                user.active = True
                for key, value in data.items():
                    if hasattr(user, key) and (getattr(user, key) in [None, ""] or key in {"photo", "bio"}):
                        setattr(user, key, value)
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
            )
            db.add(pet)
            db.commit()
    finally:
        db.close()


run_lightweight_migrations()
ensure_seed_data()


# ============================================================
# ROTAS WEBSOCKET / SAÚDE
# ============================================================

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
    return {
        "ok": True,
        "app": "AmigoPet Pro Cliente",
        "version": "8.5.0",
        "frontend_dir": str(FRONTEND_DIR),
        "smtp_configured": bool(SMTP_HOST and SMTP_USER and SMTP_PASSWORD),
    }


# ============================================================
# AUTENTICAÇÃO PROFISSIONAL
# ============================================================

@app.post("/api/auth/register")
def register(data: RegisterIn, db: Session = Depends(get_db)):
    # Compatibilidade com app antigo.
    if db.query(User).filter(User.email == data.email).first():
        raise HTTPException(status_code=400, detail="E-mail já cadastrado")
    user = User(
        **data.model_dump(exclude={"password"}),
        password_hash=hash_password(data.password),
        email_verified=not EMAIL_CONFIRMATION_REQUIRED,
        phone_verified=not EMAIL_CONFIRMATION_REQUIRED,
        active=True,
        verified_at=datetime.utcnow() if not EMAIL_CONFIRMATION_REQUIRED else None,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user_to_dict(user)


@app.post("/api/auth/register-client")
def register_client(data: ClientRegisterIn, db: Session = Depends(get_db)):
    email = str(data.email).lower().strip()
    existing = db.query(User).filter(User.email == email).first()
    if existing:
        raise HTTPException(status_code=400, detail="E-mail já cadastrado. Use login ou peça novo código.")

    code = generate_code()
    user = User(
        full_name=data.full_name.strip(),
        email=email,
        password_hash=hash_password(data.password),
        role="client",
        phone=data.phone.strip(),
        photo=data.photo.strip(),
        document=data.document.strip(),
        zip_code=data.zip_code.strip(),
        street=data.street.strip(),
        number=data.number.strip(),
        complement=data.complement.strip(),
        neighborhood=data.neighborhood.strip(),
        city=data.city.strip(),
        state=data.state.strip(),
        address=full_address(data),
        bio=data.bio.strip(),
        email_verified=not EMAIL_CONFIRMATION_REQUIRED,
        phone_verified=not EMAIL_CONFIRMATION_REQUIRED,
        verification_code_hash=hash_code(code) if EMAIL_CONFIRMATION_REQUIRED else "",
        verification_expires_at=datetime.utcnow() + timedelta(minutes=VERIFICATION_CODE_MINUTES) if EMAIL_CONFIRMATION_REQUIRED else None,
        verified_at=datetime.utcnow() if not EMAIL_CONFIRMATION_REQUIRED else None,
        active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    email_result = {"sent": False}
    if EMAIL_CONFIRMATION_REQUIRED:
        try:
    email_result = send_verification_email(user.email, user.full_name, code)
except Exception as e:
    print("[EMAIL FAIL]", e)
    email_result = {"sent": False, "dev_code": code}

    response = {
        "ok": True,
        "message": "Cadastro criado. Confirme o código enviado por e-mail.",
        "email": user.email,
        "email_sent": email_result.get("sent", False),
    }
    if email_result.get("dev_code"):
        response["dev_code"] = email_result["dev_code"]
        response["message"] = "SMTP não configurado. Use o código exibido para teste."
    return response


@app.post("/api/auth/verify-code")
def verify_code(data: VerifyCodeIn, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == str(data.email).lower().strip()).first()
    if not user:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    if user.email_verified and user.phone_verified:
        return user_to_dict(user)
    if not user.verification_code_hash or not user.verification_expires_at:
        raise HTTPException(status_code=400, detail="Código não solicitado")
    if user.verification_expires_at < datetime.utcnow():
        raise HTTPException(status_code=400, detail="Código expirado. Solicite um novo código.")
    if not secrets.compare_digest(user.verification_code_hash, hash_code(data.code.strip())):
        raise HTTPException(status_code=400, detail="Código inválido")

    user.email_verified = True
    user.phone_verified = True
    user.verified_at = datetime.utcnow()
    user.verification_code_hash = ""
    user.verification_expires_at = None
    db.commit()
    db.refresh(user)
    return user_to_dict(user)


@app.post("/api/auth/resend-code")
def resend_code(data: ResendCodeIn, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == str(data.email).lower().strip()).first()
    if not user:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    if user.email_verified and user.phone_verified:
        return {"ok": True, "message": "Conta já confirmada"}

    code = generate_code()
    user.verification_code_hash = hash_code(code)
    user.verification_expires_at = datetime.utcnow() + timedelta(minutes=VERIFICATION_CODE_MINUTES)
    db.commit()

    email_result = send_verification_email(user.email, user.full_name, code)
    response = {"ok": True, "message": "Novo código enviado", "email_sent": email_result.get("sent", False)}
    if email_result.get("dev_code"):
        response["dev_code"] = email_result["dev_code"]
    return response


@app.post("/api/auth/login")
def login(data: LoginIn, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == str(data.email).lower().strip()).first()
    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="E-mail ou senha inválidos")
    if not user.active:
        raise HTTPException(status_code=403, detail="Conta inativa")
    if user.role == "client" and EMAIL_CONFIRMATION_REQUIRED and not (user.email_verified and user.phone_verified):
        raise HTTPException(status_code=403, detail="Confirme o código enviado por e-mail antes de entrar")
    return user_to_dict(user)


# ============================================================
# USUÁRIOS / PETS / PASSEIOS
# ============================================================

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
    pet = Pet(**data.model_dump())
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
    client = db.get(User, data.client_id)
    if not client or client.role != "client":
        raise HTTPException(status_code=400, detail="Cliente inválido")
    if EMAIL_CONFIRMATION_REQUIRED and not (client.email_verified and client.phone_verified):
        raise HTTPException(status_code=403, detail="Cliente ainda não confirmado")
    if data.pet_id:
        pet = db.get(Pet, data.pet_id)
        if not pet or pet.owner_id != client.id:
            raise HTTPException(status_code=400, detail="Pet inválido para este cliente")
    if data.walker_id:
        walker = db.get(User, data.walker_id)
        if not walker or walker.role != "walker":
            raise HTTPException(status_code=400, detail="Passeador inválido")

    price = 14 + (data.duration_minutes / 30) * 16 + max(data.dogs_count - 1, 0) * 9
    distance = 1.2 + max(data.dogs_count - 1, 0) * 0.3
    walk = WalkRequest(
        **data.model_dump(),
        estimated_price=round(price, 2),
        distance_km=round(distance, 1),
        expires_at=datetime.utcnow() + timedelta(minutes=5),
        status="convite_enviado",
    )
    db.add(walk)
    db.commit()
    walk.pix_code = make_pix_code(walk.id, walk.estimated_price)
    db.commit()
    db.refresh(walk)
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
    walk = db.get(WalkRequest, walk_id)
    if not walk:
        raise HTTPException(status_code=404, detail="Solicitação não encontrada")
    walk.payment_status = "pago"
    if walk.status in ["pendente", "convite_enviado"]:
        walk.status = "pagamento_confirmado"
    db.commit()
    payload = walk_to_dict(walk)
    await manager.broadcast({"type": "payment_confirmed", "walk": payload})
    return payload


@app.post("/api/walks/{walk_id}/start")
async def start_walk(walk_id: int, db: Session = Depends(get_db)):
    walk = db.get(WalkRequest, walk_id)
    if not walk:
        raise HTTPException(status_code=404, detail="Solicitação não encontrada")
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


@app.post("/api/walks/{walk_id}/gps")
async def update_gps(walk_id: int, data: LocationIn, db: Session = Depends(get_db)):
    return await update_location(walk_id, data, db)


@app.post("/api/messages")
async def create_message(data: MessageIn, db: Session = Depends(get_db)):
    msg = Message(**data.model_dump())
    db.add(msg)
    db.commit()
    db.refresh(msg)
    payload = {
        "id": msg.id,
        "request_id": msg.request_id,
        "sender_id": msg.sender_id,
        "text": msg.text,
        "created_at": msg.created_at.isoformat(),
    }
    await manager.broadcast({"type": "message", "message": payload})
    return payload


@app.get("/api/messages/{request_id}")
def list_messages(request_id: int, db: Session = Depends(get_db)):
    msgs = db.query(Message).filter(Message.request_id == request_id).order_by(Message.id.asc()).all()
    return [
        {
            "id": m.id,
            "request_id": m.request_id,
            "sender_id": m.sender_id,
            "text": m.text,
            "created_at": m.created_at.isoformat(),
        }
        for m in msgs
    ]


# ============================================================
# FRONTEND
# ============================================================

@app.get("/")
def index():
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/admin")
def admin_page():
    admin_file = FRONTEND_DIR / "admin.html"
    if admin_file.exists():
        return FileResponse(admin_file)
    return FileResponse(FRONTEND_DIR / "index.html")


app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")
