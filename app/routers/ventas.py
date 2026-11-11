"""Ventas de granos (liquidaciones)."""

from datetime import date

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app.auditoria import auditar, diferencias
from app.deps import DB, requiere
from app.models import Lote, Usuario, Venta
from app.schemas import VentaIn, VentaOut

router = APIRouter(prefix="/ventas", tags=["ventas"])


def _validar(db: DB, data: VentaIn) -> None:
    if data.lote_id is not None:
        lote = db.get(Lote, data.lote_id)
        if not lote or (data.campo_id is not None and lote.campo_id != data.campo_id):
            raise HTTPException(422, "El lote no pertenece al campo elegido")
        data.campo_id = lote.campo_id


@router.get("", response_model=list[VentaOut], dependencies=[requiere("ventas:leer")])
def listar(db: DB, campania_id: int | None = None, campo_id: int | None = None, grano: str | None = None,
           desde: date | None = None, hasta: date | None = None, limit: int = 200, offset: int = 0):
    stmt = select(Venta).order_by(Venta.fecha.desc(), Venta.id.desc())
    for col, v in ((Venta.campania_id, campania_id), (Venta.campo_id, campo_id), (Venta.grano, grano)):
        if v is not None:
            stmt = stmt.where(col == v)
    if desde:
        stmt = stmt.where(Venta.fecha >= desde)
    if hasta:
        stmt = stmt.where(Venta.fecha <= hasta)
    return db.scalars(stmt.limit(min(limit, 1000)).offset(offset)).all()


@router.post("", response_model=VentaOut, status_code=201)
def crear(db: DB, data: VentaIn, usuario: Usuario = requiere("ventas:escribir")):
    _validar(db, data)
    venta = Venta(**data.model_dump(), creado_por_id=usuario.id)
    venta.grano = venta.grano.strip().lower()
    db.add(venta)
    db.flush()
    auditar(db, usuario.id, "venta_creada", "venta", venta.id, total=venta.total, kilos=venta.kilos)
    db.commit()
    db.refresh(venta)
    return venta


@router.put("/{venta_id}", response_model=VentaOut)
def editar(db: DB, venta_id: int, data: VentaIn, usuario: Usuario = requiere("ventas:escribir")):
    venta = db.get(Venta, venta_id)
    if not venta:
        raise HTTPException(404, "Venta no encontrada")
    _validar(db, data)
    cambios = data.model_dump()
    cambios["grano"] = cambios["grano"].strip().lower()
    if dif := diferencias(venta, cambios):
        auditar(db, usuario.id, "venta_editada", "venta", venta.id, cambios=dif)
    for k, v in cambios.items():
        setattr(venta, k, v)
    db.commit()
    db.refresh(venta)
    return venta


@router.delete("/{venta_id}", status_code=204)
def borrar(db: DB, venta_id: int, usuario: Usuario = requiere("ventas:escribir")):
    venta = db.get(Venta, venta_id)
    if not venta:
        raise HTTPException(404, "Venta no encontrada")
    auditar(db, usuario.id, "venta_borrada", "venta", venta.id, total=venta.total, fecha=venta.fecha)
    db.delete(venta)
    db.commit()
