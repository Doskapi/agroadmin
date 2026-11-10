"""Catálogo de insumos y asignación de ítems de factura a insumos."""

from fastapi import APIRouter, HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app import insumos
from app.deps import DB, requiere
from app.models import FacturaItem, Insumo
from app.schemas import AsignarInsumo, FacturaItemOut, InsumoIn, InsumoOut, ItemSinInsumo

router = APIRouter(tags=["insumos"])


@router.get("/insumos", response_model=list[InsumoOut], dependencies=[requiere("catalogos:leer")])
def listar(db: DB):
    return db.scalars(select(Insumo).order_by(Insumo.nombre)).all()


def _guardar(db: DB, obj: Insumo) -> Insumo:
    db.add(obj)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Ya existe un insumo con ese nombre")
    db.refresh(obj)
    return obj


@router.post("/insumos", response_model=InsumoOut, status_code=201, dependencies=[requiere("catalogos:escribir")])
def crear(db: DB, data: InsumoIn):
    return _guardar(db, Insumo(**data.model_dump()))


@router.put("/insumos/{insumo_id}", response_model=InsumoOut, dependencies=[requiere("catalogos:escribir")])
def editar(db: DB, insumo_id: int, data: InsumoIn):
    obj = db.get(Insumo, insumo_id)
    if not obj:
        raise HTTPException(404, "Insumo no encontrado")
    for k, v in data.model_dump().items():
        setattr(obj, k, v)
    return _guardar(db, obj)


@router.get("/insumos/sin-asignar", response_model=list[ItemSinInsumo], dependencies=[requiere("catalogos:leer")])
def items_sin_asignar(db: DB, limit: int = 200):
    """Descripciones de ítems que todavía no tienen insumo, de la más repetida a la menos."""
    filas = db.execute(
        select(FacturaItem.descripcion, func.min(FacturaItem.id), func.count(), func.max(FacturaItem.unidad))
        .where(FacturaItem.insumo_id.is_(None))
        .group_by(FacturaItem.descripcion)
        .order_by(func.count().desc(), FacturaItem.descripcion)
        .limit(min(limit, 1000))
    ).all()
    return [ItemSinInsumo(descripcion=d, ejemplo_item_id=i, cantidad_items=n, unidad=u) for d, i, n, u in filas]


@router.put("/facturas/items/{item_id}/insumo", response_model=FacturaItemOut,
            dependencies=[requiere("catalogos:escribir")])
def asignar(db: DB, item_id: int, data: AsignarInsumo):
    """Asigna un insumo a un ítem. Con `recordar`, se aplica a todos los ítems con la misma descripción
    (también a los que se carguen después). Funciona aunque la factura esté confirmada: no cambia importes."""
    item = db.get(FacturaItem, item_id)
    if not item:
        raise HTTPException(404, "Ítem no encontrado")
    if data.insumo_id is not None and not db.get(Insumo, data.insumo_id):
        raise HTTPException(422, "El insumo no existe")
    item.insumo_id = data.insumo_id
    if data.recordar:
        insumos.recordar(db, item.descripcion, data.insumo_id)
    db.commit()
    db.refresh(item)
    return item
