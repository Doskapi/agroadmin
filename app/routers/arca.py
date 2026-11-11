"""Conciliación con "Mis Comprobantes Recibidos" de ARCA y verificación de comprobantes (WSCDC)."""

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, HTTPException, UploadFile
from sqlalchemy import and_, exists, func, select, tuple_
from sqlalchemy.dialects.postgresql import insert

from app import validar_archivo
from app.arca import mis_comprobantes, tareas, wscdc
from app.auditoria import auditar
from app.deps import DB, requiere
from app.models import ComprobanteArca, EstadoFactura, Factura, Usuario
from app.schemas import Conciliacion, Diferencia, FacturaOut, ResultadoImportacionArca

router = APIRouter(tags=["arca"])

CLAVE_F = (Factura.cuit_emisor, Factura.tipo_comprobante, Factura.punto_venta, Factura.numero)
CLAVE_A = (ComprobanteArca.cuit_emisor, ComprobanteArca.tipo_comprobante, ComprobanteArca.punto_venta,
           ComprobanteArca.numero)


@router.post("/arca/comprobantes-recibidos", response_model=ResultadoImportacionArca)
async def importar(db: DB, archivo: UploadFile, usuario: Usuario = requiere("facturas:escribir")):
    """Sube el CSV o Excel que se descarga de ARCA → Mis Comprobantes → Recibidos. Se puede subir varias veces:
    los comprobantes ya importados se actualizan."""
    data = await validar_archivo.leer_con_limite(archivo)
    try:
        filas = mis_comprobantes.leer(data, archivo.filename or "")
    except mis_comprobantes.ArchivoInvalido as e:
        raise HTTPException(422, str(e)) from None
    if not filas:
        raise HTTPException(422, "El archivo no tiene comprobantes")
    antes = db.scalar(select(func.count()).select_from(ComprobanteArca))
    valores = [f.__dict__ for f in {(f.cuit_emisor, f.tipo_comprobante, f.punto_venta, f.numero): f for f in filas}.values()]
    stmt = insert(ComprobanteArca).values(valores)
    db.execute(stmt.on_conflict_do_update(
        index_elements=["cuit_emisor", "tipo_comprobante", "punto_venta", "numero"],
        set_={k: stmt.excluded[k] for k in ("fecha", "razon_social", "total", "moneda", "cae")},
    ))
    nuevos = db.scalar(select(func.count()).select_from(ComprobanteArca)) - antes
    auditar(db, usuario.id, "arca_importado", None, None, archivo=archivo.filename, leidos=len(filas), nuevos=nuevos)
    db.commit()
    return ResultadoImportacionArca(leidos=len(filas), nuevos=nuevos, desde=min(f.fecha for f in filas),
                                    hasta=max(f.fecha for f in filas))


@router.get("/arca/conciliacion", response_model=Conciliacion, dependencies=[requiere("facturas:leer")])
def conciliacion(db: DB, desde: date | None = None, hasta: date | None = None):
    """Compara lo importado de ARCA con las facturas del sistema en el período (por defecto, todo lo importado)."""
    if desde is None or hasta is None:
        minimo, maximo = db.execute(select(func.min(ComprobanteArca.fecha), func.max(ComprobanteArca.fecha))).one()
        desde, hasta = desde or minimo, hasta or maximo
    if desde is None:
        return Conciliacion(desde=None, hasta=None, coinciden=0, faltan_cargar=[], no_estan_en_arca=[], diferencias=[])

    en_arca = and_(ComprobanteArca.fecha >= desde, ComprobanteArca.fecha <= hasta)
    vigente = Factura.estado.not_in([EstadoFactura.anulada])
    misma_clave = and_(*(a == b for a, b in zip(CLAVE_F, CLAVE_A, strict=True)))

    faltan = db.scalars(select(ComprobanteArca).where(en_arca, ~exists().where(misma_clave, vigente))
                        .order_by(ComprobanteArca.fecha)).all()
    no_estan = db.scalars(
        select(Factura).where(Factura.estado == EstadoFactura.confirmada, Factura.fecha_emision >= desde,
                              Factura.fecha_emision <= hasta, *(c.is_not(None) for c in CLAVE_F),
                              tuple_(*CLAVE_F).not_in(select(*CLAVE_A)))
        .order_by(Factura.fecha_emision)).all()
    pares = db.execute(select(Factura.id, Factura.total, ComprobanteArca).join(ComprobanteArca, misma_clave)
                       .where(en_arca, vigente)).all()
    diferencias = [Diferencia(factura_id=fid, arca=a, total_cargado=t) for fid, t, a in pares
                   if a.total is not None and t is not None and abs(a.total - t) > Decimal("1")]
    return Conciliacion(desde=desde, hasta=hasta, coinciden=len(pares) - len(diferencias), faltan_cargar=faltan,
                        no_estan_en_arca=no_estan, diferencias=diferencias)


@router.get("/arca/estado", dependencies=[requiere("facturas:leer")])
def estado() -> dict:
    return {"verificacion_configurada": wscdc.configurado(), "entorno": wscdc.settings.arca_entorno}


@router.post("/facturas/{factura_id}/verificar-arca", response_model=FacturaOut, status_code=202)
def verificar(db: DB, factura_id: int, usuario: Usuario = requiere("facturas:escribir")):
    """Pide (en segundo plano) la constatación del comprobante en ARCA."""
    factura = db.get(Factura, factura_id)
    if not factura:
        raise HTTPException(404, "Factura no encontrada")
    if not wscdc.configurado():
        raise HTTPException(422, "La verificación con ARCA no está configurada")
    if faltan := tareas.faltan_datos(factura):
        raise HTTPException(422, f"Faltan datos para verificar: {', '.join(faltan)}")
    tareas.encolar(db, factura)
    db.commit()
    return factura
