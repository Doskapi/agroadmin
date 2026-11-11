"""Reportes de gastos y producción.

- Los montos se expresan en pesos (total x cotización del comprobante) o en dólares (`expresado_en=USD`: las facturas
  en dólares van directo y las en pesos se dividen por la cotización del BCRA del día de emisión).
- Las notas de crédito restan.
- Una factura repartida entre varios campos/lotes cuenta en cada uno según su porcentaje.
"""

import enum
import io
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from openpyxl import Workbook
from openpyxl.styles import Font
from sqlalchemy import Numeric, case, cast, distinct, exists, func, literal, select, union_all
from sqlalchemy.orm import aliased

from app.deps import DB, requiere
from app.filtros import FiltrosFactura, aplicar, filtros_query, monto_pesos, signo
from app.models import (
    Campania,
    Campo,
    CartaPorte,
    Categoria,
    Cotizacion,
    EstadoCartaPorte,
    EstadoFactura,
    Factura,
    FacturaImputacion,
    FacturaItem,
    Insumo,
    Lote,
    Proveedor,
    Venta,
)
from app.schemas import (
    Celda,
    Dimension,
    FaltanCotizaciones,
    FilaCostoHectarea,
    FilaIva,
    FilaMargen,
    FilaReporte,
    PrecioInsumo,
    ReporteCruce,
    ResumenDashboard,
    ResumenInsumo,
)

router = APIRouter(prefix="/reportes", tags=["reportes"], dependencies=[requiere("reportes:ver")])

Filtros = Annotated[FiltrosFactura, Depends(filtros_query)]
CENTAVO = Decimal("0.01")


class Agrupar(str, enum.Enum):
    mes = "mes"
    categoria = "categoria"
    proveedor = "proveedor"
    campo = "campo"
    lote = "lote"
    campania = "campania"


class Moneda(str, enum.Enum):
    ARS = "ARS"
    USD = "USD"


# --- Piezas de las consultas -------------------------------------------------


def _reparto():
    """Una fila por (factura, campo, lote) con la fracción del gasto que le toca.
    Facturas sin reparto: una sola fila con su campo/lote y fracción 1."""
    con = select(
        FacturaImputacion.factura_id.label("factura_id"), FacturaImputacion.campo_id.label("campo_id"),
        FacturaImputacion.lote_id.label("lote_id"), (FacturaImputacion.porcentaje / 100).label("fraccion"),
    )
    sin = select(
        Factura.id, Factura.campo_id, Factura.lote_id, cast(literal(1), Numeric(9, 6)),
    ).where(~exists().where(FacturaImputacion.factura_id == Factura.id))
    return union_all(con, sin).subquery("reparto")


def _cotizacion_usd():
    """Pesos por dólar del día de emisión (o el último día hábil anterior con dato)."""
    return (
        select(Cotizacion.valor)
        .where(Cotizacion.moneda == "DOL", Cotizacion.fecha <= Factura.fecha_emision)
        .order_by(Cotizacion.fecha.desc()).limit(1)
        .correlate(Factura).scalar_subquery()
    )


def _monto(moneda: Moneda):
    if moneda == Moneda.ARS:
        return monto_pesos()
    return case(
        (Factura.moneda == "DOL", func.coalesce(Factura.total, 0) * signo()),
        else_=monto_pesos() / _cotizacion_usd(),
    )


@dataclass
class Dim:
    id: object
    etiqueta: object
    joins: list = field(default_factory=list)


