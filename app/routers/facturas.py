import io
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from fastapi.responses import FileResponse, StreamingResponse
from openpyxl import Workbook
from openpyxl.styles import Font
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app import importacion, insumos, validar_archivo
from app.arca import tareas as arca_tareas
from app.auditoria import auditar, diferencias
from app.deps import DB, UsuarioActual, requiere
from app.extraccion import pipeline
from app.filtros import NOTAS_CREDITO, FiltrosFactura, aplicar, filtros_query, monto_pesos
from app.models import (
    Archivo,
    Campania,
    Campo,
    Categoria,
    EstadoFactura,
    Factura,
    FacturaImputacion,
    FacturaItem,
    Insumo,
    Lote,
    Proveedor,
    Usuario,
)
from app.schemas import (
    AccionMasiva,
    AnularIn,
    CatalogoFacturas,
    FacturaIn,
    FacturaOut,
    FacturaResumen,
    FacturaUpdate,
    ImputacionIn,
    ResultadoAccionMasiva,
)

router = APIRouter(prefix="/facturas", tags=["facturas"])

Filtros = Annotated[FiltrosFactura, Depends(filtros_query)]
NO_EDITABLES = (EstadoFactura.confirmada, EstadoFactura.anulada)

ORDEN = {
    "fecha": Factura.fecha_emision,
    "total": Factura.total * Factura.cotizacion,
    "proveedor": Proveedor.razon_social,
    "numero": Factura.numero,
    "estado": Factura.estado,
    "id": Factura.id,
}


def _obtener(db: DB, factura_id: int) -> Factura:
    factura = db.get(Factura, factura_id)
    if not factura:
        raise HTTPException(404, "Factura no encontrada")
    return factura


def _commit(db: DB, factura: Factura):
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "Ya existe un comprobante con ese CUIT, tipo, punto de venta y número") from None
    db.refresh(factura)


def _imputaciones(db: DB, datos: list[ImputacionIn]) -> list[FacturaImputacion]:
    """Valida el reparto entre campos/lotes: porcentajes que suman 100 y lotes que pertenecen a su campo."""
    if not datos:
        return []
    suma = sum((i.porcentaje for i in datos), Decimal(0))
    if abs(suma - 100) > Decimal("0.01"):
        raise HTTPException(422, f"Los porcentajes del reparto suman {suma}, tienen que sumar 100")
    for i in datos:
        if not db.get(Campo, i.campo_id):
            raise HTTPException(422, f"El campo {i.campo_id} no existe")
        if i.lote_id is not None:
            lote = db.get(Lote, i.lote_id)
            if not lote or lote.campo_id != i.campo_id:
                raise HTTPException(422, f"El lote {i.lote_id} no pertenece al campo {i.campo_id}")
    return [FacturaImputacion(**i.model_dump()) for i in datos]


def _items(db: DB, datos: list[dict]) -> list[FacturaItem]:
    items = [FacturaItem(**i) for i in datos]
    insumos.autoasignar(db, items)
    return items


def _categoria_del_proveedor(db: DB, factura: Factura) -> None:
    if factura.categoria_id is None and factura.proveedor_id:
        prov = db.get(Proveedor, factura.proveedor_id)
        if prov and prov.categoria_id:
            factura.categoria_id = prov.categoria_id


def _catalogo_stmt(f: FiltrosFactura, orden: str, dir: str):
    stmt = aplicar(select(Factura).outerjoin(Proveedor, Factura.proveedor_id == Proveedor.id), f)
    col = ORDEN[orden]
    col = col.asc().nulls_last() if dir == "asc" else col.desc().nulls_last()
    return stmt.order_by(col, Factura.id.desc())


# --- Listados ----------------------------------------------------------------


@router.get("", response_model=list[FacturaResumen], dependencies=[requiere("facturas:leer")])
def listar(db: DB, f: Filtros, limit: int = 50, offset: int = 0):
    """Listado simple (sin totales). Para pantallas usar `/facturas/catalogo`."""
    stmt = _catalogo_stmt(f, "fecha", "desc")
    return db.scalars(stmt.limit(min(limit, 500)).offset(offset)).all()


