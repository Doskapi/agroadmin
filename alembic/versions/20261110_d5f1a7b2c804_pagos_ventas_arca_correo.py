"""pagos, ventas de granos, comprobantes de ARCA, correos importados y extracción de cartas de porte

Revision ID: d5f1a7b2c804
Revises: c3e8f2a6d915
Create Date: 2026-11-10 22:00:00
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "d5f1a7b2c804"
down_revision: str | None = "c3e8f2a6d915"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TYPE estado_carta_porte ADD VALUE IF NOT EXISTS 'procesando' BEFORE 'borrador'")

    op.add_column("facturas", sa.Column("arca_resultado", sa.String(1), nullable=True))
    op.add_column("facturas", sa.Column("arca_verificado", sa.DateTime(timezone=True), nullable=True))
    op.add_column("facturas", sa.Column("arca_observaciones", sa.Text(), nullable=True))

    op.alter_column("cartas_porte", "fecha_carga", nullable=True)
    op.alter_column("cartas_porte", "grano", nullable=True)
    op.add_column("cartas_porte", sa.Column("archivo_id", sa.Integer(), sa.ForeignKey("archivos.id"), nullable=True))
    op.add_column("cartas_porte", sa.Column("datos_extraidos", postgresql.JSONB(), nullable=True))
    op.add_column("cartas_porte", sa.Column("error_extraccion", sa.Text(), nullable=True))

    op.create_table(
        "pagos",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("factura_id", sa.Integer(), sa.ForeignKey("facturas.id", ondelete="CASCADE"), nullable=False),
        sa.Column("fecha", sa.Date(), nullable=False),
        sa.Column("monto", sa.Numeric(16, 2), nullable=False),
        sa.Column("medio", sa.String(32), nullable=False),
        sa.Column("referencia", sa.String(128), nullable=True),
        sa.Column("observaciones", sa.Text(), nullable=True),
        sa.Column("creado_por_id", sa.Integer(), sa.ForeignKey("usuarios.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_pagos_factura_id", "pagos", ["factura_id"])

    op.create_table(
        "ventas",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("fecha", sa.Date(), nullable=False),
        sa.Column("campania_id", sa.Integer(), sa.ForeignKey("campanias.id"), nullable=True),
        sa.Column("campo_id", sa.Integer(), sa.ForeignKey("campos.id"), nullable=True),
        sa.Column("lote_id", sa.Integer(), sa.ForeignKey("lotes.id"), nullable=True),
        sa.Column("grano", sa.String(64), nullable=False),
        sa.Column("kilos", sa.Numeric(14, 2), nullable=False),
        sa.Column("precio_tonelada", sa.Numeric(16, 4), nullable=True),
        sa.Column("total", sa.Numeric(16, 2), nullable=False),
        sa.Column("moneda", sa.String(3), nullable=False),
        sa.Column("cotizacion", sa.Numeric(14, 6), nullable=False),
        sa.Column("comprador", sa.String(255), nullable=True),
        sa.Column("comprobante", sa.String(64), nullable=True),
        sa.Column("observaciones", sa.Text(), nullable=True),
        sa.Column("creado_por_id", sa.Integer(), sa.ForeignKey("usuarios.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_ventas_fecha", "ventas", ["fecha"])
    op.create_index("ix_ventas_campania_id", "ventas", ["campania_id"])
    op.create_index("ix_ventas_campo_id", "ventas", ["campo_id"])

    op.create_table(
        "comprobantes_arca",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("fecha", sa.Date(), nullable=False),
        sa.Column("cuit_emisor", sa.String(11), nullable=False),
        sa.Column("razon_social", sa.String(255), nullable=True),
        sa.Column("tipo_comprobante", sa.Integer(), nullable=False),
        sa.Column("punto_venta", sa.Integer(), nullable=False),
        sa.Column("numero", sa.Integer(), nullable=False),
        sa.Column("total", sa.Numeric(16, 2), nullable=True),
        sa.Column("moneda", sa.String(3), nullable=False),
        sa.Column("cae", sa.String(14), nullable=True),
        sa.Column("importado", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("cuit_emisor", "tipo_comprobante", "punto_venta", "numero"),
    )
    op.create_index("ix_comprobantes_arca_fecha", "comprobantes_arca", ["fecha"])

    op.create_table(
        "correos_importados",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("message_id", sa.String(512), nullable=False, unique=True),
        sa.Column("fecha", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("remitente", sa.String(255), nullable=True),
        sa.Column("asunto", sa.String(512), nullable=True),
        sa.Column("facturas", postgresql.JSONB(), nullable=True),
        sa.Column("detalle", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("correos_importados")
    op.drop_table("comprobantes_arca")
    op.drop_table("ventas")
    op.drop_table("pagos")
    for c in ("error_extraccion", "datos_extraidos", "archivo_id"):
        op.drop_column("cartas_porte", c)
    for c in ("arca_observaciones", "arca_verificado", "arca_resultado"):
        op.drop_column("facturas", c)
    # El valor 'procesando' del enum queda (Postgres no permite quitar valores de un enum)