def _dim(agrupar: Agrupar, r, sufijo: str) -> Dim:
    match agrupar:
        case Agrupar.mes:
            mes = func.to_char(Factura.fecha_emision, "YYYY-MM")
            return Dim(mes, mes)
        case Agrupar.categoria:
            t = aliased(Categoria, name=f"cat_{sufijo}")
            return Dim(t.id, t.nombre, [(t, Factura.categoria_id == t.id)])
        case Agrupar.proveedor:
            t = aliased(Proveedor, name=f"prov_{sufijo}")
            return Dim(t.id, t.razon_social, [(t, Factura.proveedor_id == t.id)])
        case Agrupar.campania:
            t = aliased(Campania, name=f"camp_{sufijo}")
            return Dim(t.id, t.nombre, [(t, Factura.campania_id == t.id)])
        case Agrupar.campo:
            t = aliased(Campo, name=f"campo_{sufijo}")
            return Dim(t.id, t.nombre, [(t, r.c.campo_id == t.id)])
        case Agrupar.lote:
            lote = aliased(Lote, name=f"lote_{sufijo}")
            campo = aliased(Campo, name=f"lotecampo_{sufijo}")
            etiqueta = case((lote.id.is_(None), None), else_=func.concat(campo.nombre, " / ", lote.nombre))
            return Dim(lote.id, etiqueta, [(lote, r.c.lote_id == lote.id), (campo, lote.campo_id == campo.id)])


def _estados(incluir_pendientes: bool) -> list[EstadoFactura]:
    return [EstadoFactura.confirmada] + ([EstadoFactura.pendiente_revision] if incluir_pendientes else [])


def _agregado(dims: list[Dim], r, f: FiltrosFactura, moneda: Moneda, incluir_pendientes: bool):
    """SELECT ids y etiquetas de las dimensiones, cantidad de comprobantes y total, agrupado."""
    total = func.sum(_monto(moneda) * r.c.fraccion)
    cols = [c for d in dims for c in (d.id, d.etiqueta)]
    stmt = select(*cols, func.count(distinct(Factura.id)), total).select_from(Factura)
    stmt = stmt.join(r, r.c.factura_id == Factura.id)
    for d in dims:
        for tabla, on in d.joins:
            stmt = stmt.outerjoin(tabla, on)
    filtros = FiltrosFactura(**{**f.__dict__, "estado": _estados(incluir_pendientes)})
    stmt = aplicar(stmt, filtros, por_campo=False)
    if f.campo_id is not None:
        stmt = stmt.where(r.c.campo_id == f.campo_id)
    if f.lote_id is not None:
        stmt = stmt.where(r.c.lote_id == f.lote_id)
    return stmt.group_by(*cols), total


def _dec(v) -> Decimal:
    return Decimal(v or 0).quantize(CENTAVO)


def _gastos(db, agrupar: Agrupar, f: FiltrosFactura, moneda=Moneda.ARS, incluir_pendientes=False,
            limite: int | None = None) -> list[FilaReporte]:
    r = _reparto()
    d = _dim(agrupar, r, "a")
    stmt, total = _agregado([d], r, f, moneda, incluir_pendientes)
    stmt = stmt.order_by(d.etiqueta) if agrupar == Agrupar.mes else stmt.order_by(total.desc().nulls_last())
    if limite:
        stmt = stmt.limit(limite)
    return [FilaReporte(id=i, clave=c, cantidad=n, total=_dec(t)) for i, c, n, t in db.execute(stmt)]


# --- Endpoints -----------------------------------------------------------------


@router.get("/gastos", response_model=list[FilaReporte])
def gastos(db: DB, f: Filtros, agrupar: Agrupar = Agrupar.categoria, expresado_en: Moneda = Moneda.ARS,
           incluir_pendientes: bool = False):
    return _gastos(db, agrupar, f, expresado_en, incluir_pendientes)


def _excel(nombre: str, hojas: list[tuple[str, list[str], list[list]]]) -> StreamingResponse:
    wb = Workbook()
    wb.remove(wb.active)
    for titulo, encabezado, filas in hojas:
        ws = wb.create_sheet(titulo[:31])
        ws.append(encabezado)
        for c in ws[1]:
            c.font = Font(bold=True)
        for fila in filas:
            ws.append(fila)
        for fila in ws.iter_rows(min_row=2):
            for c in fila:
                if isinstance(c.value, float):
                    c.number_format = "#,##0.00"
        ws.column_dimensions["A"].width = 40
        ws.freeze_panes = "B2"
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return StreamingResponse(
        buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{nombre}.xlsx"'},
    )


