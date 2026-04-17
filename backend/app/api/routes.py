from datetime import datetime, timedelta
from pathlib import Path
from uuid import uuid4
import os
import requests

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query, Request
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.models.user import User
from app.models.pet import Pet
from app.models.walk_request import WalkRequest
from app.models.message import Message
from app.schemas.user import UserCreate, UserLogin, UserOut
from app.schemas.pet import PetCreate, PetOut
from app.schemas.walk_request import WalkRequestCreate, WalkRequestAction
from app.schemas.message import MessageCreate
from app.services.redis_service import redis_service

router = APIRouter()

ALLOWED_IMAGE_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
}


def _db_safe_now() -> datetime:
    return datetime.utcnow()


def _normalize_email(value: str) -> str:
    return (value or "").strip().lower()


def _normalize_password(value: str) -> str:
    return (value or "").strip()


def _mercado_pago_token() -> str:
    token = (settings.MERCADO_PAGO_ACCESS_TOKEN or os.getenv("MERCADO_PAGO_ACCESS_TOKEN") or "").strip()
    if not token:
        raise HTTPException(status_code=500, detail="MERCADO_PAGO_ACCESS_TOKEN não configurado.")
    return token


def _mercado_pago_headers() -> dict:
    return {
        "Authorization": f"Bearer {_mercado_pago_token()}",
        "Content-Type": "application/json",
    }


def _payment_status_map(status: str | None) -> str:
    mapping = {
        "approved": "paid",
        "pending": "pending",
        "in_process": "processing",
        "authorized": "processing",
        "rejected": "failed",
        "cancelled": "cancelled",
        "refunded": "refunded",
        "charged_back": "charged_back",
    }
    return mapping.get((status or "").lower(), status or "unknown")


def _serialize_walk_request(db: Session, walk: WalkRequest) -> dict:
    client = db.get(User, walk.client_id) if walk.client_id else None
    walker = db.get(User, walk.walker_id) if walk.walker_id else None
    pet = db.get(Pet, walk.pet_id) if walk.pet_id else None
    return {
        "id": walk.id,
        "client_id": walk.client_id,
        "client_name": client.full_name if client else None,
        "client_photo": client.profile_photo if client else None,
        "walker_id": walk.walker_id,
        "walker_name": walker.full_name if walker else None,
        "walker_photo": walker.profile_photo if walker else None,
        "pet_id": walk.pet_id,
        "pet_name": pet.name if pet else None,
        "pet_photo": pet.photo_url if pet else None,
        "pickup_address": walk.pickup_address,
        "neighborhood": walk.neighborhood,
        "city": walk.city,
        "scheduled_at": walk.scheduled_at,
        "duration_minutes": walk.duration_minutes,
        "dog_count": int(getattr(walk, "dog_count", 1) or 1),
        "price": float(walk.price or 0),
        "status": walk.status,
        "payment_status": walk.payment_status,
        "payment_id": walk.payment_id,
        "payment_provider": walk.payment_provider,
        "payment_link": walk.payment_link,
        "paid_at": walk.paid_at.isoformat() if walk.paid_at else None,
        "payment_updated_at": walk.payment_updated_at.isoformat() if walk.payment_updated_at else None,
        "notes": walk.notes,
        "created_at": walk.created_at.isoformat() if walk.created_at else None,
    }


def _serialize_message(db: Session, msg: Message) -> dict:
    sender = db.get(User, msg.sender_id) if msg.sender_id else None
    return {
        "id": msg.id,
        "walk_request_id": msg.walk_request_id,
        "sender_id": msg.sender_id,
        "sender_name": msg.sender_name or (sender.full_name if sender else f"Usuário {msg.sender_id}"),
        "sender_role": msg.sender_role or (sender.role if sender else None),
        "sender_photo": msg.sender_photo or (sender.profile_photo if sender else None),
        "text": msg.text,
        "created_at": msg.created_at.isoformat() if msg.created_at else None,
    }


def _extract_walk_id_from_payment(data: dict) -> int | None:
    external_reference = data.get("external_reference")
    if external_reference:
        try:
            return int(str(external_reference))
        except Exception:
            pass

    metadata = data.get("metadata") or {}
    for key in ("request_id", "walk_request_id"):
        if metadata.get(key) is not None:
            try:
                return int(str(metadata.get(key)))
            except Exception:
                pass

    return None


