from sqlalchemy import text
from app.db.session import engine

def ensure_columns():
    statements = [
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS phone VARCHAR(30)"
    ]
    with engine.begin() as conn:
        for stmt in statements:
            try:
                conn.execute(text(stmt))
            except:
                pass
