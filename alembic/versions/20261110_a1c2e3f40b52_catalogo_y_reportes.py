"""catálogo de facturas: imputaciones, insumos, cotizaciones y rubro por defecto del proveedor

Revision ID: a1c2e3f40b52
Revises: 6faf9fcf9223
Create Date: 2026-11-10 16:00:00
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a1c2e3f40b52"
down_revision: str | None = "6faf9fcf9223"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("proveedores", sa.Column("categoria_id", sa.Integer(), nullable=True))
    op.create_foreign_key("proveedores_categoria_id_fkey", "proveedores", "categorias", ["categoria_id"], ["id"],
                          ondelete="SET NULL")

    op.create_table(
        "factura_imputaciones",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("factura_id", sa.Integer(), sa.ForeignKey("facturas.id", ondelete="CASCADE"), nullable=False),
        sa.Column("campo_id", sa.Integer(), sa.ForeignKey("campos.id"), nullable=False),
        sa.Column("lote_id", sa.Integer(), sa.ForeignKey("lotes.id"), nullable=True),
        sa.Column("porcentaje", sa.Numeric(7, 4), nullable=False),
    )
    op.create_index("ix_factura_imputaciones_factura_id", "factura_imputaciones", ["factura_id"])

    op.create_table(
        "insumos",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("nombre", sa.String(255), nullable=False, unique=True),
        sa.Column("unidad", sa.String(32), nullable=True),
        sa.Column("categoria_id", sa.Integer(), sa.ForeignKey("categorias.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_table(
        "insumo_alias",
        sa.Column("descripcion", sa.String(512), primary_key=True),
        sa.Column("insumo_id", sa.Integer(), sa.ForeignKey("insumos.id", ondelete="CASCADE"), nullable=False),
    )
    op.create_index("ix_insumo_alias_insumo_id", "insumo_alias", ["insumo_id"])

    op.add_column("factura_items", sa.Column("insumo_id", sa.Integer(), nullable=True))
    op.create_foreign_key("factura_items_insumo_id_fkey", "factura_items", "insumos", ["insumo_id"], ["id"],
                          ondelete="SET NULL")
    op.create_index("ix_factura_items_insumo_id", "factura_items", ["insumo_id"])

    op.create_table(
        "cotizaciones",
        sa.Column("moneda", sa.String(3), primary_key=True),
        sa.Column("fecha", sa.Date(), primary_key=True),
        sa.Column("valor", sa.Numeric(14, 6), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("cotizaciones")
    op.drop_index("ix_factura_items_insumo_id", "factura_items")
    op.drop_constraint("factura_items_insumo_id_fkey", "factura_items", type_="foreignkey")
    op.drop_column("factura_items", "insumo_id")
    op.drop_table("insumo_alias")
    op.drop_table("insumos")
    op.drop_table("factura_imputaciones")
    op.drop_constraint("proveedores_categoria_id_fkey", "proveedores", type_="foreignkey")
    op.drop_column("proveedores", "categoria_id")
