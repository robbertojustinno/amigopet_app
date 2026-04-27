from sqlalchemy import text
from app.db.session import engine


def ensure_sqlite_columns():
    stmts_sqlite = [
        "ALTER TABLE users ADD COLUMN phone VARCHAR(30)",
        "ALTER TABLE users ADD COLUMN accepted_terms BOOLEAN DEFAULT 0",
        "ALTER TABLE users ADD COLUMN accepted_terms_at DATETIME",
        "ALTER TABLE users ADD COLUMN terms_version VARCHAR(80)",
        "ALTER TABLE users ADD COLUMN accepted_terms_items TEXT",
        "ALTER TABLE pets ADD COLUMN photo_url VARCHAR(255)",
        "ALTER TABLE pets ADD COLUMN dog_count INTEGER DEFAULT 1",
        "ALTER TABLE messages ADD COLUMN sender_name VARCHAR(120)",
        "ALTER TABLE messages ADD COLUMN sender_role VARCHAR(20)",
        "ALTER TABLE messages ADD COLUMN sender_photo VARCHAR(255)",
        "ALTER TABLE walk_requests ADD COLUMN dog_count INTEGER DEFAULT 1",
        "ALTER TABLE walk_requests ADD COLUMN payment_id VARCHAR(80)",
        "ALTER TABLE walk_requests ADD COLUMN payment_provider VARCHAR(30) DEFAULT 'mercado_pago'",
        "ALTER TABLE walk_requests ADD COLUMN payment_link TEXT",
        "ALTER TABLE walk_requests ADD COLUMN paid_at DATETIME",
        "ALTER TABLE walk_requests ADD COLUMN payment_updated_at DATETIME",
    ]

    stmts_postgres = [
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS phone VARCHAR(30)",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS accepted_terms BOOLEAN DEFAULT FALSE",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS accepted_terms_at TIMESTAMP NULL",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS terms_version VARCHAR(80)",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS accepted_terms_items TEXT",
        "ALTER TABLE pets ADD COLUMN IF NOT EXISTS photo_url VARCHAR(255)",
        "ALTER TABLE pets ADD COLUMN IF NOT EXISTS dog_count INTEGER DEFAULT 1",
        "ALTER TABLE messages ADD COLUMN IF NOT EXISTS sender_name VARCHAR(120)",
        "ALTER TABLE messages ADD COLUMN IF NOT EXISTS sender_role VARCHAR(20)",
        "ALTER TABLE messages ADD COLUMN IF NOT EXISTS sender_photo VARCHAR(255)",
        "ALTER TABLE walk_requests ADD COLUMN IF NOT EXISTS dog_count INTEGER DEFAULT 1",
        "ALTER TABLE walk_requests ADD COLUMN IF NOT EXISTS payment_id VARCHAR(80)",
        "ALTER TABLE walk_requests ADD COLUMN IF NOT EXISTS payment_provider VARCHAR(30) DEFAULT 'mercado_pago'",
        "ALTER TABLE walk_requests ADD COLUMN IF NOT EXISTS payment_link TEXT",
        "ALTER TABLE walk_requests ADD COLUMN IF NOT EXISTS paid_at TIMESTAMP NULL",
        "ALTER TABLE walk_requests ADD COLUMN IF NOT EXISTS payment_updated_at TIMESTAMP NULL",
    ]

    is_sqlite = str(engine.url).startswith("sqlite")
    statements = stmts_sqlite if is_sqlite else stmts_postgres

    with engine.begin() as conn:
        for stmt in statements:
            try:
                conn.execute(text(stmt))
            except Exception:
                pass


def add_phone_column(db=None):
    """Compatibilidade com main.py antigo. Cria a coluna phone se ainda não existir."""
    statement = (
        "ALTER TABLE users ADD COLUMN phone VARCHAR(30)"
        if str(engine.url).startswith("sqlite")
        else "ALTER TABLE users ADD COLUMN IF NOT EXISTS phone VARCHAR(30)"
    )

    if db is not None:
        try:
            db.execute(text(statement))
            db.commit()
        except Exception:
            try:
                db.rollback()
            except Exception:
                pass
        return

    with engine.begin() as conn:
        try:
            conn.execute(text(statement))
        except Exception:
            pass
