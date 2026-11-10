"""Filtros de facturas compartidos por el catálogo (`/facturas/catalogo`) y los reportes."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from fastapi import Query
from sqlalchemy import Select, String, and_, case, cast, exists, func, or_
from sqlalchemy.orm import aliased

from app.models import EstadoFactura, Factura, FacturaImputacion, FacturaItem, Proveedor

NOTAS_CREDITO = (3, 8, 13, 53)


@dataclass
class FiltrosFactura:
    q: str | None = None
    estado: list[EstadoFactura] | None = None
    proveedor_id: int | None = None
    categoria_id: int | None = None
    campania_id: int | None = None
    campo_id: int | None = None
    lote_id: int | None = None
    tipo_comprobante: int | None = None
    moneda: str | None = None
    desde: date | None = None
    hasta: date | None = None
    monto_min: Decimal | None = None
    monto_max: Decimal | None = None
    sin_imputar: bool = False


def filtros_query(
    q: str | None = None,
    estado: list[EstadoFactura] | None = Query(None),
    proveedor_id: int | None = None,
    categoria_id: int | None = None,
    campania_id: int | None = None,
    campo_id: int | None = None,
    lote_id: int | None = None,
    tipo_comprobante: int | None = None,
    moneda: str | None = None,
    desde: date | None = None,
    hasta: date | None = None,
    monto_min: Decimal | None = None,
    monto_max: Decimal | None = None,
    sin_imputar: bool = False,
) -> FiltrosFactura:
    """Dependencia de FastAPI: lee los filtros de la query string."""
    return FiltrosFactura(q, estado, proveedor_id, categoria_id, campania_id, campo_id, lote_id, tipo_comprobante,
                          moneda, desde, hasta, monto_min, monto_max, sin_imputar)


def _tiene_imputaciones():
    return exists().where(FacturaImputacion.factura_id == Factura.id)


def aplicar(stmt: Select, f: FiltrosFactura, *, por_campo: bool = True) -> Select:
    """Agrega los WHERE de los filtros. `stmt` debe tener a Factura en el FROM.

    Con `por_campo=False` no se filtra campo/lote acá (los reportes lo hacen sobre el reparto).
    """
    if f.estado:
        stmt = stmt.where(Factura.estado.in_(f.estado))
    for col, valor in ((Factura.proveedor_id, f.proveedor_id), (Factura.categoria_id, f.categoria_id),
                       (Factura.campania_id, f.campania_id), (Factura.tipo_comprobante, f.tipo_comprobante),
                       (Factura.moneda, f.moneda)):
        if valor is not None and valor != "":
            stmt = stmt.where(col == valor)
    if por_campo and f.campo_id is not None:
        stmt = stmt.where(or_(
            and_(Factura.campo_id == f.campo_id, ~_tiene_imputaciones()),
            exists().where(FacturaImputacion.factura_id == Factura.id, FacturaImputacion.campo_id == f.campo_id),
        ))
    if por_campo and f.lote_id is not None:
        stmt = stmt.where(or_(
            and_(Factura.lote_id == f.lote_id, ~_tiene_imputaciones()),
            exists().where(FacturaImputacion.factura_id == Factura.id, FacturaImputacion.lote_id == f.lote_id),
        ))
    if f.desde:
        stmt = stmt.where(Factura.fecha_emision >= f.desde)
    if f.hasta:
        stmt = stmt.where(Factura.fecha_emision <= f.hasta)
    if f.monto_min is not None:
        stmt = stmt.where(Factura.total >= f.monto_min)
    if f.monto_max is not None:
        stmt = stmt.where(Factura.total <= f.monto_max)
    if f.sin_imputar:
        stmt = stmt.where(or_(
            Factura.categoria_id.is_(None),
            Factura.campania_id.is_(None),
            and_(Factura.campo_id.is_(None), ~_tiene_imputaciones()),
        ))
    if f.q and (q := f.q.strip()):
        patron = f"%{q}%"
        prov = aliased(Proveedor)
        digitos = "".join(c for c in q if c.isdigit())
        condiciones = [
            # alias: la consulta del catálogo ya tiene a Proveedor en el FROM y se correlacionaría
            exists().where(prov.id == Factura.proveedor_id, prov.razon_social.ilike(patron)),
            Factura.observaciones.ilike(patron),
            exists().where(FacturaItem.factura_id == Factura.id, FacturaItem.descripcion.ilike(patron)),
        ]
        if digitos:
            condiciones += [Factura.cuit_emisor.contains(digitos), cast(Factura.numero, String) == digitos.lstrip("0"),
                            Factura.cae == digitos]
        stmt = stmt.where(or_(*condiciones))
    return stmt


def signo():
    """+1 o -1 según el tipo de comprobante (las notas de crédito restan)."""
    return case((Factura.tipo_comprobante.in_(NOTAS_CREDITO), -1), else_=1)


def monto_pesos():
    return func.coalesce(Factura.total, 0) * Factura.cotizacion * signo()
