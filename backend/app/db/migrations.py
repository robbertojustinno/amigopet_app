from sqlalchemy import text
from app.db.session import engine


def ensure_sqlite_columns():
    if not str(engine.url).startswith("sqlite"):
        return

    stmts = [
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

    with engine.begin() as conn:
        for stmt in stmts:
            try:
                conn.execute(text(stmt))
            except Exception:
                pass