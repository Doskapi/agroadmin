"""Reportes de gastos y producción. Los montos se expresan en pesos (total x cotización)
y las notas de crédito restan."""

import enum
import io
from datetime import date
from decimal import Decimal

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from openpyxl import Workbook
from openpyxl.styles import Font
from sqlalchemy import case, func, select

from app.deps import DB, requiere
from app.models import Campania, Campo, CartaPorte, Categoria, EstadoCartaPorte, EstadoFactura, Factura, Proveedor
from app.schemas import FilaReporte, ResumenDashboard

router = APIRouter(prefix="/reportes", tags=["reportes"], dependencies=[requiere("reportes:ver")])

NOTAS_CREDITO = (3, 8, 13, 53)
_signo = case((Factura.tipo_comprobante.in_(NOTAS_CREDITO), -1), else_=1)
MONTO_PESOS = func.coalesce(Factura.total, 0) * Factura.cotizacion * _signo


class Agrupar(str, enum.Enum):
    mes = "mes"
    categoria = "categoria"
    proveedor = "proveedor"
    campo = "campo"
    campania = "campania"


def _clave(agrupar: Agrupar):
    match agrupar:
        case Agrupar.mes:
            return func.to_char(Factura.fecha_emision, "YYYY-MM"), None
        case Agrupar.categoria:
            return Categoria.nombre, (Categoria, Factura.categoria_id == Categoria.id)
        case Agrupar.proveedor:
            return Proveedor.razon_social, (Proveedor, Factura.proveedor_id == Proveedor.id)
        case Agrupar.campo:
            return Campo.nombre, (Campo, Factura.campo_id == Campo.id)
        case Agrupar.campania:
            return Campania.nombre, (Campania, Factura.campania_id == Campania.id)


def _gastos(db, agrupar: Agrupar, desde=None, hasta=None, campania_id=None, campo_id=None,
            incluir_pendientes=False, limite: int | None = None) -> list[FilaReporte]:
    clave, join = _clave(agrupar)
    total = func.sum(MONTO_PESOS)
    stmt = select(clave.label("clave"), func.count(Factura.id), total).select_from(Factura)
    if join:
        stmt = stmt.outerjoin(*join)
    estados = [EstadoFactura.confirmada] + ([EstadoFactura.pendiente_revision] if incluir_pendientes else [])
    stmt = stmt.where(Factura.estado.in_(estados))
    if desde:
        stmt = stmt.where(Factura.fecha_emision >= desde)
    if hasta:
        stmt = stmt.where(Factura.fecha_emision <= hasta)
    if campania_id:
        stmt = stmt.where(Factura.campania_id == campania_id)
    if campo_id:
        stmt = stmt.where(Factura.campo_id == campo_id)
    stmt = stmt.group_by(clave)
    stmt = stmt.order_by(clave) if agrupar == Agrupar.mes else stmt.order_by(total.desc())
    if limite:
        stmt = stmt.limit(limite)
    return [
        FilaReporte(clave=c, cantidad=n, total=Decimal(t or 0).quantize(Decimal("0.01")))
        for c, n, t in db.execute(stmt)
    ]


@router.get("/gastos", response_model=list[FilaReporte])
def gastos(
    db: DB,
    agrupar: Agrupar = Agrupar.categoria,
    desde: date | None = None,
    hasta: date | None = None,
    campania_id: int | None = None,
    campo_id: int | None = None,
    incluir_pendientes: bool = False,
):
    return _gastos(db, agrupar, desde, hasta, campania_id, campo_id, incluir_pendientes)


@router.get("/gastos.xlsx")
def gastos_excel(
    db: DB,
    agrupar: Agrupar = Agrupar.categoria,
    desde: date | None = None,
    hasta: date | None = None,
    campania_id: int | None = None,
    campo_id: int | None = None,
    incluir_pendientes: bool = False,
):
    filas = _gastos(db, agrupar, desde, hasta, campania_id, campo_id, incluir_pendientes)
    wb = Workbook()
    ws = wb.active
    ws.title = f"Gastos por {agrupar.value}"
    ws.append([agrupar.value.capitalize(), "Comprobantes", "Total (ARS)"])
    for celda in ws[1]:
        celda.font = Font(bold=True)
    for f in filas:
        ws.append([f.clave or "(sin asignar)", f.cantidad, float(f.total)])
    ws.append(["Total", sum(f.cantidad for f in filas), float(sum(f.total for f in filas))])
    ws[f"A{ws.max_row}"].font = Font(bold=True)
    for fila in ws.iter_rows(min_row=2, min_col=3, max_col=3):
        fila[0].number_format = '#,##0.00'
    ws.column_dimensions["A"].width = 40
    ws.column_dimensions["C"].width = 18

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="gastos_por_{agrupar.value}.xlsx"'},
    )


@router.get("/resumen", response_model=ResumenDashboard)
def resumen(db: DB, desde: date | None = None, hasta: date | None = None, campania_id: int | None = None):
    """Datos para el dashboard principal."""
    filtros = dict(desde=desde, hasta=hasta, campania_id=campania_id)
    por_mes = _gastos(db, Agrupar.mes, **filtros)

    kilos = select(func.coalesce(func.sum(func.coalesce(CartaPorte.kilos_descargados, CartaPorte.kilos_netos)), 0)) \
        .where(CartaPorte.estado != EstadoCartaPorte.anulada)
    if desde:
        kilos = kilos.where(CartaPorte.fecha_carga >= desde)
    if hasta:
        kilos = kilos.where(CartaPorte.fecha_carga <= hasta)
    if campania_id:
        kilos = kilos.where(CartaPorte.campania_id == campania_id)

    return ResumenDashboard(
        total_gastos=sum((f.total for f in por_mes), Decimal(0)),
        cantidad_facturas=sum(f.cantidad for f in por_mes),
        pendientes_revision=db.scalar(
            select(func.count()).select_from(Factura).where(Factura.estado == EstadoFactura.pendiente_revision)
        ),
        kilos_despachados=db.scalar(kilos),
        gastos_por_mes=por_mes,
        gastos_por_categoria=_gastos(db, Agrupar.categoria, **filtros),
        top_proveedores=_gastos(db, Agrupar.proveedor, **filtros, limite=10),
    )
