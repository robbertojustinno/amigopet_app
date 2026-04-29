from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, EmailStr
from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text, create_engine
from sqlalchemy.orm import Session, declarative_base, relationship, sessionmaker
from passlib.context import CryptContext

BASE_DIR = Path(__file__).resolve().parents[2]
FRONTEND_DIR = BASE_DIR / "frontend"
DATABASE_URL = "sqlite:///./amigopet.db"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

app = FastAPI(title="AmigoPet Pro", version="2.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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
    address = Column(Text, default="")
    neighborhood = Column(String(120), default="")
    city = Column(String(120), default="")
    rating = Column(Float, default=5.0)
    available = Column(Boolean, default=True)
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
    duration_minutes = Column(Integer, default=30)
    dogs_count = Column(Integer, default=1)
    estimated_price = Column(Float, default=25.0)
    status = Column(String(40), default="pendente")
    payment_status = Column(String(40), default="aguardando")
    notes = Column(Text, default="")
    expires_at = Column(DateTime, nullable=True)
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
    address: str = ""
    neighborhood: str = ""
    city: str = ""

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
    duration_minutes: int = 30
    dogs_count: int = 1
    notes: str = ""

class MessageIn(BaseModel):
    request_id: int
    sender_id: int
    text: str

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(password: str, password_hash: str) -> bool:
    return pwd_context.verify(password, password_hash)

def user_to_dict(u: User):
    return {
        "id": u.id,
        "full_name": u.full_name,
        "email": u.email,
        "role": u.role,
        "phone": u.phone,
        "photo": u.photo,
        "address": u.address,
        "neighborhood": u.neighborhood,
        "city": u.city,
        "rating": u.rating,
        "available": u.available,
    }

def pet_to_dict(p: Pet):
    return {"id": p.id, "owner_id": p.owner_id, "name": p.name, "species": p.species, "breed": p.breed, "size": p.size, "age": p.age, "photo": p.photo, "notes": p.notes}

def walk_to_dict(w: WalkRequest):
    return {
        "id": w.id,
        "client_id": w.client_id,
        "walker_id": w.walker_id,
        "pet_id": w.pet_id,
        "client": w.client.full_name if w.client else "",
        "walker": w.walker.full_name if w.walker else "Aguardando",
        "pet": w.pet.name if w.pet else "",
        "address": w.address,
        "duration_minutes": w.duration_minutes,
        "dogs_count": w.dogs_count,
        "estimated_price": w.estimated_price,
        "status": w.status,
        "payment_status": w.payment_status,
        "notes": w.notes,
        "expires_at": w.expires_at.isoformat() if w.expires_at else None,
        "created_at": w.created_at.isoformat(),
    }

def seed_data():
    db = SessionLocal()
    try:
        if db.query(User).count() == 0:
            users = [
                User(full_name="Administrador AmigoPet", email="admin@amigopet.com", password_hash=hash_password("123456"), role="admin", city="Magé", available=True),
                User(full_name="Cliente Teste", email="cliente@amigopet.com", password_hash=hash_password("123456"), role="client", address="Rua Mirabel, 49 Piabetá - Magé - RJ", neighborhood="Piabetá", city="Magé"),
                User(full_name="Passeador Profissional", email="passeador@amigopet.com", password_hash=hash_password("123456"), role="walker", phone="(21) 99999-0000", neighborhood="Piabetá", city="Magé", rating=4.9, available=True),
            ]
            db.add_all(users)
            db.commit()
            cliente = db.query(User).filter(User.email == "cliente@amigopet.com").first()
            pet = Pet(owner_id=cliente.id, name="Thor", breed="SRD", size="Médio", age="3 anos", notes="Gosta de passeios tranquilos.")
            db.add(pet)
            db.commit()
    finally:
        db.close()

Base.metadata.create_all(bind=engine)
seed_data()

@app.get("/health")
def health():
    return {"ok": True, "app": "AmigoPet Pro"}

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
    return [user_to_dict(u) for u in q.order_by(User.id.desc()).all()]

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
def walks(db: Session = Depends(get_db)):
    return [walk_to_dict(w) for w in db.query(WalkRequest).order_by(WalkRequest.id.desc()).all()]

@app.post("/api/walks")
def create_walk(data: WalkIn, db: Session = Depends(get_db)):
    price = 20 + (data.duration_minutes / 30) * 10 + max(data.dogs_count - 1, 0) * 8
    walk = WalkRequest(**data.model_dump(), estimated_price=round(price, 2), expires_at=datetime.utcnow() + timedelta(minutes=5))
    db.add(walk)
    db.commit()
    db.refresh(walk)
    return walk_to_dict(walk)

@app.post("/api/walks/{walk_id}/accept")
def accept_walk(walk_id: int, walker_id: int, db: Session = Depends(get_db)):
    walk = db.get(WalkRequest, walk_id)
    if not walk:
        raise HTTPException(status_code=404, detail="Solicitação não encontrada")
    walk.walker_id = walker_id
    walk.status = "aceito"
    db.commit()
    db.refresh(walk)
    return walk_to_dict(walk)

@app.post("/api/walks/{walk_id}/reject")
def reject_walk(walk_id: int, db: Session = Depends(get_db)):
    walk = db.get(WalkRequest, walk_id)
    if not walk:
        raise HTTPException(status_code=404, detail="Solicitação não encontrada")
    walk.status = "recusado"
    db.commit()
    return walk_to_dict(walk)

@app.post("/api/walks/{walk_id}/pay")
def pay_walk(walk_id: int, db: Session = Depends(get_db)):
    walk = db.get(WalkRequest, walk_id)
    if not walk:
        raise HTTPException(status_code=404, detail="Solicitação não encontrada")
    walk.payment_status = "pago"
    if walk.status == "pendente":
        walk.status = "aguardando_passeador"
    db.commit()
    return walk_to_dict(walk)

@app.post("/api/messages")
def create_message(data: MessageIn, db: Session = Depends(get_db)):
    msg = Message(**data.model_dump())
    db.add(msg)
    db.commit()
    db.refresh(msg)
    return {"id": msg.id, "request_id": msg.request_id, "sender_id": msg.sender_id, "text": msg.text, "created_at": msg.created_at.isoformat()}

@app.get("/api/messages/{request_id}")
def list_messages(request_id: int, db: Session = Depends(get_db)):
    msgs = db.query(Message).filter(Message.request_id == request_id).order_by(Message.id.asc()).all()
    return [{"id": m.id, "request_id": m.request_id, "sender_id": m.sender_id, "text": m.text, "created_at": m.created_at.isoformat()} for m in msgs]

@app.get("/")
def index():
    return FileResponse(FRONTEND_DIR / "index.html")

app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")