def _apply_payment_to_walk(db: Session, walk: WalkRequest, payment_data: dict) -> WalkRequest:
    mp_status = (payment_data.get("status") or "").lower()
    normalized_status = _payment_status_map(mp_status)

    walk.payment_id = str(payment_data.get("id")) if payment_data.get("id") else walk.payment_id
    walk.payment_status = normalized_status
    walk.payment_provider = "mercado_pago"
    walk.payment_updated_at = _db_safe_now()

    if normalized_status == "paid":
        walk.paid_at = walk.paid_at or _db_safe_now()
        if walk.status != "completed":
            walk.status = "paid"

    db.add(walk)
    db.commit()
    db.refresh(walk)
    return walk


@router.post("/uploads/profile-photo")
async def upload_profile_photo(file: UploadFile = File(...)):
    if not file.content_type or file.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(status_code=400, detail="Envie uma imagem JPG, PNG, WEBP ou GIF.")

    uploads_dir = Path("storage/profile_photos")
    uploads_dir.mkdir(parents=True, exist_ok=True)

    suffix = Path(file.filename or "foto").suffix.lower() or ALLOWED_IMAGE_TYPES[file.content_type]
    if suffix not in {".jpg", ".jpeg", ".png", ".webp", ".gif"}:
        suffix = ALLOWED_IMAGE_TYPES[file.content_type]

    filename = f"{uuid4().hex}{suffix}"
    destination = uploads_dir / filename
    content = await file.read()

    if not content:
        raise HTTPException(status_code=400, detail="Arquivo vazio.")
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="A imagem deve ter no máximo 5 MB.")

    destination.write_bytes(content)
    return {"file_url": f"/storage/profile_photos/{filename}", "filename": filename}


@router.get("/health")
def health():
    return {"ok": True, "app": settings.APP_NAME, "default_address": settings.DEFAULT_ADDRESS}


@router.post("/admin/login")
def admin_login(payload: UserLogin):
    admin_email = os.getenv("ADMIN_EMAIL")
    admin_password = os.getenv("ADMIN_PASSWORD")

    if not admin_email or not admin_password:
        raise HTTPException(status_code=500, detail="Admin não configurado no servidor.")

    if payload.email.strip().lower() != admin_email.strip().lower() or payload.password.strip() != admin_password.strip():
        raise HTTPException(status_code=401, detail="Credenciais admin inválidas.")

    return {
        "id": 0,
        "full_name": "Administrador",
        "email": admin_email,
        "role": "admin",
        "neighborhood": "Painel central",
        "city": "Sistema",
        "address": "Ambiente administrativo",
        "online": True,
    }


@router.get("/admin/dashboard")
def admin_dashboard(db: Session = Depends(get_db)):
    total_users = db.scalar(select(func.count()).select_from(User)) or 0
    total_clients = db.scalar(select(func.count()).select_from(User).where(User.role == "client")) or 0
    total_walkers = db.scalar(select(func.count()).select_from(User).where(User.role == "walker")) or 0
    total_requests = db.scalar(select(func.count()).select_from(WalkRequest)) or 0
    total_completed = db.scalar(select(func.count()).select_from(WalkRequest).where(WalkRequest.status == "completed")) or 0
    total_paid = db.scalar(select(func.count()).select_from(WalkRequest).where(WalkRequest.payment_status == "paid")) or 0
    total_revenue = db.scalar(select(func.coalesce(func.sum(WalkRequest.price), 0)).where(WalkRequest.payment_status == "paid")) or 0

    return {
        "total_users": total_users,
        "total_clients": total_clients,
        "total_walkers": total_walkers,
        "total_requests": total_requests,
        "total_completed": total_completed,
        "total_paid": total_paid,
        "total_revenue": float(total_revenue),
    }


