from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.routes import router
from app.core.config import settings
from app.core.security import get_password_hash
from app.db.migrations import ensure_sqlite_columns
from app.db.session import Base, SessionLocal, engine
from app.models.user import User

app = FastAPI(title=settings.APP_NAME, version="9.2.0")


def ensure_runtime_columns() -> None:
    """Garante colunas novas em bancos existentes, inclusive PostgreSQL no Render."""
    dialect = engine.dialect.name
    if dialect == "postgresql":
        statements = [
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS accepted_terms BOOLEAN DEFAULT FALSE",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS accepted_terms_at TIMESTAMP NULL",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS terms_version VARCHAR(120) NULL",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS accepted_terms_items TEXT NULL",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS pix_key VARCHAR(255) NULL",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS pix_key_type VARCHAR(30) NULL",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS pix_holder_name VARCHAR(255) NULL",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS pix_holder_document VARCHAR(80) NULL",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS pix_verified BOOLEAN DEFAULT FALSE",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS pix_updated_at TIMESTAMP NULL",
            "ALTER TABLE pets ADD COLUMN IF NOT EXISTS photo_url TEXT NULL",
            "ALTER TABLE pets ADD COLUMN IF NOT EXISTS dog_count INTEGER DEFAULT 1",
            "ALTER TABLE walk_requests ADD COLUMN IF NOT EXISTS dog_count INTEGER DEFAULT 1",
            "ALTER TABLE walk_requests ADD COLUMN IF NOT EXISTS payment_id VARCHAR(80) NULL",
            "ALTER TABLE walk_requests ADD COLUMN IF NOT EXISTS payment_provider VARCHAR(30) DEFAULT 'mercado_pago'",
            "ALTER TABLE walk_requests ADD COLUMN IF NOT EXISTS payment_link TEXT NULL",
            "ALTER TABLE walk_requests ADD COLUMN IF NOT EXISTS paid_at TIMESTAMP NULL",
            "ALTER TABLE walk_requests ADD COLUMN IF NOT EXISTS payment_updated_at TIMESTAMP NULL",
            "ALTER TABLE walk_requests ADD COLUMN IF NOT EXISTS platform_fee_percent DOUBLE PRECISION DEFAULT 20",
            "ALTER TABLE walk_requests ADD COLUMN IF NOT EXISTS platform_fee_amount DOUBLE PRECISION DEFAULT 0",
            "ALTER TABLE walk_requests ADD COLUMN IF NOT EXISTS walker_amount DOUBLE PRECISION DEFAULT 0",
            "ALTER TABLE walk_requests ADD COLUMN IF NOT EXISTS wallet_status VARCHAR(30) DEFAULT 'pending'",
            "ALTER TABLE walk_requests ADD COLUMN IF NOT EXISTS released_at TIMESTAMP NULL",
            "ALTER TABLE messages ADD COLUMN IF NOT EXISTS sender_name VARCHAR(120) NULL",
            "ALTER TABLE messages ADD COLUMN IF NOT EXISTS sender_role VARCHAR(20) NULL",
            "ALTER TABLE messages ADD COLUMN IF NOT EXISTS sender_photo TEXT NULL",
        ]
    else:
        statements = [
            "ALTER TABLE users ADD COLUMN accepted_terms BOOLEAN DEFAULT FALSE",
            "ALTER TABLE users ADD COLUMN accepted_terms_at DATETIME",
            "ALTER TABLE users ADD COLUMN terms_version VARCHAR(120)",
            "ALTER TABLE users ADD COLUMN accepted_terms_items TEXT",
            "ALTER TABLE users ADD COLUMN pix_key VARCHAR(255)",
            "ALTER TABLE users ADD COLUMN pix_key_type VARCHAR(30)",
            "ALTER TABLE users ADD COLUMN pix_holder_name VARCHAR(255)",
            "ALTER TABLE users ADD COLUMN pix_holder_document VARCHAR(80)",
            "ALTER TABLE users ADD COLUMN pix_verified BOOLEAN DEFAULT FALSE",
            "ALTER TABLE users ADD COLUMN pix_updated_at DATETIME",
        ]
    with engine.begin() as conn:
        for statement in statements:
            try:
                conn.execute(text(statement))
            except Exception:
                pass


Base.metadata.create_all(bind=engine)
ensure_sqlite_columns()
ensure_runtime_columns()


def create_admin():
    db: Session = SessionLocal()
    try:
        admin_email = "admin@amigopet.com"
        admin_password = "123456"

        existing = db.query(User).filter(User.email == admin_email).first()

        if not existing:
            admin = User(
                full_name="Administrador",
                email=admin_email,
                password_hash=get_password_hash(admin_password),
                role="admin",
                neighborhood="Painel central",
                city="Sistema",
                address="Ambiente administrativo",
                profile_photo=None,
                online=False,
                active=True,
            )
            db.add(admin)
            db.commit()
            print("✅ Admin criado automaticamente.")
        else:
            print("ℹ️ Admin já existe.")
    finally:
        db.close()


create_admin()

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

storage_dir = Path("storage")
storage_dir.mkdir(exist_ok=True)
app.mount("/storage", StaticFiles(directory=str(storage_dir)), name="storage")

app.include_router(router, prefix="/api")

BASE_DIR = Path(__file__).resolve().parent.parent.parent
FRONTEND_DIR = BASE_DIR / "frontend"
INDEX_FILE = FRONTEND_DIR / "index.html"


@app.get("/health", include_in_schema=False)
async def health():
    return JSONResponse({"status": "ok"})


if FRONTEND_DIR.exists():
    app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIR)), name="assets")


    @app.get("/admin", include_in_schema=False)
    async def serve_admin_panel():
        admin_file = FRONTEND_DIR / "admin.html"
        if admin_file.exists():
            response = FileResponse(admin_file, media_type="text/html")
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
            return response
        return JSONResponse({"detail": "admin.html não encontrado"}, status_code=404)

    @app.get("/admin.html", include_in_schema=False)
    async def serve_admin_html():
        admin_file = FRONTEND_DIR / "admin.html"
        if admin_file.exists():
            response = FileResponse(admin_file, media_type="text/html")
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
            return response
        return JSONResponse({"detail": "admin.html não encontrado"}, status_code=404)

    @app.get("/landing.html", include_in_schema=False)
    async def serve_landing():
        landing_file = FRONTEND_DIR / "landing.html"
        if landing_file.exists():
            response = FileResponse(landing_file, media_type="text/html")
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
            return response
        return JSONResponse({"detail": "landing.html não encontrado"}, status_code=404)

    @app.get("/", include_in_schema=False)
    async def serve_frontend():
        response = FileResponse(INDEX_FILE)
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response

    @app.get("/app.js", include_in_schema=False)
    async def serve_app_js():
        response = FileResponse(FRONTEND_DIR / "app.js", media_type="application/javascript")
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response

    @app.get("/styles.css", include_in_schema=False)
    async def serve_styles_css():
        css_file = FRONTEND_DIR / "styles.css"
        if css_file.exists():
            response = FileResponse(css_file, media_type="text/css")
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
            return response
        return JSONResponse({"detail": "styles.css não encontrado"}, status_code=404)