@router.get("/catalogo", response_model=CatalogoFacturas, dependencies=[requiere("facturas:leer")])
def catalogo(
    db: DB,
    f: Filtros,
    orden: Literal["fecha", "total", "proveedor", "numero", "estado", "id"] = "fecha",
    dir: Literal["asc", "desc"] = "desc",
    limit: int = 50,
    offset: int = 0,
):
    """Búsqueda de facturas con filtros, orden y paginado. Devuelve además la cantidad total
    y la suma en pesos (notas de crédito restan) de todo lo filtrado, no solo de la página."""
    base = aplicar(select(Factura.id).outerjoin(Proveedor, Factura.proveedor_id == Proveedor.id), f).subquery()
    total, suma = db.execute(
        select(func.count(), func.coalesce(func.sum(monto_pesos()), 0)).select_from(Factura)
        .where(Factura.id.in_(select(base.c.id)))
    ).one()
    items = db.scalars(_catalogo_stmt(f, orden, dir).limit(min(limit, 500)).offset(offset)).all()
    return CatalogoFacturas(items=items, total=total, suma_pesos=Decimal(suma).quantize(Decimal("0.01")))


@router.get("/catalogo.xlsx", dependencies=[requiere("facturas:leer")])
def catalogo_excel(
    db: DB,
    f: Filtros,
    orden: Literal["fecha", "total", "proveedor", "numero", "estado", "id"] = "fecha",
    dir: Literal["asc", "desc"] = "asc",
):
    """Detalle de las facturas filtradas: hoja de comprobantes (sirve de libro IVA compras) y hoja de ítems.
    En las notas de crédito los importes van en negativo."""
    facturas = db.scalars(_catalogo_stmt(f, orden, dir).limit(20000)).unique().all()
    nombres = {
        "categoria": dict(db.execute(select(Categoria.id, Categoria.nombre)).all()),
        "campania": dict(db.execute(select(Campania.id, Campania.nombre)).all()),
        "campo": dict(db.execute(select(Campo.id, Campo.nombre)).all()),
        "lote": dict(db.execute(select(Lote.id, Lote.nombre)).all()),
        "insumo": dict(db.execute(select(Insumo.id, Insumo.nombre)).all()),
    }

    wb = Workbook()
    ws = wb.active
    ws.title = "Comprobantes"
    encabezado = ["ID", "Fecha", "Tipo", "Punto de venta", "Número", "CUIT", "Proveedor", "Condición IVA", "Moneda",
                  "Cotización", "Neto gravado", "No gravado", "IVA", "Percepciones", "Total", "Total ARS", "Rubro",
                  "Campaña", "Campo", "Lote", "Estado", "CAE", "Vencimiento"]
    ws.append(encabezado)
    items_ws = wb.create_sheet("Ítems")
    items_ws.append(["Factura ID", "Fecha", "Proveedor", "Comprobante", "Descripción", "Insumo", "Cantidad", "Unidad",
                     "Precio unitario", "Alícuota IVA", "Subtotal", "Moneda"])

    def n(v, s=1):
        return None if v is None else float(v) * s

    for fa in facturas:
        s = -1 if fa.tipo_comprobante in NOTAS_CREDITO else 1
        prov = fa.proveedor
        if fa.imputaciones:
            campo = " + ".join(
                f"{nombres['campo'].get(i.campo_id)} {format(i.porcentaje.normalize(), 'f')}%" for i in fa.imputaciones)
            lote = " + ".join(nombres["lote"].get(i.lote_id, "") for i in fa.imputaciones if i.lote_id) or None
        else:
            campo, lote = nombres["campo"].get(fa.campo_id), nombres["lote"].get(fa.lote_id)
        ws.append([
            fa.id, fa.fecha_emision, fa.tipo_comprobante, fa.punto_venta, fa.numero, fa.cuit_emisor,
            prov.razon_social if prov else None, prov.condicion_iva if prov else None, fa.moneda, n(fa.cotizacion),
            n(fa.neto_gravado, s), n(fa.no_gravado, s), n(fa.iva, s), n(fa.percepciones, s), n(fa.total, s),
            n(fa.total * fa.cotizacion, s) if fa.total is not None else None,
            nombres["categoria"].get(fa.categoria_id), nombres["campania"].get(fa.campania_id), campo, lote,
            fa.estado.value, fa.cae, fa.fecha_vencimiento,
        ])
        comp = f"{fa.tipo_comprobante or ''} {fa.punto_venta or ''}-{fa.numero or ''}".strip()
        for it in fa.items:
            items_ws.append([fa.id, fa.fecha_emision, prov.razon_social if prov else None, comp, it.descripcion,
                             nombres["insumo"].get(it.insumo_id), n(it.cantidad), it.unidad,
                             n(it.precio_unitario), n(it.alicuota_iva), n(it.subtotal, s), fa.moneda])

    for hoja, anchos in ((ws, {"G": 36, "Q": 16}), (items_ws, {"C": 30, "E": 50, "F": 26})):
        for celda in hoja[1]:
            celda.font = Font(bold=True)
        hoja.freeze_panes = "A2"
        for col, ancho in anchos.items():
            hoja.column_dimensions[col].width = ancho
        for fila in hoja.iter_rows(min_row=2):
            for c in fila:
                if isinstance(c.value, float):
                    c.number_format = "#,##0.00"
                elif hasattr(c.value, "isoformat"):
                    c.number_format = "DD/MM/YYYY"

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return StreamingResponse(
        buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="facturas.xlsx"'},
    )