@router.get("/admin/users")
def admin_list_users(db: Session = Depends(get_db)):
    users = list(db.scalars(select(User).order_by(User.id.desc())).all())
    return [
        {
            "id": user.id,
            "full_name": user.full_name,
            "email": user.email,
            "role": user.role,
            "neighborhood": user.neighborhood,
            "city": user.city,
            "address": user.address,
            "profile_photo": user.profile_photo,
            "online": user.online,
            "active": user.active,
        }
        for user in users
    ]


@router.post("/users/register")
def register_user(payload: UserCreate, db: Session = Depends(get_db)):
    normalized_email = _normalize_email(payload.email)
    normalized_password = _normalize_password(payload.password)
    normalized_full_name = payload.full_name.strip()

    if payload.role not in {"client", "walker"}:
        raise HTTPException(status_code=400, detail="Role inválida.")
    if payload.role == "walker" and not payload.profile_photo:
        raise HTTPException(status_code=400, detail="Passeador precisa enviar foto obrigatoriamente.")

    exists = db.scalar(select(User).where(func.lower(func.trim(User.email)) == normalized_email))
    if exists:
        raise HTTPException(status_code=400, detail="E-mail já cadastrado.")

    user = User(
        full_name=normalized_full_name,
        email=normalized_email,
        password=normalized_password,
        role=payload.role,
        neighborhood=(payload.neighborhood or "").strip(),
        city=(payload.city or "").strip(),
        address=(payload.address or settings.DEFAULT_ADDRESS).strip(),
        profile_photo=payload.profile_photo,
        online=False,
        active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return {
        "id": user.id,
        "full_name": user.full_name,
        "email": user.email,
        "role": user.role,
        "neighborhood": user.neighborhood,
        "city": user.city,
        "address": user.address,
        "profile_photo": user.profile_photo,
        "online": user.online,
    }


@router.post("/users/login")
def login_user(payload: UserLogin, db: Session = Depends(get_db)):
    normalized_email = _normalize_email(payload.email)
    normalized_password = _normalize_password(payload.password)

    user = db.scalar(
        select(User).where(
            func.lower(func.trim(User.email)) == normalized_email,
            func.trim(User.password) == normalized_password,
            User.active == True,
        )
    )
    if not user:
        raise HTTPException(status_code=401, detail="Credenciais inválidas.")

    user.online = True
    db.commit()
    db.refresh(user)
    return {
        "id": user.id,
        "full_name": user.full_name,
        "email": user.email,
        "role": user.role,
        "neighborhood": user.neighborhood,
        "city": user.city,
        "address": user.address,
        "profile_photo": user.profile_photo,
        "online": user.online,
    }


@router.get("/walkers", response_model=list[UserOut])
def list_walkers(neighborhood: str | None = None, city: str | None = None, db: Session = Depends(get_db)):
    query = select(User).where(User.role == "walker", User.active == True)
    if neighborhood:
        query = query.where(User.neighborhood.ilike(f"%{neighborhood}%"))
    if city:
        query = query.where(User.city.ilike(f"%{city}%"))
    return list(db.scalars(query.order_by(User.full_name.asc())).all())


@router.post("/pets", response_model=PetOut)
def create_pet(payload: PetCreate, db: Session = Depends(get_db)):
    owner = db.get(User, payload.owner_id)
    if not owner or owner.role != "client":
        raise HTTPException(status_code=400, detail="Dono do pet inválido.")

    pet = Pet(**payload.model_dump())
    db.add(pet)
    db.commit()
    db.refresh(pet)
    return pet


@router.get("/pets/{owner_id}", response_model=list[PetOut])
def list_pets(owner_id: int, db: Session = Depends(get_db)):
    return list(db.scalars(select(Pet).where(Pet.owner_id == owner_id).order_by(Pet.id.desc())).all())


@router.post("/walk-requests")
def create_walk_request(payload: WalkRequestCreate, db: Session = Depends(get_db)):
    client = db.get(User, payload.client_id)
    if not client or client.role != "client":
        raise HTTPException(status_code=400, detail="Cliente inválido.")

    pet = db.get(Pet, payload.pet_id) if payload.pet_id else None
    if payload.pet_id and (not pet or pet.owner_id != payload.client_id):
        raise HTTPException(status_code=400, detail="Pet inválido para este cliente.")

    walker = db.get(User, payload.walker_id) if payload.walker_id else None
    if payload.walker_id and (not walker or walker.role != "walker"):
        raise HTTPException(status_code=400, detail="Passeador inválido.")

    status = "pending"
    expires_at = None
    if walker:
        status = "invited"
        expires_at = _db_safe_now() + timedelta(seconds=90)

    walk = WalkRequest(
        client_id=payload.client_id,
        walker_id=payload.walker_id,
        pet_id=payload.pet_id,
        pickup_address=payload.pickup_address,
        neighborhood=payload.neighborhood,
        city=payload.city,
        scheduled_at=payload.scheduled_at,
        duration_minutes=payload.duration_minutes,
        dog_count=payload.dog_count,
        price=payload.price,
        notes=payload.notes,
        status=status,
        invite_expires_at=expires_at,
        payment_status="unpaid",
        payment_provider="mercado_pago",
    )
    db.add(walk)
    db.commit()
    db.refresh(walk)

    if walker:
        redis_service.publish(
            f"walker:{walker.id}",
            {
                "type": "walk_invite",
                "request_id": walk.id,
                "expires_at": walk.invite_expires_at.isoformat() if walk.invite_expires_at else None,
            },
        )

    return _serialize_walk_request(db, walk)


@router.get("/walk-requests")
def list_walk_requests(user_id: int | None = None, db: Session = Depends(get_db)):
    query = select(WalkRequest)
    if user_id:
        query = query.where((WalkRequest.client_id == user_id) | (WalkRequest.walker_id == user_id))
    items = list(db.scalars(query.order_by(WalkRequest.id.desc())).all())
    return [_serialize_walk_request(db, item) for item in items]


@router.post("/walk-requests/{request_id}/accept")
def accept_walk_request(request_id: int, payload: WalkRequestAction, db: Session = Depends(get_db)):
    walk = db.get(WalkRequest, request_id)
    if not walk:
        raise HTTPException(status_code=404, detail="Solicitação não encontrada.")
    if walk.walker_id and walk.walker_id != payload.actor_id:
        raise HTTPException(status_code=403, detail="Somente o passeador convidado pode aceitar.")
    if walk.status not in {"invited", "pending"}:
        raise HTTPException(status_code=400, detail="Solicitação não pode mais ser aceita.")
    if walk.invite_expires_at and _db_safe_now() > walk.invite_expires_at.replace(tzinfo=None):
        walk.status = "expired"
        db.commit()
        raise HTTPException(status_code=400, detail="Convite expirou.")

    walk.walker_id = payload.actor_id
    walk.status = "accepted"
    db.commit()
    db.refresh(walk)
    redis_service.publish(f"client:{walk.client_id}", {"type": "walk_accepted", "request_id": walk.id})
    return _serialize_walk_request(db, walk)


@router.post("/walk-requests/{request_id}/decline")
def decline_walk_request(request_id: int, payload: WalkRequestAction, db: Session = Depends(get_db)):
    walk = db.get(WalkRequest, request_id)
    if not walk:
        raise HTTPException(status_code=404, detail="Solicitação não encontrada.")
    if walk.walker_id and walk.walker_id != payload.actor_id:
        raise HTTPException(status_code=403, detail="Somente o passeador convidado pode recusar.")
    walk.status = "declined"
    db.commit()
    db.refresh(walk)
    redis_service.publish(f"client:{walk.client_id}", {"type": "walk_declined", "request_id": walk.id})
    return _serialize_walk_request(db, walk)


@router.post("/walk-requests/{request_id}/complete")
def complete_walk(request_id: int, payload: WalkRequestAction, db: Session = Depends(get_db)):
    walk = db.get(WalkRequest, request_id)
    if not walk:
        raise HTTPException(status_code=404, detail="Solicitação não encontrada.")
    if walk.walker_id != payload.actor_id:
        raise HTTPException(status_code=403, detail="Somente o passeador pode concluir.")

    walk.status = "completed"
    db.commit()
    db.refresh(walk)
    return _serialize_walk_request(db, walk)


@router.post("/messages")
def send_message(payload: MessageCreate, db: Session = Depends(get_db)):
    walk = db.get(WalkRequest, payload.walk_request_id)
    if not walk:
        raise HTTPException(status_code=404, detail="Solicitação não encontrada.")

    if payload.sender_id not in {walk.client_id, walk.walker_id}:
        raise HTTPException(status_code=403, detail="Somente cliente ou passeador desta solicitação podem enviar mensagens.")

    sender = db.get(User, payload.sender_id)
    msg = Message(
        **payload.model_dump(),
        sender_name=(sender.full_name if sender else None),
        sender_role=(sender.role if sender else None),
        sender_photo=(sender.profile_photo if sender else None),
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)

    redis_service.publish(
        f"chat:{walk.id}",
        {"type": "new_message", "request_id": walk.id, "sender_id": payload.sender_id, "text": payload.text},
    )
    return _serialize_message(db, msg)


@router.get("/messages/{request_id}")
def list_messages(request_id: int, db: Session = Depends(get_db)):
    messages = list(db.scalars(select(Message).where(Message.walk_request_id == request_id).order_by(Message.id.asc())).all())
    return [_serialize_message(db, message) for message in messages]


@router.post("/maintenance/expire-invites")
def expire_invites(db: Session = Depends(get_db)):
    now = _db_safe_now()
    items = list(db.scalars(select(WalkRequest).where(WalkRequest.status == "invited", WalkRequest.invite_expires_at.is_not(None))).all())

    expired_ids = []
    for item in items:
        if item.invite_expires_at and now > item.invite_expires_at.replace(tzinfo=None):
            item.status = "expired"
            expired_ids.append(item.id)
            redis_service.publish(f"client:{item.client_id}", {"type": "walk_expired", "request_id": item.id})

    db.commit()
    return {"expired_ids": expired_ids, "count": len(expired_ids)}


@router.get("/pagamento")
def criar_pagamento(
    request: Request,
    request_id: int = Query(...),
    amount: float = Query(default=1.0),
    db: Session = Depends(get_db),
):
    walk = db.get(WalkRequest, request_id)
    if not walk:
        raise HTTPException(status_code=404, detail="Solicitação não encontrada.")

    client = db.get(User, walk.client_id)
    if not client:
        raise HTTPException(status_code=400, detail="Cliente da solicitação não encontrado.")

    webhook_base_url = (settings.WEBHOOK_BASE_URL or "").strip().rstrip("/")
    if not webhook_base_url:
        webhook_base_url = str(request.base_url).rstrip("/")

    payload = {
        "transaction_amount": float(amount),
        "description": f"Passeio com Pet #{request_id}",
        "payment_method_id": "pix",
        "notification_url": f"{webhook_base_url}/api/webhooks/mercado-pago",
        "external_reference": str(request_id),
        "metadata": {"request_id": request_id},
        "payer": {
            "email": client.email,
            "first_name": "Cliente",
            "last_name": "AmigoPet",
            "identification": {
                "type": "CPF",
                "number": "19119119100"
            }
        }
    }

    headers = _mercado_pago_headers()
    headers["X-Idempotency-Key"] = f"walk-{request_id}-{uuid4().hex}"

    response = requests.post(
        "https://api.mercadopago.com/v1/payments",
        json=payload,
        headers=headers,
        timeout=30,
    )

    try:
        data = response.json()
    except Exception:
        raise HTTPException(status_code=500, detail="Resposta inválida do Mercado Pago.")

    if response.status_code >= 400:
        raise HTTPException(
            status_code=400,
            detail=data.get("message") or data.get("error") or str(data) or "Erro ao criar pagamento Pix no Mercado Pago.",
        )

    transaction_data = data.get("point_of_interaction", {}).get("transaction_data", {})

    walk.payment_id = str(data.get("id")) if data.get("id") else None
    walk.payment_provider = "mercado_pago"
    walk.payment_link = transaction_data.get("ticket_url")
    walk.payment_status = _payment_status_map(data.get("status"))
    walk.payment_updated_at = _db_safe_now()

    db.add(walk)
    db.commit()
    db.refresh(walk)

    return {
        "request_id": request_id,
        "amount": float(amount),
        "payment_id": walk.payment_id,
        "link_pagamento": transaction_data.get("ticket_url"),
        "qr_code": transaction_data.get("qr_code"),
        "qr_code_base64": transaction_data.get("qr_code_base64"),
        "status": walk.payment_status,
    }


@router.get("/pagamento/status/{request_id}")
def status_pagamento(request_id: int, db: Session = Depends(get_db)):
    walk = db.get(WalkRequest, request_id)
    if not walk:
        raise HTTPException(status_code=404, detail="Solicitação não encontrada.")

    if not walk.payment_id:
        return {
            "request_id": walk.id,
            "payment_id": None,
            "payment_status": walk.payment_status,
            "status": walk.status,
            "paid": walk.payment_status == "paid",
        }

    response = requests.get(
        f"https://api.mercadopago.com/v1/payments/{walk.payment_id}",
        headers=_mercado_pago_headers(),
        timeout=30,
    )

    try:
        data = response.json()
    except Exception:
        raise HTTPException(status_code=500, detail="Resposta inválida do Mercado Pago.")

    if response.status_code >= 400:
        raise HTTPException(
            status_code=400,
            detail=data.get("message") or data.get("error") or "Erro ao consultar pagamento.",
        )

    walk = _apply_payment_to_walk(db, walk, data)

    return {
        "request_id": walk.id,
        "payment_id": walk.payment_id,
        "payment_status": walk.payment_status,
        "status": walk.status,
        "paid": walk.payment_status == "paid",
    }


@router.post("/webhooks/mercado-pago")
async def mercado_pago_webhook(request: Request, db: Session = Depends(get_db)):
    body = {}
    try:
        body = await request.json()
    except Exception:
        body = {}

    query = request.query_params
    payment_id = None

    if isinstance(body, dict):
        data_obj = body.get("data") or {}
        if isinstance(data_obj, dict):
            payment_id = data_obj.get("id")
        payment_id = payment_id or body.get("id")

    payment_id = payment_id or query.get("data.id") or query.get("id")

    if not payment_id:
        return {"ok": True, "message": "Webhook recebido sem payment_id."}

    payment_response = requests.get(
        f"https://api.mercadopago.com/v1/payments/{payment_id}",
        headers=_mercado_pago_headers(),
        timeout=30,
    )

    try:
        payment_data = payment_response.json()
    except Exception:
        raise HTTPException(status_code=500, detail="Resposta inválida ao consultar pagamento.")

    if payment_response.status_code >= 400:
        raise HTTPException(
            status_code=400,
            detail=payment_data.get("message") or payment_data.get("error") or "Erro ao consultar pagamento.",
        )

    walk_id = _extract_walk_id_from_payment(payment_data)
    if not walk_id:
        return {"ok": True, "message": "Pagamento localizado, mas sem request_id vinculado."}

    walk = db.get(WalkRequest, walk_id)
    if not walk:
        return {"ok": True, "message": f"WalkRequest {walk_id} não encontrado."}

    walk = _apply_payment_to_walk(db, walk, payment_data)

    if walk.payment_status == "paid":
        redis_service.publish(
            f"client:{walk.client_id}",
            {"type": "payment_confirmed", "request_id": walk.id, "payment_id": walk.payment_id},
        )
        if walk.walker_id:
            redis_service.publish(
                f"walker:{walk.walker_id}",
                {"type": "payment_confirmed", "request_id": walk.id, "payment_id": walk.payment_id},
            )

    return {
        "ok": True,
        "request_id": walk.id,
        "payment_id": walk.payment_id,
        "payment_status": walk.payment_status,
        "status": walk.status,
    }

from app.db.session import SessionLocal
from app.models.user import User

@router.get("/force-admin")
def force_admin():
    db = SessionLocal()

    admin_email = "admin@amigopet.com"
    admin_password = "1%3R723$Rj"

    existing = db.query(User).filter(User.email == admin_email).first()

    if not existing:
        admin = User(
            full_name="Administrador",
            email=admin_email,
            password=admin_password,
            role="admin",
            neighborhood="Sistema",
            city="Sistema",
            address="Admin",
            profile_photo=None,
            online=False,
            active=True,
        )
        db.add(admin)
        db.commit()
        db.close()
        return {"msg": "Admin criado"}

    db.close()
    return {"msg": "Admin já existe"}
