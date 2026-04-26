from datetime import datetime, timedelta
from pathlib import Path
from uuid import uuid4
import os
import hashlib
import hmac
import secrets
import requests
import json

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query, Request, Body
from sqlalchemy import select, func, text, inspect
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


FINANCE_DEFAULT_FEE_PERCENT = 20.0


def _round_money(value: float) -> float:
    try:
        return round(float(value or 0), 2)
    except Exception:
        return 0.0


def _finance_calc(price: float, fee_percent: float = FINANCE_DEFAULT_FEE_PERCENT) -> dict:
    total = _round_money(price)
    percent = _round_money(fee_percent)
    platform_fee = _round_money(total * (percent / 100))
    walker_amount = _round_money(total - platform_fee)
    return {
        "platform_fee_percent": percent,
        "platform_fee_amount": platform_fee,
        "walker_amount": walker_amount,
    }


def _table_columns(db: Session, table_name: str) -> set[str]:
    try:
        return {col["name"] for col in inspect(db.bind).get_columns(table_name)}
    except Exception:
        return set()


def _ensure_finance_schema(db: Session) -> None:
    dialect = db.bind.dialect.name if db.bind else "sqlite"
    timestamp_type = "TIMESTAMP" if dialect != "sqlite" else "DATETIME"

    walk_columns = _table_columns(db, "walk_requests")
    finance_columns = {
        "platform_fee_percent": "FLOAT DEFAULT 20",
        "platform_fee_amount": "FLOAT DEFAULT 0",
        "walker_amount": "FLOAT DEFAULT 0",
        "wallet_status": "VARCHAR(30) DEFAULT 'pending'",
        "released_at": f"{timestamp_type} NULL",
    }

    for column_name, column_type in finance_columns.items():
        if column_name not in walk_columns:
            try:
                db.execute(text(f"ALTER TABLE walk_requests ADD COLUMN {column_name} {column_type}"))
                db.commit()
            except Exception:
                db.rollback()

    if dialect == "postgresql":
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS wallet_transactions (
                id SERIAL PRIMARY KEY,
                walker_id INTEGER NOT NULL,
                request_id INTEGER,
                amount DOUBLE PRECISION DEFAULT 0,
                transaction_type VARCHAR(30) DEFAULT 'credit',
                status VARCHAR(30) DEFAULT 'pending',
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))
    else:
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS wallet_transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                walker_id INTEGER NOT NULL,
                request_id INTEGER,
                amount FLOAT DEFAULT 0,
                transaction_type VARCHAR(30) DEFAULT 'credit',
                status VARCHAR(30) DEFAULT 'pending',
                description TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """))
    db.commit()


def _get_walk_finance(db: Session, walk_id: int) -> dict:
    _ensure_finance_schema(db)
    row = db.execute(
        text("""
            SELECT platform_fee_percent, platform_fee_amount, walker_amount, wallet_status, released_at
            FROM walk_requests
            WHERE id = :walk_id
        """),
        {"walk_id": walk_id},
    ).mappings().first()

    if not row:
        return {
            "platform_fee_percent": FINANCE_DEFAULT_FEE_PERCENT,
            "platform_fee_amount": 0,
            "walker_amount": 0,
            "wallet_status": "pending",
            "released_at": None,
        }

    return {
        "platform_fee_percent": float(row.get("platform_fee_percent") or FINANCE_DEFAULT_FEE_PERCENT),
        "platform_fee_amount": float(row.get("platform_fee_amount") or 0),
        "walker_amount": float(row.get("walker_amount") or 0),
        "wallet_status": row.get("wallet_status") or "pending",
        "released_at": row.get("released_at"),
    }


def _ensure_wallet_credit_for_walk(db: Session, walk: WalkRequest) -> dict:
    _ensure_finance_schema(db)

    if not walk or not walk.walker_id:
        return {"created": False, "reason": "Passeador não vinculado."}

    finance = _finance_calc(float(walk.price or 0), FINANCE_DEFAULT_FEE_PERCENT)
    wallet_status = "available" if walk.payment_status == "paid" and walk.status in {"completed", "paid"} else "pending"

    db.execute(
        text("""
            UPDATE walk_requests
            SET platform_fee_percent = :fee_percent,
                platform_fee_amount = :fee_amount,
                walker_amount = :walker_amount,
                wallet_status = :wallet_status
            WHERE id = :walk_id
        """),
        {
            "fee_percent": finance["platform_fee_percent"],
            "fee_amount": finance["platform_fee_amount"],
            "walker_amount": finance["walker_amount"],
            "wallet_status": wallet_status,
            "walk_id": walk.id,
        },
    )

    existing = db.execute(
        text("""
            SELECT id FROM wallet_transactions
            WHERE request_id = :request_id
              AND walker_id = :walker_id
              AND transaction_type = 'credit'
            LIMIT 1
        """),
        {"request_id": walk.id, "walker_id": walk.walker_id},
    ).first()

    if existing:
        db.execute(
            text("""
                UPDATE wallet_transactions
                SET amount = :amount,
                    status = :status,
                    updated_at = CURRENT_TIMESTAMP
                WHERE request_id = :request_id
                  AND walker_id = :walker_id
                  AND transaction_type = 'credit'
            """),
            {
                "amount": finance["walker_amount"],
                "status": wallet_status,
                "request_id": walk.id,
                "walker_id": walk.walker_id,
            },
        )
        created = False
    else:
        db.execute(
            text("""
                INSERT INTO wallet_transactions
                (walker_id, request_id, amount, transaction_type, status, description)
                VALUES (:walker_id, :request_id, :amount, 'credit', :status, :description)
            """),
            {
                "walker_id": walk.walker_id,
                "request_id": walk.id,
                "amount": finance["walker_amount"],
                "status": wallet_status,
                "description": f"Crédito do passeio #{walk.id}",
            },
        )
        created = True

    db.commit()
    return {"created": created, "wallet_status": wallet_status, **finance}


def _wallet_summary(db: Session, walker_id: int | None = None) -> dict:
    _ensure_finance_schema(db)

    params = {}
    where = ""
    if walker_id:
        where = "WHERE walker_id = :walker_id"
        params["walker_id"] = walker_id

    rows = db.execute(
        text(f"""
            SELECT status, COALESCE(SUM(amount), 0) AS total
            FROM wallet_transactions
            {where}
            GROUP BY status
        """),
        params,
    ).mappings().all()

    summary = {"pending": 0.0, "available": 0.0, "paid": 0.0, "blocked": 0.0}
    for row in rows:
        summary[row["status"] or "pending"] = float(row["total"] or 0)

    summary["total_open"] = _round_money(summary["pending"] + summary["available"] + summary["blocked"])
    return summary


def _wallet_transactions(db: Session, walker_id: int | None = None, limit: int = 100) -> list[dict]:
    _ensure_finance_schema(db)
    params = {"limit": limit}
    where = ""
    if walker_id:
        where = "WHERE wt.walker_id = :walker_id"
        params["walker_id"] = walker_id

    rows = db.execute(
        text(f"""
            SELECT wt.id, wt.walker_id, wt.request_id, wt.amount, wt.transaction_type, wt.status,
                   wt.description, wt.created_at, wt.updated_at, u.full_name AS walker_name, u.email AS walker_email
            FROM wallet_transactions wt
            LEFT JOIN users u ON u.id = wt.walker_id
            {where}
            ORDER BY wt.id DESC
            LIMIT :limit
        """),
        params,
    ).mappings().all()

    return [dict(row) for row in rows]


PASSWORD_ALGORITHM = "pbkdf2_sha256"
PASSWORD_ITERATIONS = 260_000


def _get_password_hash(password: str) -> str:
    clean_password = _normalize_password(password)
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        clean_password.encode("utf-8"),
        salt.encode("utf-8"),
        PASSWORD_ITERATIONS,
    ).hex()
    return f"{PASSWORD_ALGORITHM}${PASSWORD_ITERATIONS}${salt}${digest}"


def _verify_password(plain_password: str, stored_password: str | None) -> bool:
    plain_password = _normalize_password(plain_password)
    stored_password = (stored_password or "").strip()
    if not stored_password:
        return False
    if stored_password.startswith(f"{PASSWORD_ALGORITHM}$"):
        try:
            _, iterations, salt, expected_digest = stored_password.split("$", 3)
            calculated_digest = hashlib.pbkdf2_hmac(
                "sha256",
                plain_password.encode("utf-8"),
                salt.encode("utf-8"),
                int(iterations),
            ).hex()
            return hmac.compare_digest(calculated_digest, expected_digest)
        except Exception:
            return False
    return hmac.compare_digest(plain_password, stored_password)

def _get_user_stored_password(user: User) -> str:
    return (getattr(user, "password_hash", None) or getattr(user, "password", None) or "").strip()


def _set_user_password(user: User, password: str) -> None:
    hashed_password = _get_password_hash(password)
    if hasattr(user, "password_hash"):
        user.password_hash = hashed_password
    if hasattr(user, "password"):
        user.password = hashed_password


def _user_payload(user: User) -> dict:
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
        "active": user.active,
    }


def _build_user_kwargs(
    *,
    full_name: str,
    email: str,
    password: str,
    role: str,
    neighborhood: str,
    city: str,
    address: str,
    profile_photo: str | None,
    online: bool,
    active: bool,
) -> dict:
    hashed_password = _get_password_hash(password)
    data = {
        "full_name": full_name,
        "email": email,
        "role": role,
        "neighborhood": neighborhood,
        "city": city,
        "address": address,
        "profile_photo": profile_photo,
        "online": online,
        "active": active,
    }
    if hasattr(User, "password_hash"):
        data["password_hash"] = hashed_password
    if hasattr(User, "password"):
        data["password"] = hashed_password
    return data

PROFESSIONAL_EVENT_DIR = Path("storage/professional")
PROFESSIONAL_EVENT_DIR.mkdir(parents=True, exist_ok=True)
EVENT_LOG_FILE = PROFESSIONAL_EVENT_DIR / "events.jsonl"
CONTRACTS_DIR = PROFESSIONAL_EVENT_DIR / "contracts"
CONTRACTS_DIR.mkdir(parents=True, exist_ok=True)
TERMS_FILE = PROFESSIONAL_EVENT_DIR / "terms_acceptances.jsonl"
TERMS_VERSION = "2026-04-25-v1"


def _json_safe(value):
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _append_jsonl(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {k: _json_safe(v) for k, v in payload.items()}
    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")


def _log_event(event_type: str, *, actor_id: int | None = None, walk_id: int | None = None, data: dict | None = None) -> None:
    _append_jsonl(
        EVENT_LOG_FILE,
        {
            "event_id": uuid4().hex,
            "event_type": event_type,
            "actor_id": actor_id,
            "walk_id": walk_id,
            "created_at": _db_safe_now(),
            "data": data or {},
        },
    )


def _save_contract_snapshot(db: Session, walk: WalkRequest, event_type: str) -> dict:
    snapshot = _serialize_walk_request(db, walk)
    payload = {
        "contract_id": f"AMIGOPET-{walk.id}",
        "terms_version": TERMS_VERSION,
        "event_type": event_type,
        "generated_at": _db_safe_now().isoformat(),
        "walk": snapshot,
        "legal_summary": {
            "platform_role": "intermediadora tecnológica",
            "walker_responsibility": "segurança, guarda, zelo e integridade do pet durante o passeio",
            "client_responsibility": "informações verdadeiras sobre pet, endereço, comportamento e condições especiais",
            "payment_rule": "pagamento/liberação vinculados ao status do passeio e confirmação do provedor",
        },
    }
    path = CONTRACTS_DIR / f"walk_{walk.id}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    _log_event(event_type, actor_id=getattr(walk, "walker_id", None), walk_id=walk.id, data={"contract_file": str(path)})
    return payload


def _read_jsonl(path: Path, limit: int = 100) -> list[dict]:
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()[-limit:]
    items = []
    for line in lines:
        try:
            items.append(json.loads(line))
        except Exception:
            pass
    return list(reversed(items))


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
    finance = _get_walk_finance(db, walk.id)
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
        "platform_fee_percent": finance.get("platform_fee_percent"),
        "platform_fee_amount": finance.get("platform_fee_amount"),
        "walker_amount": finance.get("walker_amount"),
        "wallet_status": finance.get("wallet_status"),
        "released_at": str(finance.get("released_at")) if finance.get("released_at") else None,
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

    if normalized_status == "paid":
        _ensure_wallet_credit_for_walk(db, walk)
        db.refresh(walk)

    return walk


@router.post("/uploads/profile-photo")
async def upload_profile_photo(request: Request, file: UploadFile = File(...)):
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
    relative_url = f"/storage/profile_photos/{filename}"
    absolute_url = str(request.base_url).rstrip("/") + relative_url
    _log_event("profile_photo_uploaded", data={"filename": filename, "content_type": file.content_type, "size": len(content)})
    return {"file_url": relative_url, "absolute_url": absolute_url, "filename": filename}


@router.get("/health")
def health():
    return {"ok": True, "app": settings.APP_NAME, "default_address": settings.DEFAULT_ADDRESS}

@router.post("/admin/login")
def admin_login(payload: UserLogin, db: Session = Depends(get_db)):
    normalized_email = _normalize_email(payload.email)
    normalized_password = _normalize_password(payload.password)

    admin = db.scalar(
        select(User).where(
            func.lower(func.trim(User.email)) == normalized_email,
            User.role == "admin",
            User.active == True,
        )
    )

    if not admin or not _verify_password(normalized_password, _get_user_stored_password(admin)):
        raise HTTPException(status_code=401, detail="Credenciais admin inválidas.")

    admin.online = True
    _set_user_password(admin, normalized_password)  # garante hash atualizado mesmo se veio senha antiga em texto puro
    db.commit()
    db.refresh(admin)
    return _user_payload(admin)

@router.get("/admin/dashboard")
def admin_dashboard(db: Session = Depends(get_db)):
    total_users = db.scalar(select(func.count()).select_from(User)) or 0
    total_clients = db.scalar(select(func.count()).select_from(User).where(User.role == "client")) or 0
    total_walkers = db.scalar(select(func.count()).select_from(User).where(User.role == "walker")) or 0
    total_requests = db.scalar(select(func.count()).select_from(WalkRequest)) or 0
    total_completed = db.scalar(select(func.count()).select_from(WalkRequest).where(WalkRequest.status == "completed")) or 0
    total_paid = db.scalar(select(func.count()).select_from(WalkRequest).where(WalkRequest.payment_status == "paid")) or 0
    pending_walkers = db.scalar(select(func.count()).select_from(User).where(User.role == "walker", User.active == False)) or 0
    total_revenue = db.scalar(select(func.coalesce(func.sum(WalkRequest.price), 0)).where(WalkRequest.payment_status == "paid")) or 0

    _ensure_finance_schema(db)
    finance_totals = db.execute(text("""
        SELECT
          COALESCE(SUM(platform_fee_amount), 0) AS platform_total,
          COALESCE(SUM(walker_amount), 0) AS walker_total
        FROM walk_requests
        WHERE payment_status = 'paid'
    """)).mappings().first()
    wallet_summary = _wallet_summary(db)

    return {
        "total_users": total_users,
        "total_clients": total_clients,
        "total_walkers": total_walkers,
        "total_requests": total_requests,
        "total_completed": total_completed,
        "total_paid": total_paid,
        "pending_walkers": pending_walkers,
        "total_revenue": float(total_revenue),
        "platform_total": float((finance_totals or {}).get("platform_total") or 0),
        "walker_total": float((finance_totals or {}).get("walker_total") or 0),
        "wallet_pending": wallet_summary.get("pending", 0),
        "wallet_available": wallet_summary.get("available", 0),
        "wallet_paid": wallet_summary.get("paid", 0),
        "wallet_blocked": wallet_summary.get("blocked", 0),
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


@router.post("/admin/users/{user_id}/approve")
def admin_approve_user(user_id: int, db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado.")
    user.active = True
    db.commit()
    db.refresh(user)
    _log_event("admin_user_approved", actor_id=0, data={"user_id": user.id, "role": user.role})
    return _user_payload(user)


@router.post("/admin/users/{user_id}/block")
def admin_block_user(user_id: int, db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado.")
    if user.role == "admin":
        raise HTTPException(status_code=400, detail="Não é permitido bloquear o administrador principal por esta rota.")
    user.active = False
    user.online = False
    db.commit()
    db.refresh(user)
    _log_event("admin_user_blocked", actor_id=0, data={"user_id": user.id, "role": user.role})
    return _user_payload(user)


@router.get("/admin/events")
def admin_events(limit: int = Query(default=100, ge=1, le=500)):
    return _read_jsonl(EVENT_LOG_FILE, limit=limit)


@router.get("/admin/contracts/{request_id}")
def admin_contract(request_id: int):
    path = CONTRACTS_DIR / f"walk_{request_id}.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Contrato digital ainda não gerado para este passeio.")
    return json.loads(path.read_text(encoding="utf-8"))




@router.get("/admin/finance")
def admin_finance(db: Session = Depends(get_db)):
    _ensure_finance_schema(db)
    totals = db.execute(text("""
        SELECT
          COALESCE(SUM(price), 0) AS gross_total,
          COALESCE(SUM(platform_fee_amount), 0) AS platform_total,
          COALESCE(SUM(walker_amount), 0) AS walker_total,
          COUNT(*) AS paid_count
        FROM walk_requests
        WHERE payment_status = 'paid'
    """)).mappings().first()

    return {
        "gross_total": float((totals or {}).get("gross_total") or 0),
        "platform_total": float((totals or {}).get("platform_total") or 0),
        "walker_total": float((totals or {}).get("walker_total") or 0),
        "paid_count": int((totals or {}).get("paid_count") or 0),
        "wallet": _wallet_summary(db),
        "transactions": _wallet_transactions(db, limit=100),
    }


@router.get("/wallet/{walker_id}")
def walker_wallet(walker_id: int, db: Session = Depends(get_db)):
    walker = db.get(User, walker_id)
    if not walker or walker.role != "walker":
        raise HTTPException(status_code=404, detail="Passeador não encontrado.")

    return {
        "walker_id": walker.id,
        "walker_name": walker.full_name,
        "summary": _wallet_summary(db, walker_id=walker_id),
        "transactions": _wallet_transactions(db, walker_id=walker_id, limit=100),
    }


@router.post("/admin/wallet-transactions/{transaction_id}/mark-paid")
def admin_mark_wallet_transaction_paid(transaction_id: int, db: Session = Depends(get_db)):
    _ensure_finance_schema(db)

    tx = db.execute(
        text("SELECT * FROM wallet_transactions WHERE id = :id"),
        {"id": transaction_id},
    ).mappings().first()

    if not tx:
        raise HTTPException(status_code=404, detail="Transação não encontrada.")

    db.execute(
        text("""
            UPDATE wallet_transactions
            SET status = 'paid', updated_at = CURRENT_TIMESTAMP
            WHERE id = :id
        """),
        {"id": transaction_id},
    )

    if tx.get("request_id"):
        db.execute(
            text("""
                UPDATE walk_requests
                SET wallet_status = 'paid',
                    released_at = CURRENT_TIMESTAMP
                WHERE id = :request_id
            """),
            {"request_id": tx.get("request_id")},
        )

    db.commit()
    _log_event("wallet_transaction_paid", actor_id=0, data={"transaction_id": transaction_id, "walker_id": tx.get("walker_id"), "amount": tx.get("amount")})
    return {"ok": True, "transaction_id": transaction_id, "status": "paid"}


@router.post("/admin/wallet-transactions/{transaction_id}/block")
def admin_block_wallet_transaction(transaction_id: int, db: Session = Depends(get_db)):
    _ensure_finance_schema(db)

    tx = db.execute(
        text("SELECT * FROM wallet_transactions WHERE id = :id"),
        {"id": transaction_id},
    ).mappings().first()

    if not tx:
        raise HTTPException(status_code=404, detail="Transação não encontrada.")

    db.execute(
        text("""
            UPDATE wallet_transactions
            SET status = 'blocked', updated_at = CURRENT_TIMESTAMP
            WHERE id = :id
        """),
        {"id": transaction_id},
    )

    if tx.get("request_id"):
        db.execute(
            text("""
                UPDATE walk_requests
                SET wallet_status = 'blocked'
                WHERE id = :request_id
            """),
            {"request_id": tx.get("request_id")},
        )

    db.commit()
    _log_event("wallet_transaction_blocked", actor_id=0, data={"transaction_id": transaction_id, "walker_id": tx.get("walker_id"), "amount": tx.get("amount")})
    return {"ok": True, "transaction_id": transaction_id, "status": "blocked"}


@router.post("/legal/accept-terms")
def accept_terms(payload: dict = Body(default={})):
    user_id = payload.get("user_id")
    role = payload.get("role")
    accepted = bool(payload.get("accepted", True))
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id é obrigatório.")
    if not accepted:
        raise HTTPException(status_code=400, detail="É necessário aceitar os termos para continuar.")
    record = {
        "user_id": user_id,
        "role": role,
        "terms_version": TERMS_VERSION,
        "accepted_at": _db_safe_now(),
        "source": "app",
    }
    _append_jsonl(TERMS_FILE, record)
    _log_event("terms_accepted", actor_id=int(user_id), data={"role": role, "terms_version": TERMS_VERSION})
    return {"ok": True, "terms_version": TERMS_VERSION, "accepted_at": record["accepted_at"].isoformat()}


@router.get("/legal/terms-version")
def terms_version():
    return {"terms_version": TERMS_VERSION, "required": True}


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
        **_build_user_kwargs(
            full_name=normalized_full_name,
            email=normalized_email,
            password=normalized_password,
            role=payload.role,
            neighborhood=(payload.neighborhood or "").strip(),
            city=(payload.city or "").strip(),
            address=(payload.address or settings.DEFAULT_ADDRESS).strip(),
            profile_photo=payload.profile_photo,
            online=False,
            active=(payload.role != "walker"),
        )
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return _user_payload(user)


@router.post("/users/login")
def login_user(payload: UserLogin, db: Session = Depends(get_db)):
    normalized_email = _normalize_email(payload.email)
    normalized_password = _normalize_password(payload.password)

    user = db.scalar(
        select(User).where(
            func.lower(func.trim(User.email)) == normalized_email,
            User.active == True,
        )
    )
    if not user or not _verify_password(normalized_password, _get_user_stored_password(user)):
        raise HTTPException(status_code=401, detail="Credenciais inválidas.")

    user.online = True
    _set_user_password(user, normalized_password)  # migra senha antiga em texto puro para hash no primeiro login válido
    db.commit()
    db.refresh(user)
    return _user_payload(user)

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
    _log_event("walk_created", actor_id=walk.client_id, walk_id=walk.id, data={"walker_id": walk.walker_id, "pet_id": walk.pet_id, "price": float(walk.price or 0)})
    _save_contract_snapshot(db, walk, "contract_created")

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
    _log_event("walk_accepted", actor_id=payload.actor_id, walk_id=walk.id)
    _save_contract_snapshot(db, walk, "contract_accepted")
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
    _log_event("walk_declined", actor_id=payload.actor_id, walk_id=walk.id)
    return _serialize_walk_request(db, walk)


@router.post("/walk-requests/{request_id}/complete")
def complete_walk(request_id: int, payload: WalkRequestAction, db: Session = Depends(get_db)):
    walk = db.get(WalkRequest, request_id)
    if not walk:
        raise HTTPException(status_code=404, detail="Solicitação não encontrada.")
    if walk.walker_id != payload.actor_id:
        raise HTTPException(status_code=403, detail="Somente o passeador pode concluir.")

    walk.status = "completed"
    if walk.payment_status in {None, "", "unpaid"}:
        walk.payment_status = "payment_pending"
    db.commit()
    db.refresh(walk)
    _log_event("walk_completed_by_walker", actor_id=payload.actor_id, walk_id=walk.id, data={"payment_status": walk.payment_status})
    _save_contract_snapshot(db, walk, "contract_completed")
    redis_service.publish(f"client:{walk.client_id}", {"type": "walk_completed", "request_id": walk.id})
    return _serialize_walk_request(db, walk)


@router.post("/walk-requests/{request_id}/emergency")
def emergency_alert(request_id: int, payload: dict = Body(default={}), db: Session = Depends(get_db)):
    walk = db.get(WalkRequest, request_id)
    if not walk:
        raise HTTPException(status_code=404, detail="Solicitação não encontrada.")
    actor_id = payload.get("actor_id")
    message = (payload.get("message") or "Emergência acionada no passeio.").strip()
    location = payload.get("location") or {}
    if actor_id not in {walk.client_id, walk.walker_id}:
        raise HTTPException(status_code=403, detail="Somente cliente ou passeador desta solicitação podem acionar emergência.")
    _log_event("emergency_alert", actor_id=actor_id, walk_id=walk.id, data={"message": message, "location": location})
    redis_service.publish(f"client:{walk.client_id}", {"type": "emergency_alert", "request_id": walk.id, "message": message})
    if walk.walker_id:
        redis_service.publish(f"walker:{walk.walker_id}", {"type": "emergency_alert", "request_id": walk.id, "message": message})
    return {"ok": True, "message": "Alerta de emergência registrado.", "request_id": walk.id}


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
    amount: float | None = Query(default=None),
    db: Session = Depends(get_db),
):
    walk = db.get(WalkRequest, request_id)
    if not walk:
        raise HTTPException(status_code=404, detail="Solicitação não encontrada.")

    if walk.status not in {"completed", "payment_pending", "paid"}:
        raise HTTPException(status_code=400, detail="O pagamento só pode ser gerado após o passeio ser finalizado pelo passeador.")

    if walk.status not in {"completed", "paid"}:
        raise HTTPException(status_code=400, detail="O pagamento só pode ser gerado após o passeio ser finalizado pelo passeador.")

    client = db.get(User, walk.client_id)
    if not client:
        raise HTTPException(status_code=400, detail="Cliente da solicitação não encontrado.")

    webhook_base_url = (settings.WEBHOOK_BASE_URL or "").strip().rstrip("/")
    if not webhook_base_url:
        webhook_base_url = str(request.base_url).rstrip("/")

    payload = {
        "transaction_amount": float(amount if amount is not None else (walk.price or 1.0)),
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
    _log_event("payment_generated", actor_id=walk.client_id, walk_id=walk.id, data={"payment_id": walk.payment_id, "payment_status": walk.payment_status})

    return {
        "request_id": request_id,
        "amount": float(amount if amount is not None else (walk.price or 1.0)),
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
    _log_event("payment_webhook_received", actor_id=walk.client_id, walk_id=walk.id, data={"payment_id": walk.payment_id, "payment_status": walk.payment_status})

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
