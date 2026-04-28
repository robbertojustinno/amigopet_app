from sqlalchemy import text
from app.db.session import engine


def ensure_sqlite_columns():
    """Cria colunas faltantes em SQLite e PostgreSQL sem quebrar deploy."""
    is_sqlite = str(engine.url).startswith("sqlite")
    sqlite_stmts = [
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
    postgres_stmts = [
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
    with engine.begin() as conn:
        for stmt in (sqlite_stmts if is_sqlite else postgres_stmts):
            try:
                conn.execute(text(stmt))
            except Exception:
                pass
