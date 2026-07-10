"""initial schema managed by alembic

Revision ID: 20260709_0001
Revises:
Create Date: 2026-07-09
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text

revision = "20260709_0001"
down_revision = None
branch_labels = None
depends_on = None


def _dialect() -> str:
    return op.get_bind().dialect.name


def _tables() -> set[str]:
    return set(inspect(op.get_bind()).get_table_names())


def _columns(table: str) -> set[str]:
    if table not in _tables():
        return set()
    return {col["name"] for col in inspect(op.get_bind()).get_columns(table)}


def _indexes(table: str) -> set[str]:
    if table not in _tables():
        return set()
    return {idx["name"] for idx in inspect(op.get_bind()).get_indexes(table)}


def _add_column(table: str, column: sa.Column) -> None:
    if column.name not in _columns(table):
        op.add_column(table, column)


def _create_index(name: str, table: str, columns: list[str]) -> None:
    if table in _tables() and name not in _indexes(table):
        op.create_index(name, table, columns)


def _normalize_postgres() -> None:
    if _dialect() != "postgresql":
        return
    bind = op.get_bind()
    statements = [
        "UPDATE users SET password_hash='sha256$legacy$invalid' WHERE password_hash IS NULL",
        "UPDATE users SET active=TRUE WHERE active IS NULL",
        "UPDATE users SET email_verified=TRUE WHERE email_verified IS NULL",
        "UPDATE users SET phone_verified=TRUE WHERE phone_verified IS NULL",
        "UPDATE users SET accepted_terms=FALSE WHERE accepted_terms IS NULL",
        "UPDATE users SET terms_version='' WHERE terms_version IS NULL",
        "UPDATE users SET client_terms_accepted=FALSE WHERE client_terms_accepted IS NULL",
        "UPDATE users SET client_terms_version='' WHERE client_terms_version IS NULL",
        "UPDATE pets SET dog_count=1 WHERE dog_count IS NULL",
        "UPDATE walk_requests SET address='' WHERE address IS NULL",
        "UPDATE walk_requests SET pickup_lat=-22.5884 WHERE pickup_lat IS NULL",
        "UPDATE walk_requests SET pickup_lng=-43.1847 WHERE pickup_lng IS NULL",
        "UPDATE walk_requests SET walker_lat=-22.5900 WHERE walker_lat IS NULL",
        "UPDATE walk_requests SET walker_lng=-43.1810 WHERE walker_lng IS NULL",
        "UPDATE walk_requests SET duration_minutes=30 WHERE duration_minutes IS NULL",
        "UPDATE walk_requests SET dogs_count=1 WHERE dogs_count IS NULL",
        "UPDATE walk_requests SET estimated_price=25 WHERE estimated_price IS NULL",
        "UPDATE walk_requests SET distance_km=1.8 WHERE distance_km IS NULL",
        "UPDATE walk_requests SET status='pendente' WHERE status IS NULL",
        "UPDATE walk_requests SET payment_status='aguardando' WHERE payment_status IS NULL",
        "UPDATE walk_requests SET payment_method='PIX' WHERE payment_method IS NULL",
        "UPDATE walk_requests SET pix_code='' WHERE pix_code IS NULL",
        "UPDATE walk_requests SET mp_payment_id='' WHERE mp_payment_id IS NULL",
        "UPDATE walk_requests SET mp_status='' WHERE mp_status IS NULL",
        "UPDATE walk_requests SET mp_status_detail='' WHERE mp_status_detail IS NULL",
        "UPDATE walk_requests SET mp_qr_code='' WHERE mp_qr_code IS NULL",
        "UPDATE walk_requests SET mp_qr_code_base64='' WHERE mp_qr_code_base64 IS NULL",
        "UPDATE walk_requests SET mp_ticket_url='' WHERE mp_ticket_url IS NULL",
        "UPDATE walk_requests SET payout_status='aguardando' WHERE payout_status IS NULL",
        "UPDATE walk_requests SET payout_transfer_id='' WHERE payout_transfer_id IS NULL",
        "UPDATE walk_requests SET payout_amount=0 WHERE payout_amount IS NULL",
        "UPDATE walk_requests SET payout_error='' WHERE payout_error IS NULL",
        "UPDATE walk_requests SET notes='' WHERE notes IS NULL",
        "UPDATE walk_requests SET created_at=NOW() WHERE created_at IS NULL",
        "UPDATE messages SET message_type='text' WHERE message_type IS NULL",
    ]
    for statement in statements:
        bind.execute(text(statement))

    rows = bind.execute(text("""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'walk_requests'
          AND is_nullable = 'NO'
          AND column_name <> 'id'
    """)).fetchall()
    for row in rows:
        column = row[0]
        if column.replace("_", "").isalnum():
            bind.execute(text(f"ALTER TABLE walk_requests ALTER COLUMN {column} DROP NOT NULL"))

    legacy_defaults = {
        "pickup_address": "''",
        "pickup_time": "NOW()",
        "price": "0",
        "total_price": "0",
        "client_name": "''",
        "walker_name": "''",
        "dog_name": "''",
        "dog_size": "''",
        "request_status": "'convite_enviado'",
    }
    existing = {
        row[0]
        for row in bind.execute(text("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = 'walk_requests'
        """)).fetchall()
    }
    for column, default in legacy_defaults.items():
        if column in existing:
            bind.execute(text(f"ALTER TABLE walk_requests ALTER COLUMN {column} SET DEFAULT {default}"))