# --- Acciones masivas --------------------------------------------------------


@router.post("/acciones", response_model=ResultadoAccionMasiva)
def accion_masiva(db: DB, data: AccionMasiva, usuario: UsuarioActual):
    """Imputa (rubro/campaña/campo/lote) o confirma varias facturas a la vez.
    Cada factura se procesa por separado: las que no se pueden quedan en `errores` con el motivo."""
    permiso = "facturas:escribir" if data.accion == "imputar" else "facturas:confirmar"
    if permiso not in usuario.permisos:
        raise HTTPException(status.HTTP_403_FORBIDDEN, f"Falta el permiso '{permiso}'")

    cambios = data.model_dump(include={"categoria_id", "campania_id", "campo_id", "lote_id"}, exclude_unset=True)
    if data.accion == "imputar":
        if not cambios:
            raise HTTPException(422, "Indicá al menos un rubro, campaña, campo o lote")
        if cambios.get("lote_id") is not None:
            lote = db.get(Lote, cambios["lote_id"])
            if not lote or ("campo_id" in cambios and lote.campo_id != cambios["campo_id"]):
                raise HTTPException(422, "El lote no pertenece al campo elegido")
            cambios["campo_id"] = lote.campo_id
        elif "campo_id" in cambios:
            cambios["lote_id"] = None

    ok, errores = [], {}
    for fid in dict.fromkeys(data.ids):
        factura = db.get(Factura, fid)
        if not factura:
            errores[fid] = "No existe"
            continue
        if data.accion == "imputar":
            if factura.estado in NO_EDITABLES or factura.estado == EstadoFactura.procesando:
                errores[fid] = f"Está {factura.estado.value}"
                continue
            if dif := diferencias(factura, cambios):
                auditar(db, usuario.id, "factura_editada", "factura", fid, cambios=dif, masiva=True)
            for k, v in cambios.items():
                setattr(factura, k, v)
            if "campo_id" in cambios:
                factura.imputaciones = []
        else:
            if motivo := _no_confirmable(factura):
                errores[fid] = motivo
                continue
            factura.estado = EstadoFactura.confirmada
            auditar(db, usuario.id, "factura_confirmada", "factura", fid, masiva=True)
            arca_tareas.encolar(db, factura)
        ok.append(fid)
    db.commit()
    return ResultadoAccionMasiva(ok=ok, errores=errores)


# --- Una factura -------------------------------------------------------------


@router.get("/{factura_id}", response_model=FacturaOut, dependencies=[requiere("facturas:leer")])
def obtener(db: DB, factura_id: int):
    return _obtener(db, factura_id)


@router.post("", response_model=FacturaOut, status_code=201)
def crear_manual(db: DB, data: FacturaIn, usuario: Usuario = requiere("facturas:escribir")):
    factura = Factura(**data.model_dump(exclude={"items", "imputaciones"}), creado_por_id=usuario.id,
                      estado=EstadoFactura.pendiente_revision)
    factura.items = _items(db, [i.model_dump() for i in data.items])
    factura.imputaciones = _imputaciones(db, data.imputaciones)
    _categoria_del_proveedor(db, factura)
    db.add(factura)
    db.flush()
    auditar(db, usuario.id, "factura_creada", "factura", factura.id, origen="manual")
    _commit(db, factura)
    return factura


@router.post("/importar", response_model=FacturaOut, status_code=202)
async def importar(db: DB, archivo: UploadFile, usuario: Usuario = requiere("facturas:escribir")):
    """Sube un PDF o imagen de factura. La lectura la hace el worker en segundo plano:
    consultar `GET /facturas/{id}` hasta que el estado deje de ser `procesando`."""
    data = await validar_archivo.leer_con_limite(archivo)
    factura = importacion.importar_factura(db, data, archivo.filename, usuario.id)
    db.commit()
    return factura


