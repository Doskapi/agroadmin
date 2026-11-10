"""sesiones revocables, verificación en dos pasos, recuperación de contraseña y auditoría

Revision ID: b7d4c1e9a3f0
Revises: a1c2e3f40b52
Create Date: 2026-11-10 18:00:00
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b7d4c1e9a3f0"
down_revision: str | None = "a1c2e3f40b52"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("usuarios", sa.Column("totp_secreto", sa.String(64), nullable=True))
    op.add_column("usuarios", sa.Column("totp_activo", sa.Boolean(), server_default="false", nullable=False))
    op.add_column("usuarios", sa.Column("totp_ultimo_paso", sa.Integer(), nullable=True))

    op.create_table(
        "sesiones",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("usuario_id", sa.Integer(), sa.ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False),
        sa.Column("creada", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("ultima_actividad", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("expira", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revocada", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ip", sa.String(64), nullable=True),
        sa.Column("user_agent", sa.String(255), nullable=True),
    )
    op.create_index("ix_sesiones_usuario_id", "sesiones", ["usuario_id"])

    op.create_table(
        "tokens_recuperacion",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("usuario_id", sa.Integer(), sa.ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False),
        sa.Column("expira", sa.DateTime(timezone=True), nullable=False),
        sa.Column("usado", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "auditoria",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("fecha", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("usuario_id", sa.Integer(), sa.ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True),
        sa.Column("accion", sa.String(64), nullable=False),
        sa.Column("entidad", sa.String(64), nullable=True),
        sa.Column("entidad_id", sa.String(64), nullable=True),
        sa.Column("detalle", postgresql.JSONB(), nullable=True),
        sa.Column("ip", sa.String(64), nullable=True),
    )
    op.create_index("ix_auditoria_fecha", "auditoria", ["fecha"])
    op.create_index("ix_auditoria_usuario_id", "auditoria", ["usuario_id"])
    op.create_index("ix_auditoria_accion", "auditoria", ["accion"])
    op.create_index("ix_auditoria_entidad", "auditoria", ["entidad", "entidad_id"])


def downgrade() -> None:
    op.drop_table("auditoria")
    op.drop_table("tokens_recuperacion")
    op.drop_table("sesiones")
    op.drop_column("usuarios", "totp_ultimo_paso")
    op.drop_column("usuarios", "totp_activo")
    op.drop_column("usuarios", "totp_secreto")
