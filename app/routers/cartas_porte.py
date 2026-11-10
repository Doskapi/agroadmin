from datetime import date

from fastapi import APIRouter, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.deps import DB, requiere
from app.models import CartaPorte, EstadoCartaPorte, Usuario
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
    stmt = select(CartaPorte).order_by(CartaPorte.fecha_carga.desc(), CartaPorte.id.desc())
    for col, valor in {CartaPorte.campania_id: campania_id, CartaPorte.campo_id: campo_id,
                       CartaPorte.grano: grano, CartaPorte.estado: estado}.items():
        if valor is not None:
            stmt = stmt.where(col == valor)
    if desde:
        stmt = stmt.where(CartaPorte.fecha_carga >= desde)
    if hasta:
        stmt = stmt.where(CartaPorte.fecha_carga <= hasta)
    return db.scalars(stmt.limit(min(limit, 500)).offset(offset)).all()


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
    for k, v in data.model_dump().items():
        setattr(cp, k, v)
    _completar_kilos(cp)
    _commit(db, cp)
    return cp