@router.get("/gastos.xlsx")
def gastos_excel(db: DB, f: Filtros, agrupar: Agrupar = Agrupar.categoria, expresado_en: Moneda = Moneda.ARS,
                 incluir_pendientes: bool = False):
    filas = _gastos(db, agrupar, f, expresado_en, incluir_pendientes)
    datos = [[x.clave or "(sin asignar)", x.cantidad, float(x.total)] for x in filas]
    datos.append(["Total", sum(x.cantidad for x in filas), float(sum(x.total for x in filas))])
    return _excel(f"gastos_por_{agrupar.value}",
                  [(f"Gastos por {agrupar.value}", [agrupar.value.capitalize(), "Comprobantes", f"Total ({expresado_en.value})"],
                    datos)])


def _cruce(db, f: FiltrosFactura, filas: Agrupar, columnas: Agrupar, moneda: Moneda,
           incluir_pendientes: bool) -> ReporteCruce:
    if filas == columnas:
        raise HTTPException(422, "Filas y columnas tienen que ser distintas")
    r = _reparto()
    df, dc = _dim(filas, r, "f"), _dim(columnas, r, "c")
    stmt, _ = _agregado([df, dc], r, f, moneda, incluir_pendientes)
    res = db.execute(stmt).all()
    fs, cs = {}, {}
    celdas = []
    for fid, fet, cid, cet, n, t in res:
        fs[fid] = fet
        cs[cid] = cet
        celdas.append(Celda(fila=fid, columna=cid, cantidad=n, total=_dec(t)))

    def ordenar(dims: dict, agrupar: Agrupar, eje: str) -> list[Dimension]:
        if agrupar in (Agrupar.mes, Agrupar.campania):  # cronológico (las campañas se llaman "2025/26")
            claves = sorted(dims, key=lambda k: (k is None, dims[k] or ""))
        else:  # de mayor a menor gasto
            tot: dict = {}
            for c in celdas:
                k = getattr(c, eje)
                tot[k] = tot.get(k, 0) + c.total
            claves = sorted(dims, key=lambda k: -tot.get(k, 0))
        return [Dimension(id=k, clave=dims[k]) for k in claves]

    return ReporteCruce(filas=ordenar(fs, filas, "fila"), columnas=ordenar(cs, columnas, "columna"), celdas=celdas)


@router.get("/cruce", response_model=ReporteCruce)
def cruce(db: DB, f: Filtros, filas: Agrupar = Agrupar.categoria, columnas: Agrupar = Agrupar.mes,
          expresado_en: Moneda = Moneda.ARS, incluir_pendientes: bool = False):
    """Tabla de doble entrada, ej. rubro x mes o rubro x campaña (para comparar campañas)."""
    return _cruce(db, f, filas, columnas, expresado_en, incluir_pendientes)


@router.get("/cruce.xlsx")
def cruce_excel(db: DB, f: Filtros, filas: Agrupar = Agrupar.categoria, columnas: Agrupar = Agrupar.mes,
                expresado_en: Moneda = Moneda.ARS, incluir_pendientes: bool = False):
    c = _cruce(db, f, filas, columnas, expresado_en, incluir_pendientes)
    valores = {(x.fila, x.columna): float(x.total) for x in c.celdas}
    datos = []
    for fi in c.filas:
        fila = [valores.get((fi.id, co.id), 0.0) for co in c.columnas]
        datos.append([fi.clave or "(sin asignar)", *fila, sum(fila)])
    totales = [sum(valores.get((fi.id, co.id), 0.0) for fi in c.filas) for co in c.columnas]
    datos.append(["Total", *totales, sum(totales)])
    encabezado = [f"{filas.value} \\ {columnas.value}", *[co.clave or "(sin asignar)" for co in c.columnas], "Total"]
    return _excel(f"{filas.value}_por_{columnas.value}", [(f"{filas.value} x {columnas.value}", encabezado, datos)])