def upgrade() -> None:
    tables = _tables()

    if "users" not in tables:
        op.create_table(
            "users",
            sa.Column("id", sa.Integer(), primary_key=True, index=True),
            sa.Column("full_name", sa.String(120), nullable=False),
            sa.Column("email", sa.String(180), nullable=False, unique=True, index=True),
            sa.Column("password_hash", sa.String(255), nullable=False),
            sa.Column("role", sa.String(30), nullable=False, server_default="client"),
            sa.Column("phone", sa.String(30), server_default=""),
            sa.Column("photo", sa.Text(), server_default=""),
            sa.Column("document", sa.String(40), server_default=""),
            sa.Column("pix_key_type", sa.String(30), server_default=""),
            sa.Column("pix_key", sa.String(180), server_default=""),
            sa.Column("pix_holder_name", sa.String(160), server_default=""),
            sa.Column("pix_holder_document", sa.String(40), server_default=""),
            sa.Column("address", sa.Text(), server_default=""),
            sa.Column("neighborhood", sa.String(120), server_default=""),
            sa.Column("city", sa.String(120), server_default=""),
            sa.Column("lat", sa.Float(), server_default="-22.5884"),
            sa.Column("lng", sa.Float(), server_default="-43.1847"),
            sa.Column("rating", sa.Float(), server_default="5"),
            sa.Column("available", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("bio", sa.Text(), server_default=""),
            sa.Column("zip_code", sa.String(20), server_default=""),
            sa.Column("street", sa.String(160), server_default=""),
            sa.Column("number", sa.String(30), server_default=""),
            sa.Column("complement", sa.String(120), server_default=""),
            sa.Column("state", sa.String(60), server_default="RJ"),
            sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("email_verified", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("phone_verified", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("verification_code_hash", sa.String(255), server_default=""),
            sa.Column("verification_expires_at", sa.DateTime(), nullable=True),
            sa.Column("verified_at", sa.DateTime(), nullable=True),
            sa.Column("accepted_terms", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("accepted_terms_at", sa.DateTime(), nullable=True),
            sa.Column("terms_version", sa.String(20), nullable=False, server_default=""),
            sa.Column("accepted_terms_ip", sa.String(80), server_default=""),
            sa.Column("accepted_terms_user_agent", sa.Text(), server_default=""),
            sa.Column("client_terms_accepted", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("client_terms_accepted_at", sa.DateTime(), nullable=True),
            sa.Column("client_terms_version", sa.String(20), nullable=False, server_default=""),
            sa.Column("client_terms_ip", sa.String(80), server_default=""),
            sa.Column("client_terms_user_agent", sa.Text(), server_default=""),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        )
    else:
        for column in [
            sa.Column("password_hash", sa.String(255), nullable=True),
            sa.Column("phone", sa.String(30), server_default=""),
            sa.Column("photo", sa.Text(), server_default=""),
            sa.Column("document", sa.String(40), server_default=""),
            sa.Column("pix_key_type", sa.String(30), server_default=""),
            sa.Column("pix_key", sa.String(180), server_default=""),
            sa.Column("pix_holder_name", sa.String(160), server_default=""),
            sa.Column("pix_holder_document", sa.String(40), server_default=""),
            sa.Column("address", sa.Text(), server_default=""),
            sa.Column("neighborhood", sa.String(120), server_default=""),
            sa.Column("city", sa.String(120), server_default=""),
            sa.Column("zip_code", sa.String(20), server_default=""),
            sa.Column("street", sa.String(160), server_default=""),
            sa.Column("number", sa.String(30), server_default=""),
            sa.Column("complement", sa.String(120), server_default=""),
            sa.Column("state", sa.String(60), server_default="RJ"),
            sa.Column("lat", sa.Float(), server_default="-22.5884"),
            sa.Column("lng", sa.Float(), server_default="-43.1847"),
            sa.Column("rating", sa.Float(), server_default="5"),
            sa.Column("available", sa.Boolean(), server_default=sa.true()),
            sa.Column("bio", sa.Text(), server_default=""),
            sa.Column("active", sa.Boolean(), server_default=sa.true()),
            sa.Column("email_verified", sa.Boolean(), server_default=sa.true()),
            sa.Column("phone_verified", sa.Boolean(), server_default=sa.true()),
            sa.Column("verification_code_hash", sa.String(255), server_default=""),
            sa.Column("verification_expires_at", sa.DateTime(), nullable=True),
            sa.Column("verified_at", sa.DateTime(), nullable=True),
            sa.Column("accepted_terms", sa.Boolean(), server_default=sa.false()),
            sa.Column("accepted_terms_at", sa.DateTime(), nullable=True),
            sa.Column("terms_version", sa.String(20), server_default=""),
            sa.Column("accepted_terms_ip", sa.String(80), server_default=""),
            sa.Column("accepted_terms_user_agent", sa.Text(), server_default=""),
            sa.Column("client_terms_accepted", sa.Boolean(), server_default=sa.false()),
            sa.Column("client_terms_accepted_at", sa.DateTime(), nullable=True),
            sa.Column("client_terms_version", sa.String(20), server_default=""),
            sa.Column("client_terms_ip", sa.String(80), server_default=""),
            sa.Column("client_terms_user_agent", sa.Text(), server_default=""),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        ]:
            _add_column("users", column)

    if "pets" not in tables:
        op.create_table(
            "pets",
            sa.Column("id", sa.Integer(), primary_key=True, index=True),
            sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("name", sa.String(100), nullable=False),
            sa.Column("species", sa.String(60), server_default="Cachorro"),
            sa.Column("breed", sa.String(100), server_default=""),
            sa.Column("size", sa.String(50), server_default="Médio"),
            sa.Column("age", sa.String(50), server_default=""),
            sa.Column("photo", sa.Text(), server_default=""),
            sa.Column("notes", sa.Text(), server_default=""),
            sa.Column("dog_count", sa.Integer(), nullable=False, server_default="1"),
        )
    else:
        for column in [
            sa.Column("species", sa.String(60), server_default="Cachorro"),
            sa.Column("breed", sa.String(100), server_default=""),
            sa.Column("size", sa.String(50), server_default="Médio"),
            sa.Column("age", sa.String(50), server_default=""),
            sa.Column("photo", sa.Text(), server_default=""),
            sa.Column("notes", sa.Text(), server_default=""),
            sa.Column("dog_count", sa.Integer(), server_default="1"),
        ]:
            _add_column("pets", column)

    if "walk_requests" not in tables:
        op.create_table(
            "walk_requests",
            sa.Column("id", sa.Integer(), primary_key=True, index=True),
            sa.Column("client_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("walker_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("pet_id", sa.Integer(), sa.ForeignKey("pets.id"), nullable=True),
            sa.Column("address", sa.Text(), nullable=False, server_default=""),
            sa.Column("pickup_lat", sa.Float(), server_default="-22.5884"),
            sa.Column("pickup_lng", sa.Float(), server_default="-43.1847"),
            sa.Column("walker_lat", sa.Float(), server_default="-22.5900"),
            sa.Column("walker_lng", sa.Float(), server_default="-43.1810"),
            sa.Column("duration_minutes", sa.Integer(), server_default="30"),
            sa.Column("dogs_count", sa.Integer(), server_default="1"),
            sa.Column("estimated_price", sa.Float(), server_default="25"),
            sa.Column("distance_km", sa.Float(), server_default="1.8"),
            sa.Column("status", sa.String(40), server_default="pendente"),
            sa.Column("payment_status", sa.String(40), server_default="aguardando"),
            sa.Column("payment_method", sa.String(30), server_default="PIX"),
            sa.Column("pix_code", sa.Text(), server_default=""),
            sa.Column("mp_payment_id", sa.String(80), server_default=""),
            sa.Column("mp_status", sa.String(60), server_default=""),
            sa.Column("mp_status_detail", sa.String(120), server_default=""),
            sa.Column("mp_qr_code", sa.Text(), server_default=""),
            sa.Column("mp_qr_code_base64", sa.Text(), server_default=""),
            sa.Column("mp_ticket_url", sa.Text(), server_default=""),
            sa.Column("payout_status", sa.String(40), nullable=False, server_default="aguardando"),
            sa.Column("payout_transfer_id", sa.String(120), server_default=""),
            sa.Column("payout_amount", sa.Float(), server_default="0"),
            sa.Column("payout_error", sa.Text(), server_default=""),
            sa.Column("notes", sa.Text(), server_default=""),
            sa.Column("expires_at", sa.DateTime(), nullable=True),
            sa.Column("started_at", sa.DateTime(), nullable=True),
            sa.Column("finished_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        )
    else:
        for column in [
            sa.Column("client_id", sa.Integer(), nullable=True),
            sa.Column("walker_id", sa.Integer(), nullable=True),
            sa.Column("pet_id", sa.Integer(), nullable=True),
            sa.Column("address", sa.Text(), server_default=""),
            sa.Column("pickup_lat", sa.Float(), server_default="-22.5884"),
            sa.Column("pickup_lng", sa.Float(), server_default="-43.1847"),
            sa.Column("walker_lat", sa.Float(), server_default="-22.5900"),
            sa.Column("walker_lng", sa.Float(), server_default="-43.1810"),
            sa.Column("duration_minutes", sa.Integer(), server_default="30"),
            sa.Column("dogs_count", sa.Integer(), server_default="1"),
            sa.Column("estimated_price", sa.Float(), server_default="25"),
            sa.Column("distance_km", sa.Float(), server_default="1.8"),
            sa.Column("status", sa.String(40), server_default="pendente"),
            sa.Column("payment_status", sa.String(40), server_default="aguardando"),
            sa.Column("payment_method", sa.String(30), server_default="PIX"),
            sa.Column("pix_code", sa.Text(), server_default=""),
            sa.Column("mp_payment_id", sa.String(80), server_default=""),
            sa.Column("mp_status", sa.String(60), server_default=""),
            sa.Column("mp_status_detail", sa.String(120), server_default=""),
            sa.Column("mp_qr_code", sa.Text(), server_default=""),
            sa.Column("mp_qr_code_base64", sa.Text(), server_default=""),
            sa.Column("mp_ticket_url", sa.Text(), server_default=""),
            sa.Column("payout_status", sa.String(40), server_default="aguardando"),
            sa.Column("payout_transfer_id", sa.String(120), server_default=""),
            sa.Column("payout_amount", sa.Float(), server_default="0"),
            sa.Column("payout_error", sa.Text(), server_default=""),
            sa.Column("notes", sa.Text(), server_default=""),
            sa.Column("expires_at", sa.DateTime(), nullable=True),
            sa.Column("started_at", sa.DateTime(), nullable=True),
            sa.Column("finished_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        ]:
            _add_column("walk_requests", column)

    if "messages" not in tables:
        op.create_table(
            "messages",
            sa.Column("id", sa.Integer(), primary_key=True, index=True),
            sa.Column("request_id", sa.Integer(), sa.ForeignKey("walk_requests.id"), nullable=False),
            sa.Column("sender_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("text", sa.Text(), nullable=False),
            sa.Column("message_type", sa.String(30), nullable=False, server_default="text"),
            sa.Column("read_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        )
    else:
        _add_column("messages", sa.Column("message_type", sa.String(30), server_default="text"))
        _add_column("messages", sa.Column("read_at", sa.DateTime(), nullable=True))

    if "notifications" not in _tables():
        op.create_table(
            "notifications",
            sa.Column("id", sa.Integer(), primary_key=True, index=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False, index=True),
            sa.Column("title", sa.String(160), nullable=False),
            sa.Column("body", sa.Text(), server_default=""),
            sa.Column("type", sa.String(60), server_default="system", index=True),
            sa.Column("link", sa.String(240), server_default=""),
            sa.Column("is_read", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        )

    if "ratings" not in _tables():
        op.create_table(
            "ratings",
            sa.Column("id", sa.Integer(), primary_key=True, index=True),
            sa.Column("walk_id", sa.Integer(), sa.ForeignKey("walk_requests.id"), nullable=False, index=True),
            sa.Column("rater_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False, index=True),
            sa.Column("target_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False, index=True),
            sa.Column("rating", sa.Integer(), nullable=False),
            sa.Column("comment", sa.Text(), server_default=""),
            sa.Column("role", sa.String(30), server_default=""),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        )

    if "event_logs" not in _tables():
        op.create_table(
            "event_logs",
            sa.Column("id", sa.Integer(), primary_key=True, index=True),
            sa.Column("walk_id", sa.Integer(), sa.ForeignKey("walk_requests.id"), nullable=True, index=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True, index=True),
            sa.Column("event_type", sa.String(80), server_default="system", index=True),
            sa.Column("title", sa.String(180), nullable=False),
            sa.Column("details", sa.Text(), server_default=""),
            sa.Column("actor_role", sa.String(40), server_default="system"),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), index=True),
        )

    if "app_settings" not in _tables():
        op.create_table(
            "app_settings",
            sa.Column("key", sa.String(80), primary_key=True, index=True),
            sa.Column("value", sa.Text(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
        )

    _normalize_postgres()
    _create_index("ix_messages_request_created", "messages", ["request_id", "created_at"])
    _create_index("ix_notifications_user_read", "notifications", ["user_id", "is_read"])
    _create_index("ix_notifications_created_at", "notifications", ["created_at"])
    _create_index("ix_ratings_walk_rater", "ratings", ["walk_id", "rater_id"])
    _create_index("ix_ratings_target", "ratings", ["target_id"])
    _create_index("ix_event_logs_walk_created", "event_logs", ["walk_id", "created_at"])
    _create_index("ix_event_logs_type", "event_logs", ["event_type"])


def downgrade() -> None:
    raise RuntimeError("Downgrade destrutivo não é suportado para preservar dados existentes.")
