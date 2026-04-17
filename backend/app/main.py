from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from app.api.routes import router
from app.core.config import settings
from app.db.migrations import ensure_sqlite_columns
from app.db.session import Base, SessionLocal, engine
from app.models.user import User

app = FastAPI(title=settings.APP_NAME, version="9.1.0")

Base.metadata.create_all(bind=engine)
ensure_sqlite_columns()


def create_admin():
    db: Session = SessionLocal()
    try:
        admin_email = "admin@amigopet.com"
        admin_password = "1%3R723$Rj"

        existing = db.query(User).filter(User.email == admin_email).first()

        if not existing:
            admin = User(
                full_name="Administrador",
                email=admin_email,
                password=admin_password,
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
            print("Admin criado automaticamente.")
        else:
            print("Admin já existe.")
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