@router.get("/costo-hectarea", response_model=list[FilaCostoHectarea])
def costo_hectarea(db: DB, f: Filtros, expresado_en: Moneda = Moneda.ARS, incluir_pendientes: bool = False):
    """Gasto por campo y por lote, y su costo por hectárea (según las hectáreas cargadas en el catálogo).
    La fila del campo incluye todo lo imputado al campo, tenga o no lote."""
    r = _reparto()
    stmt, _ = _agregado([Dim(r.c.campo_id, r.c.lote_id)], r, f, expresado_en, incluir_pendientes)
    totales = {(c, lote): _dec(t) for c, lote, _, t in db.execute(stmt) if c is not None}
    campos = {c.id: c for c in db.scalars(select(Campo).where(Campo.id.in_({c for c, _ in totales})))}
    lotes = {lo.id: lo for lo in db.scalars(select(Lote).where(Lote.id.in_({lo for _, lo in totales if lo})))}

    def por_ha(total: Decimal, ha: Decimal | None) -> Decimal | None:
        return (total / ha).quantize(CENTAVO) if ha else None

    filas = []
    for campo in sorted(campos.values(), key=lambda c: c.nombre):
        total = sum((t for (c, _), t in totales.items() if c == campo.id), Decimal(0))
        filas.append(FilaCostoHectarea(campo_id=campo.id, campo=campo.nombre, lote_id=None, lote=None,
                                       hectareas=campo.hectareas, total=total,
                                       por_hectarea=por_ha(total, campo.hectareas)))
        for (c, lote_id), t in sorted(totales.items(), key=lambda x: lotes[x[0][1]].nombre if x[0][1] else ""):
            if c == campo.id and lote_id:
                lote = lotes[lote_id]
                filas.append(FilaCostoHectarea(campo_id=campo.id, campo=campo.nombre, lote_id=lote.id,
                                               lote=lote.nombre, hectareas=lote.hectareas, total=t,
                                               por_hectarea=por_ha(t, lote.hectareas)))
    return filas


@router.get("/iva", response_model=list[FilaIva])
def iva(db: DB, f: Filtros, incluir_pendientes: bool = False):
    """IVA compras por mes: neto, no gravado, IVA y percepciones en pesos (notas de crédito restan)."""
    s = Factura.cotizacion * signo()
    periodo = func.to_char(Factura.fecha_emision, "YYYY-MM")
    stmt = select(
        periodo, func.count(Factura.id),
        *[func.sum(func.coalesce(col, 0) * s) for col in
          (Factura.neto_gravado, Factura.no_gravado, Factura.iva, Factura.percepciones, Factura.total)],
    ).select_from(Factura)
    stmt = aplicar(stmt, FiltrosFactura(**{**f.__dict__, "estado": _estados(incluir_pendientes)}))
    stmt = stmt.group_by(periodo).order_by(periodo)
    return [FilaIva(periodo=p, cantidad=n, neto_gravado=_dec(a), no_gravado=_dec(b), iva=_dec(c),
                    percepciones=_dec(d), total=_dec(e)) for p, n, a, b, c, d, e in db.execute(stmt)]


@router.get("/cotizaciones-faltantes", response_model=FaltanCotizaciones)
def cotizaciones_faltantes(db: DB, f: Filtros, incluir_pendientes: bool = False):
    """Facturas en pesos que no se pueden pasar a dólares porque no hay cotización para su fecha."""
    stmt = select(func.count(), func.min(Factura.fecha_emision)).select_from(Factura).where(
        Factura.moneda != "DOL", Factura.fecha_emision.is_not(None), _cotizacion_usd().is_(None))
    stmt = aplicar(stmt, FiltrosFactura(**{**f.__dict__, "estado": _estados(incluir_pendientes)}))
    n, primera = db.execute(stmt).one()
    return FaltanCotizaciones(facturas_sin_cotizacion=n, primera_fecha_faltante=primera)


# --- Margen (ventas - gastos) -----------------------------------------------------


