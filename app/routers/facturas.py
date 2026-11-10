from datetime import date

from fastapi import APIRouter, BackgroundTasks, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app import storage, validar_archivo
from app.deps import DB, requiere
from app.extraccion import pipeline
from app.models import Archivo, EstadoFactura, Factura, FacturaItem, Usuario
from app.schemas import FacturaIn, FacturaOut, FacturaResumen, FacturaUpdate

router = APIRouter(prefix="/facturas", tags=["facturas"])


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
        raise HTTPException(status.HTTP_409_CONFLICT, "Ya existe un comprobante con ese CUIT, tipo, punto de venta y número")
    db.refresh(factura)


@router.get("", response_model=list[FacturaResumen], dependencies=[requiere("facturas:leer")])
def listar(
    db: DB,
    estado: EstadoFactura | None = None,
    proveedor_id: int | None = None,
    campania_id: int | None = None,
    campo_id: int | None = None,
    categoria_id: int | None = None,
    desde: date | None = None,
    hasta: date | None = None,
    limit: int = 50,
    offset: int = 0,
):
    stmt = select(Factura).order_by(Factura.fecha_emision.desc().nulls_first(), Factura.id.desc())
    filtros = {
        Factura.estado: estado, Factura.proveedor_id: proveedor_id, Factura.campania_id: campania_id,
        Factura.campo_id: campo_id, Factura.categoria_id: categoria_id,
    }
    for col, valor in filtros.items():
        if valor is not None:
            stmt = stmt.where(col == valor)
    if desde:
        stmt = stmt.where(Factura.fecha_emision >= desde)
    if hasta:
        stmt = stmt.where(Factura.fecha_emision <= hasta)
    return db.scalars(stmt.limit(min(limit, 500)).offset(offset)).all()


@router.get("/{factura_id}", response_model=FacturaOut, dependencies=[requiere("facturas:leer")])
def obtener(db: DB, factura_id: int):
    return _obtener(db, factura_id)


@router.post("", response_model=FacturaOut, status_code=201)
def crear_manual(db: DB, data: FacturaIn, usuario: Usuario = requiere("facturas:escribir")):
    factura = Factura(**data.model_dump(exclude={"items"}), creado_por_id=usuario.id,
                      estado=EstadoFactura.pendiente_revision)
    factura.items = [FacturaItem(**i.model_dump()) for i in data.items]
    db.add(factura)
    _commit(db, factura)
    return factura


@router.post("/importar", response_model=FacturaOut, status_code=202)
async def importar(
    db: DB, archivo: UploadFile, background: BackgroundTasks, usuario: Usuario = requiere("facturas:escribir")
):
    """Sube un PDF o imagen de factura. La extracción corre en segundo plano:
    consultar `GET /facturas/{id}` hasta que el estado deje de ser `procesando`."""
    data = await validar_archivo.leer_con_limite(archivo)
    content_type = validar_archivo.validar_factura(data)  # tipo real, no el que declara el navegador

    digest = storage.sha256(data)
    existente = db.scalar(select(Archivo).where(Archivo.sha256 == digest))
    if existente:
        previa = db.scalar(select(Factura).where(Factura.archivo_id == existente.id))
        if previa:
            raise HTTPException(409, f"Este archivo ya fue importado como factura #{previa.id}")
    else:
        existente = Archivo(
            nombre_original=archivo.filename or "sin_nombre", content_type=content_type,
            ruta=storage.guardar(data, content_type), sha256=digest, tamanio=len(data), subido_por_id=usuario.id,
        )
        db.add(existente)
        db.flush()

    factura = Factura(estado=EstadoFactura.procesando, archivo_id=existente.id, creado_por_id=usuario.id)
    db.add(factura)
    db.commit()
    background.add_task(pipeline.procesar_en_segundo_plano, factura.id)
    return factura


@router.post("/{factura_id}/reprocesar", response_model=FacturaOut, status_code=202,
             dependencies=[requiere("facturas:escribir")])
def reprocesar(db: DB, factura_id: int, background: BackgroundTasks):
    factura = _obtener(db, factura_id)
    if not factura.archivo_id:
        raise HTTPException(422, "La factura no tiene archivo asociado")
    if factura.estado == EstadoFactura.confirmada:
        raise HTTPException(409, "No se puede reprocesar una factura confirmada")
    factura.estado = EstadoFactura.procesando
    db.commit()
    background.add_task(pipeline.procesar_en_segundo_plano, factura.id)
    return factura


@router.patch("/{factura_id}", response_model=FacturaOut, dependencies=[requiere("facturas:escribir")])
def editar(db: DB, factura_id: int, data: FacturaUpdate):
    factura = _obtener(db, factura_id)
    if factura.estado in (EstadoFactura.confirmada, EstadoFactura.anulada):
        raise HTTPException(409, f"La factura está {factura.estado.value} y no se puede editar")
    cambios = data.model_dump(exclude_unset=True)
    items = cambios.pop("items", None)
    for k, v in cambios.items():
        setattr(factura, k, v)
    if items is not None:
        factura.items = [FacturaItem(**i) for i in items]
    if factura.estado == EstadoFactura.error:
        factura.estado = EstadoFactura.pendiente_revision
    _commit(db, factura)
    return factura


@router.post("/{factura_id}/confirmar", response_model=FacturaOut, dependencies=[requiere("facturas:confirmar")])
def confirmar(db: DB, factura_id: int):
    factura = _obtener(db, factura_id)
    if factura.estado != EstadoFactura.pendiente_revision:
        raise HTTPException(409, f"Solo se confirman facturas pendientes de revisión (estado actual: {factura.estado.value})")
    faltan = [c for c in ("proveedor_id", "fecha_emision", "total") if getattr(factura, c) is None]
    if faltan:
        raise HTTPException(422, f"Faltan datos para confirmar: {', '.join(faltan)}")
    factura.estado = EstadoFactura.confirmada
    db.commit()
    return factura


@router.post("/{factura_id}/anular", response_model=FacturaOut, dependencies=[requiere("facturas:confirmar")])
def anular(db: DB, factura_id: int):
    factura = _obtener(db, factura_id)
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
