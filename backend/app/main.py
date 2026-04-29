from __future__ import annotations

import asyncio
import os
import secrets
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, EmailStr
from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text, create_engine, inspect, text
from sqlalchemy.orm import Session, declarative_base, relationship, sessionmaker
from passlib.context import CryptContext

BASE_DIR = Path(__file__).resolve().parents[2]
FRONTEND_DIR = BASE_DIR / "frontend"
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./amigopet_v8.db")

if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()

# PBKDF2 evita o bug do bcrypt no Python 3.14 do Render.
# Também consegue verificar hashes antigos em bcrypt, se existirem.
pwd_context = CryptContext(
    schemes=["pbkdf2_sha256", "bcrypt"],
    deprecated=["bcrypt"],
)

app = FastAPI(title="AmigoPet V8 Mapa Tempo Real", version="8.0.0")

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
    destination_lat = Column(Float, default=-22.5884)
    destination_lng = Column(Float, default=-43.1847)
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


def hash_password(password: str) -> str:
    return pwd_context.hash((password or "")[:72])


def verify_password(password: str, password_hash: str) -> bool:
    if not password_hash:
        return False
    try:
        return pwd_context.verify((password or "")[:72], password_hash)
    except Exception:
        return False


def user_to_dict(u: User):
    return {
        "id": u.id,
        "full_name": u.full_name,
        "email": u.email,
        "role": u.role,
        "phone": u.phone,
        "photo": u.photo,
        "document": u.document,
        "address": u.address,
        "neighborhood": u.neighborhood,
        "city": u.city,
        "lat": u.lat,
        "lng": u.lng,
        "rating": u.rating,
        "available": u.available,
        "bio": u.bio,
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
    return f"000201-AMIGOPET-PIX-ID{walk_id}-VALOR{amount:.2f}-TOKEN{token}"


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
        "destination_lat": w.destination_lat,
        "destination_lng": w.destination_lng,
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


def run_lightweight_migrations():
    """Corrige bancos antigos sem apagar dados."""
    inspector = inspect(engine)
    with engine.begin() as conn:
        tables = inspector.get_table_names()
        if "users" in tables:
            cols = {c["name"] for c in inspector.get_columns("users")}
            if "password_hash" not in cols:
                conn.execute(text("ALTER TABLE users ADD COLUMN password_hash VARCHAR(255)"))
            for col, ddl in {
                "phone": "VARCHAR(30)",
                "photo": "TEXT",
                "document": "VARCHAR(40)",
                "address": "TEXT",
                "neighborhood": "VARCHAR(120)",
                "city": "VARCHAR(120)",
                "lat": "FLOAT",
                "lng": "FLOAT",
                "rating": "FLOAT",
                "available": "BOOLEAN",
                "bio": "TEXT",
                "created_at": "TIMESTAMP",
            }.items():
                if col not in cols:
                    conn.execute(text(f"ALTER TABLE users ADD COLUMN {col} {ddl}"))

        if "walk_requests" in tables:
            cols = {c["name"] for c in inspector.get_columns("walk_requests")}
            additions = {
                "pickup_lat": "FLOAT",
                "pickup_lng": "FLOAT",
                "walker_lat": "FLOAT",
                "walker_lng": "FLOAT",
                "destination_lat": "FLOAT",
                "destination_lng": "FLOAT",
                "duration_minutes": "INTEGER",
                "dogs_count": "INTEGER",
                "estimated_price": "FLOAT",
                "distance_km": "FLOAT",
                "payment_status": "VARCHAR(40)",
                "pix_code": "TEXT",
                "notes": "TEXT",
                "expires_at": "TIMESTAMP",
                "started_at": "TIMESTAMP",
                "finished_at": "TIMESTAMP",
                "created_at": "TIMESTAMP",
            }
            for col, ddl in additions.items():
                if col not in cols:
                    conn.execute(text(f"ALTER TABLE walk_requests ADD COLUMN {col} {ddl}"))


def seed_data():
    db = SessionLocal()
    try:
        admin = db.query(User).filter(User.email == "admin@amigopet.com").first()
        if not admin:
            users = [
                User(
                    full_name="Administrador AmigoPet",
                    email="admin@amigopet.com",
                    password_hash=hash_password("123456"),
                    role="admin",
                    city="Magé",
                    available=True,
                    bio="Gestão operacional da plataforma.",
                ),
                User(
                    full_name="Cliente Teste",
                    email="cliente@amigopet.com",
                    password_hash=hash_password("123456"),
                    role="client",
                    phone="(21) 98888-1111",
                    address="Rua Mirabel, 49 Piabetá - Magé - RJ",
                    neighborhood="Piabetá",
                    city="Magé",
                    lat=-22.5884,
                    lng=-43.1847,
                ),
                User(
                    full_name="Passeador Profissional",
                    email="passeador@amigopet.com",
                    password_hash=hash_password("123456"),
                    role="walker",
                    phone="(21) 99999-0000",
                    neighborhood="Piabetá",
                    city="Magé",
                    lat=-22.5900,
                    lng=-43.1810,
                    rating=4.9,
                    available=True,
                    bio="Passeador verificado, experiência com cães pequenos e grandes.",
                ),
                User(
                    full_name="Ana Walker Premium",
                    email="ana@amigopet.com",
                    password_hash=hash_password("123456"),
                    role="walker",
                    phone="(21) 97777-2222",
                    neighborhood="Centro",
                    city="Magé",
                    lat=-22.5852,
                    lng=-43.1881,
                    rating=4.8,
                    available=True,
                    bio="Rotas seguras, envio de fotos e cuidado especial.",
                ),
            ]
            db.add_all(users)
            db.commit()

        # Garante senha válida nos usuários antigos
        default_hash = hash_password("123456")
        for u in db.query(User).all():
            if not u.password_hash:
                u.password_hash = default_hash
        db.commit()

        cliente = db.query(User).filter(User.email == "cliente@amigopet.com").first()
        if cliente and db.query(Pet).filter(Pet.owner_id == cliente.id).count() == 0:
            db.add(
                Pet(
                    owner_id=cliente.id,
                    name="Thor",
                    breed="SRD",
                    size="Médio",
                    age="3 anos",
                    photo="",
                    notes="Gosta de passeios tranquilos.",
                )
            )
            db.commit()
    finally:
        db.close()


async def check_expired_walks():
    """Timer estilo Uber: convite expira automaticamente."""
    while True:
        db = SessionLocal()
        try:
            now = datetime.utcnow()
            expired = (
                db.query(WalkRequest)
                .filter(WalkRequest.status == "convite_enviado", WalkRequest.expires_at.isnot(None), WalkRequest.expires_at < now)
                .all()
            )
            for walk in expired:
                walk.status = "cancelado"
                db.commit()
                db.refresh(walk)
                await manager.broadcast({"type": "walk_expired", "walk": walk_to_dict(walk)})
        finally:
            db.close()
        await asyncio.sleep(5)


Base.metadata.create_all(bind=engine)
run_lightweight_migrations()
Base.metadata.create_all(bind=engine)
seed_data()


@app.on_event("startup")
async def startup_event():
    asyncio.create_task(check_expired_walks())


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
    return {"ok": True, "app": "AmigoPet V8 Mapa Tempo Real", "version": "8.0.0"}


@app.post("/api/auth/register")
def register(data: RegisterIn, db: Session = Depends(get_db)):
    if db.query(User).filter(User.email == data.email).first():
        raise HTTPException(status_code=400, detail="E-mail já cadastrado")
    user = User(**data.model_dump(exclude={"password"}), password_hash=hash_password(data.password))
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
    price = 14 + (data.duration_minutes / 30) * 16 + max(data.dogs_count - 1, 0) * 9
    distance = 1.2 + max(data.dogs_count - 1, 0) * 0.3

    walker_lat = -22.5900
    walker_lng = -43.1810
    if data.walker_id:
        walker = db.get(User, data.walker_id)
        if walker:
            walker_lat = walker.lat or walker_lat
            walker_lng = walker.lng or walker_lng

    walk = WalkRequest(
        **data.model_dump(),
        walker_lat=walker_lat,
        walker_lng=walker_lng,
        destination_lat=data.pickup_lat,
        destination_lng=data.pickup_lng,
        estimated_price=round(price, 2),
        distance_km=round(distance, 1),
        expires_at=datetime.utcnow() + timedelta(seconds=90),
        status="convite_enviado",
        payment_status="aguardando",
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
    walker = db.get(User, walker_id)
    if walker:
        walk.walker_id = walker_id
        walk.walker_lat = walker.lat or walk.walker_lat
        walk.walker_lng = walker.lng or walk.walker_lng
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
    db.refresh(walk)
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
    db.refresh(walk)
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
    db.refresh(walk)
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
    db.refresh(walk)
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
    db.refresh(walk)
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


@app.get("/")
def index():
    return FileResponse(FRONTEND_DIR / "index.html")


app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")