@router.get("/margen", response_model=list[FilaMargen], dependencies=[requiere("ventas:leer")])
def margen(db: DB, f: Filtros, agrupar: Agrupar = Agrupar.campania, expresado_en: Moneda = Moneda.ARS,
           incluir_pendientes: bool = False):
    """Ingresos por ventas de granos menos gastos, por campaña, campo o lote (con rinde y margen por hectárea).
    Las ventas se filtran por fecha, campaña y campo; los gastos con los mismos filtros que el resto de reportes."""
    if agrupar not in (Agrupar.campania, Agrupar.campo, Agrupar.lote):
        raise HTTPException(422, "El margen se agrupa por campaña, campo o lote")
    gastos = {x.id: (x.clave, x.total) for x in _gastos(db, agrupar, f, expresado_en, incluir_pendientes)}

    col_id, tabla, nombre = {
        Agrupar.campania: (Venta.campania_id, Campania, Campania.nombre),
        Agrupar.campo: (Venta.campo_id, Campo, Campo.nombre),
        Agrupar.lote: (Venta.lote_id, Lote, func.concat(Campo.nombre, " / ", Lote.nombre)),
    }[agrupar]
    if expresado_en == Moneda.ARS:
        importe = Venta.total * Venta.cotizacion
    else:
        cot = (select(Cotizacion.valor).where(Cotizacion.moneda == "DOL", Cotizacion.fecha <= Venta.fecha)
               .order_by(Cotizacion.fecha.desc()).limit(1).correlate(Venta).scalar_subquery())
        importe = case((Venta.moneda == "DOL", Venta.total), else_=Venta.total * Venta.cotizacion / cot)
    stmt = select(col_id, nombre, func.sum(Venta.kilos), func.sum(importe)).select_from(Venta).outerjoin(
        tabla, col_id == tabla.id)
    if agrupar == Agrupar.lote:
        stmt = stmt.outerjoin(Campo, Lote.campo_id == Campo.id)
    for col, v in ((Venta.campania_id, f.campania_id), (Venta.campo_id, f.campo_id), (Venta.lote_id, f.lote_id)):
        if v is not None:
            stmt = stmt.where(col == v)
    if f.desde:
        stmt = stmt.where(Venta.fecha >= f.desde)
    if f.hasta:
        stmt = stmt.where(Venta.fecha <= f.hasta)
    ventas = {i: (n, k, t) for i, n, k, t in db.execute(stmt.group_by(col_id, nombre))}

    hectareas: dict = {}
    if agrupar == Agrupar.campo:
        hectareas = dict(db.execute(select(Campo.id, Campo.hectareas)).all())
    elif agrupar == Agrupar.lote:
        hectareas = dict(db.execute(select(Lote.id, Lote.hectareas)).all())

    filas = []
    for clave in set(gastos) | set(ventas):
        nombre_v, kilos, ingresos = ventas.get(clave, (None, Decimal(0), Decimal(0)))
        nombre_g, gasto = gastos.get(clave, (None, Decimal(0)))
        ingresos, kilos = _dec(ingresos), Decimal(kilos or 0)
        ha = hectareas.get(clave)
        m = ingresos - gasto
        filas.append(FilaMargen(
            id=clave, clave=nombre_v or nombre_g, hectareas=ha, kilos=kilos,
            rinde_kg_ha=(kilos / ha).quantize(CENTAVO) if ha and kilos else None,
            ingresos=ingresos, gastos=gasto, margen=m, margen_ha=(m / ha).quantize(CENTAVO) if ha else None,
        ))
    return sorted(filas, key=lambda x: (x.clave is None, x.clave or ""))


# --- Insumos -------------------------------------------------------------------


def _subtotal_item():
    return func.coalesce(FacturaItem.subtotal, FacturaItem.cantidad * FacturaItem.precio_unitario)


