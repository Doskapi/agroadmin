"""Proveedores, campos, lotes, campañas y categorías de gasto."""

from fastapi import APIRouter, HTTPException
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError

from app.deps import DB, requiere
from app.models import Campania, Campo, Categoria, Lote, Proveedor
from app.schemas import (
    CampaniaIn,
    CampaniaOut,
    CampoIn,
    CampoOut,
    CategoriaIn,
    CategoriaOut,
    LoteIn,
    LoteOut,
    ProveedorIn,
    ProveedorOut,
)

router = APIRouter(tags=["catálogos"])
LEER = [requiere("catalogos:leer")]
ESCRIBIR = [requiere("catalogos:escribir")]


def _guardar(db: DB, obj):
    db.add(obj)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Ya existe un registro con esos datos")
    db.refresh(obj)
    return obj


def _obtener(db: DB, modelo, id_: int):
    obj = db.get(modelo, id_)
    if not obj:
        raise HTTPException(404, f"{modelo.__name__} no encontrado")
    return obj


# --- Proveedores ---


@router.get("/proveedores", response_model=list[ProveedorOut], dependencies=LEER)
def listar_proveedores(db: DB, q: str | None = None):
    stmt = select(Proveedor).order_by(Proveedor.razon_social)
    if q:
        stmt = stmt.where(or_(Proveedor.razon_social.ilike(f"%{q}%"), Proveedor.cuit.contains(q)))
    return db.scalars(stmt).all()


@router.post("/proveedores", response_model=ProveedorOut, status_code=201, dependencies=ESCRIBIR)
def crear_proveedor(db: DB, data: ProveedorIn):
    return _guardar(db, Proveedor(**data.model_dump()))


@router.put("/proveedores/{id_}", response_model=ProveedorOut, dependencies=ESCRIBIR)
def editar_proveedor(db: DB, id_: int, data: ProveedorIn):
    obj = _obtener(db, Proveedor, id_)
    for k, v in data.model_dump().items():
        setattr(obj, k, v)
    return _guardar(db, obj)


# --- Campos y lotes ---


@router.get("/campos", response_model=list[CampoOut], dependencies=LEER)
def listar_campos(db: DB):
    return db.scalars(select(Campo).order_by(Campo.nombre)).all()


@router.post("/campos", response_model=CampoOut, status_code=201, dependencies=ESCRIBIR)
def crear_campo(db: DB, data: CampoIn):
    return _guardar(db, Campo(**data.model_dump()))


@router.put("/campos/{id_}", response_model=CampoOut, dependencies=ESCRIBIR)
def editar_campo(db: DB, id_: int, data: CampoIn):
    obj = _obtener(db, Campo, id_)
    for k, v in data.model_dump().items():
        setattr(obj, k, v)
    return _guardar(db, obj)


@router.post("/campos/{campo_id}/lotes", response_model=LoteOut, status_code=201, dependencies=ESCRIBIR)
def crear_lote(db: DB, campo_id: int, data: LoteIn):
    _obtener(db, Campo, campo_id)
    return _guardar(db, Lote(campo_id=campo_id, **data.model_dump()))


# --- Campañas ---


@router.get("/campanias", response_model=list[CampaniaOut], dependencies=LEER)
def listar_campanias(db: DB):
    return db.scalars(select(Campania).order_by(Campania.fecha_inicio.desc())).all()


@router.post("/campanias", response_model=CampaniaOut, status_code=201, dependencies=ESCRIBIR)
def crear_campania(db: DB, data: CampaniaIn):
    if data.fecha_fin < data.fecha_inicio:
        raise HTTPException(422, "La fecha de fin es anterior a la de inicio")
    return _guardar(db, Campania(**data.model_dump()))


# --- Categorías ---


@router.get("/categorias", response_model=list[CategoriaOut], dependencies=LEER)
def listar_categorias(db: DB):
    return db.scalars(select(Categoria).order_by(Categoria.nombre)).all()


@router.post("/categorias", response_model=CategoriaOut, status_code=201, dependencies=ESCRIBIR)
def crear_categoria(db: DB, data: CategoriaIn):
    return _guardar(db, Categoria(nombre=data.nombre.strip().lower()))
