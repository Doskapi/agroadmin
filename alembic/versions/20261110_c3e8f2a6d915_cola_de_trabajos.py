"""cola de trabajos del worker y tareas programadas

Revision ID: c3e8f2a6d915
Revises: b7d4c1e9a3f0
Create Date: 2026-11-10 20:00:00
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c3e8f2a6d915"
down_revision: str | None = "b7d4c1e9a3f0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

estado = postgresql.ENUM("pendiente", "en_curso", "hecho", "error", name="estado_trabajo", create_type=False)


def upgrade() -> None:
    estado.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "trabajos",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tipo", sa.String(64), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("estado", estado, nullable=False),
        sa.Column("intentos", sa.Integer(), nullable=False),
        sa.Column("max_intentos", sa.Integer(), nullable=False),
        sa.Column("ejecutar_desde", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("bloqueado_hasta", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("creado", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("terminado", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_trabajos_estado", "trabajos", ["estado"])
    # El worker busca los pendientes por fecha
    op.create_index("ix_trabajos_pendientes", "trabajos", ["ejecutar_desde"],
                    postgresql_where=sa.text("estado IN ('pendiente', 'en_curso')"))
    op.create_table(
        "tareas_programadas",
        sa.Column("nombre", sa.String(64), primary_key=True),
        sa.Column("ultima_ejecucion", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("tareas_programadas")
    op.drop_table("trabajos")
    estado.drop(op.get_bind(), checkfirst=True)