@router.get("/insumos", response_model=list[ResumenInsumo])
def insumos(db: DB, f: Filtros, incluir_pendientes: bool = False):
    """Por insumo: cantidad comprada, gasto en pesos, precio promedio ponderado y último precio."""
    s = signo()
    filtros = FiltrosFactura(**{**f.__dict__, "estado": _estados(incluir_pendientes)})
    base = aplicar(select(Factura.id), filtros)
    stmt = (
        select(Insumo.id, Insumo.nombre, Insumo.unidad,
               func.sum(FacturaItem.cantidad * s),
               func.sum(func.coalesce(_subtotal_item(), 0) * Factura.cotizacion * s),
               func.max(Factura.fecha_emision))
        .select_from(FacturaItem)
        .join(Factura, Factura.id == FacturaItem.factura_id)
        .join(Insumo, Insumo.id == FacturaItem.insumo_id)
        .where(Factura.id.in_(base))
        .group_by(Insumo.id).order_by(func.sum(func.coalesce(_subtotal_item(), 0) * Factura.cotizacion * s).desc())
    )
    filas = db.execute(stmt).all()

    # Último precio unitario (en pesos) de cada insumo
    ultimo = (
        select(FacturaItem.insumo_id, (FacturaItem.precio_unitario * Factura.cotizacion).label("precio"))
        .join(Factura, Factura.id == FacturaItem.factura_id)
        .where(Factura.id.in_(base), FacturaItem.insumo_id.is_not(None), FacturaItem.precio_unitario.is_not(None))
        .order_by(FacturaItem.insumo_id, Factura.fecha_emision.desc().nulls_last(), FacturaItem.id.desc())
        .distinct(FacturaItem.insumo_id)
    )
    ultimos = dict(db.execute(ultimo).all())
    return [
        ResumenInsumo(
            insumo_id=i, insumo=n, unidad=u, cantidad=c, total_pesos=_dec(t),
            precio_promedio=(Decimal(t) / Decimal(c)).quantize(CENTAVO) if c and t else None,
            ultimo_precio=_dec(ultimos[i]) if ultimos.get(i) is not None else None, ultima_compra=fe,
        )
        for i, n, u, c, t, fe in filas
    ]


@router.get("/insumos/{insumo_id}/precios", response_model=list[PrecioInsumo])
def precios_insumo(db: DB, insumo_id: int, f: Filtros, incluir_pendientes: bool = True):
    """Historial de compras de un insumo, para ver la evolución del precio."""
    filtros = FiltrosFactura(**{**f.__dict__, "estado": _estados(incluir_pendientes)})
    stmt = (
        select(Factura.id, Factura.fecha_emision, Proveedor.razon_social, FacturaItem.descripcion,
               FacturaItem.cantidad, FacturaItem.unidad, FacturaItem.precio_unitario, Factura.moneda,
               (FacturaItem.precio_unitario * Factura.cotizacion))
        .select_from(FacturaItem)
        .join(Factura, Factura.id == FacturaItem.factura_id)
        .outerjoin(Proveedor, Proveedor.id == Factura.proveedor_id)
        .where(FacturaItem.insumo_id == insumo_id)
        .order_by(Factura.fecha_emision.asc().nulls_last(), FacturaItem.id)
    )
    stmt = aplicar(stmt, filtros)
    return [
        PrecioInsumo(factura_id=fid, fecha=fe, proveedor=p, descripcion=d, cantidad=c, unidad=u,
                     precio_unitario=pu, moneda=m, precio_pesos=_dec(pp) if pp is not None else None)
        for fid, fe, p, d, c, u, pu, m, pp in db.execute(stmt)
    ]


# --- Dashboard -------------------------------------------------------------------


@router.get("/resumen", response_model=ResumenDashboard)
def resumen(db: DB, f: Filtros):
    """Datos para el dashboard principal."""
    por_mes = _gastos(db, Agrupar.mes, f)

    kilos = select(func.coalesce(func.sum(func.coalesce(CartaPorte.kilos_descargados, CartaPorte.kilos_netos)), 0)) \
        .where(CartaPorte.estado != EstadoCartaPorte.anulada)
    if f.desde:
        kilos = kilos.where(CartaPorte.fecha_carga >= f.desde)
    if f.hasta:
        kilos = kilos.where(CartaPorte.fecha_carga <= f.hasta)
    if f.campania_id:
        kilos = kilos.where(CartaPorte.campania_id == f.campania_id)

    return ResumenDashboard(
        total_gastos=sum((x.total for x in por_mes), Decimal(0)),
        cantidad_facturas=sum(x.cantidad for x in por_mes),
        pendientes_revision=db.scalar(
            select(func.count()).select_from(Factura).where(Factura.estado == EstadoFactura.pendiente_revision)
        ),
        kilos_despachados=db.scalar(kilos),
        gastos_por_mes=por_mes,
        gastos_por_categoria=_gastos(db, Agrupar.categoria, f),
        top_proveedores=_gastos(db, Agrupar.proveedor, f, limite=10),
    )

