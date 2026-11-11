from datetime import date

from fastapi import APIRouter, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app import importacion, trabajos, validar_archivo
from app.auditoria import auditar
from app.deps import DB, requiere
from app.extraccion import carta_porte as _extraccion  # noqa: F401  (registra el trabajo)
from app.extraccion import ia
from app.models import Archivo, CartaPorte, EstadoCartaPorte, Usuario
from app.schemas import CartaPorteIn, CartaPorteOut

router = APIRouter(prefix="/cartas-porte", tags=["cartas de porte"])


def _completar_kilos(cp: CartaPorte) -> None:
    if cp.kilos_netos is None and cp.kilos_brutos is not None and cp.kilos_tara is not None:
        cp.kilos_netos = cp.kilos_brutos - cp.kilos_tara


def _commit(db: DB, cp: CartaPorte):
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Ya existe una carta de porte con ese CTG") from None
    db.refresh(cp)


@router.get("", response_model=list[CartaPorteOut], dependencies=[requiere("cartas_porte:leer")])
def listar(
    db: DB,
    campania_id: int | None = None,
    campo_id: int | None = None,
    grano: str | None = None,
    estado: EstadoCartaPorte | None = None,
    desde: date | None = None,
    hasta: date | None = None,
    limit: int = 50,
    offset: int = 0,
):
    stmt = select(CartaPorte).order_by(CartaPorte.fecha_carga.desc().nulls_first(), CartaPorte.id.desc())
    for col, valor in {CartaPorte.campania_id: campania_id, CartaPorte.campo_id: campo_id,
                       CartaPorte.grano: grano, CartaPorte.estado: estado}.items():
        if valor is not None:
            stmt = stmt.where(col == valor)
    if desde:
        stmt = stmt.where(CartaPorte.fecha_carga >= desde)
    if hasta:
        stmt = stmt.where(CartaPorte.fecha_carga <= hasta)
    return db.scalars(stmt.limit(min(limit, 500)).offset(offset)).all()


@router.post("/importar", response_model=CartaPorteOut, status_code=202)
async def importar(db: DB, archivo: UploadFile, usuario: Usuario = requiere("cartas_porte:escribir")):
    """Sube el PDF o una foto de una carta de porte electrónica. La lee Claude en segundo plano
    (requiere ANTHROPIC_API_KEY); queda en `borrador` para revisarla."""
    if not ia.disponible():
        raise HTTPException(422, "Para leer cartas de porte hace falta configurar ANTHROPIC_API_KEY")
    data = await validar_archivo.leer_con_limite(archivo)
    arch = importacion.guardar_archivo(db, data, archivo.filename, usuario.id)
    if previa := db.scalar(select(CartaPorte).where(CartaPorte.archivo_id == arch.id)):
        raise HTTPException(409, f"Este archivo ya fue importado como carta de porte #{previa.id}")
    cp = CartaPorte(estado=EstadoCartaPorte.procesando, archivo_id=arch.id, creado_por_id=usuario.id)
    db.add(cp)
    db.flush()
    trabajos.encolar(db, "procesar_carta_porte", {"carta_porte_id": cp.id})
    auditar(db, usuario.id, "carta_porte_importada", "carta_porte", cp.id, archivo=arch.nombre_original)
    db.commit()
    db.refresh(cp)
    return cp


@router.get("/{cp_id}/archivo", dependencies=[requiere("cartas_porte:leer")])
def descargar_archivo(db: DB, cp_id: int):
    cp = obtener(db, cp_id)
    arch = db.get(Archivo, cp.archivo_id) if cp.archivo_id else None
    if not arch:
        raise HTTPException(404, "La carta de porte no tiene archivo")
    return FileResponse(arch.ruta, media_type=arch.content_type, filename=arch.nombre_original)


@router.get("/{cp_id}", response_model=CartaPorteOut, dependencies=[requiere("cartas_porte:leer")])
def obtener(db: DB, cp_id: int):
    cp = db.get(CartaPorte, cp_id)
    if not cp:
        raise HTTPException(404, "Carta de porte no encontrada")
    return cp


@router.post("", response_model=CartaPorteOut, status_code=201)
def crear(db: DB, data: CartaPorteIn, usuario: Usuario = requiere("cartas_porte:escribir")):
    cp = CartaPorte(**data.model_dump(), creado_por_id=usuario.id)
    _completar_kilos(cp)
    db.add(cp)
    _commit(db, cp)
    return cp


@router.put("/{cp_id}", response_model=CartaPorteOut, dependencies=[requiere("cartas_porte:escribir")])
def editar(db: DB, cp_id: int, data: CartaPorteIn):
    cp = obtener(db, cp_id)
    if cp.estado == EstadoCartaPorte.anulada:
        raise HTTPException(409, "La carta de porte está anulada")
    if cp.estado == EstadoCartaPorte.procesando:
        raise HTTPException(409, "La carta de porte se está leyendo; esperá unos segundos")
    for k, v in data.model_dump().items():
        setattr(cp, k, v)
    _completar_kilos(cp)
    _commit(db, cp)
    return cp