@router.post("/{factura_id}/reprocesar", response_model=FacturaOut, status_code=202)
def reprocesar(db: DB, factura_id: int, usuario: Usuario = requiere("facturas:escribir")):
    factura = _obtener(db, factura_id)
    if not factura.archivo_id:
        raise HTTPException(422, "La factura no tiene archivo asociado")
    if factura.estado == EstadoFactura.confirmada:
        raise HTTPException(409, "No se puede reprocesar una factura confirmada")
    factura.estado = EstadoFactura.procesando
    auditar(db, usuario.id, "factura_reprocesada", "factura", factura.id)
    pipeline.encolar(db, factura)
    db.commit()
    return factura


@router.patch("/{factura_id}", response_model=FacturaOut)
def editar(db: DB, factura_id: int, data: FacturaUpdate, usuario: Usuario = requiere("facturas:escribir")):
    factura = _obtener(db, factura_id)
    if factura.estado in NO_EDITABLES:
        raise HTTPException(409, f"La factura está {factura.estado.value} y no se puede editar")
    cambios = data.model_dump(exclude_unset=True)
    items = cambios.pop("items", None)
    imputaciones = cambios.pop("imputaciones", None)
    dif = diferencias(factura, cambios)
    if items is not None and len(items) != len(factura.items):
        dif["items"] = [len(factura.items), len(items)]
    if imputaciones is not None:
        antes = [[i.campo_id, i.lote_id, str(i.porcentaje.normalize())] for i in factura.imputaciones]
        despues = [[i.campo_id, i.lote_id, str(i.porcentaje.normalize())] for i in data.imputaciones]
        if antes != despues:
            dif["reparto"] = [antes, despues]
    if dif:
        auditar(db, usuario.id, "factura_editada", "factura", factura.id, cambios=dif)
    for k, v in cambios.items():
        setattr(factura, k, v)
    if items is not None:
        factura.items = _items(db, items)
    if imputaciones is not None:
        factura.imputaciones = _imputaciones(db, data.imputaciones)
    if "proveedor_id" in cambios:
        _categoria_del_proveedor(db, factura)
    if factura.estado == EstadoFactura.error:
        factura.estado = EstadoFactura.pendiente_revision
    _commit(db, factura)
    return factura


def _no_confirmable(factura: Factura) -> str | None:
    if factura.estado != EstadoFactura.pendiente_revision:
        return f"Solo se confirman facturas pendientes de revisión (estado actual: {factura.estado.value})"
    faltan = [c for c in ("proveedor_id", "fecha_emision", "total") if getattr(factura, c) is None]
    if faltan:
        return f"Faltan datos para confirmar: {', '.join(faltan)}"
    return None


@router.post("/{factura_id}/confirmar", response_model=FacturaOut)
def confirmar(db: DB, factura_id: int, usuario: Usuario = requiere("facturas:confirmar")):
    factura = _obtener(db, factura_id)
    if motivo := _no_confirmable(factura):
        raise HTTPException(409 if factura.estado != EstadoFactura.pendiente_revision else 422, motivo)
    factura.estado = EstadoFactura.confirmada
    auditar(db, usuario.id, "factura_confirmada", "factura", factura.id)
    arca_tareas.encolar(db, factura)
    db.commit()
    return factura


@router.post("/{factura_id}/anular", response_model=FacturaOut)
def anular(db: DB, factura_id: int, data: AnularIn, usuario: Usuario = requiere("facturas:confirmar")):
    """Anula la factura (deja de contar en los reportes). El motivo queda en la auditoría."""
    factura = _obtener(db, factura_id)
    if factura.estado == EstadoFactura.anulada:
        raise HTTPException(409, "La factura ya está anulada")
    auditar(db, usuario.id, "factura_anulada", "factura", factura.id, motivo=data.motivo,
            estado_anterior=factura.estado)
    factura.estado = EstadoFactura.anulada
    db.commit()
    return factura


@router.get("/{factura_id}/archivo", dependencies=[requiere("facturas:leer")])
def descargar_archivo(db: DB, factura_id: int):
    factura = _obtener(db, factura_id)
    archivo = db.get(Archivo, factura.archivo_id) if factura.archivo_id else None
    if not archivo:
        raise HTTPException(404, "La factura no tiene archivo")
    return FileResponse(archivo.ruta, media_type=archivo.content_type, filename=archivo.nombre_original)
