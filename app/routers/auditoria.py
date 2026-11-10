"""Consulta del registro de auditoría."""

from datetime import date, timedelta

from fastapi import APIRouter
from sqlalchemy import func, select

from app.deps import DB, requiere
from app.models import Auditoria, Usuario
from app.schemas import AuditoriaOut, PaginaAuditoria

router = APIRouter(tags=["auditoría"])


def _con_usuario(db: DB, stmt) -> list[AuditoriaOut]:
    filas = db.execute(stmt.add_columns(Usuario.nombre).outerjoin(Usuario, Usuario.id == Auditoria.usuario_id)).all()
    return [AuditoriaOut.model_validate(a).model_copy(update={"usuario": nombre}) for a, nombre in filas]


@router.get("/auditoria", response_model=PaginaAuditoria, dependencies=[requiere("auditoria:ver")])
def listar(
    db: DB,
    usuario_id: int | None = None,
    accion: str | None = None,
    entidad: str | None = None,
    entidad_id: str | None = None,
    desde: date | None = None,
    hasta: date | None = None,
    limit: int = 100,
    offset: int = 0,
):
    stmt = select(Auditoria)
    if usuario_id is not None:
        stmt = stmt.where(Auditoria.usuario_id == usuario_id)
    if accion:
        stmt = stmt.where(Auditoria.accion == accion)
    if entidad:
        stmt = stmt.where(Auditoria.entidad == entidad)
    if entidad_id:
        stmt = stmt.where(Auditoria.entidad_id == entidad_id)
    if desde:
        stmt = stmt.where(Auditoria.fecha >= desde)
    if hasta:
        stmt = stmt.where(Auditoria.fecha < hasta + timedelta(days=1))
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    pagina = stmt.order_by(Auditoria.fecha.desc(), Auditoria.id.desc()).limit(min(limit, 500)).offset(offset)
    return PaginaAuditoria(items=_con_usuario(db, pagina), total=total)


@router.get("/auditoria/acciones", dependencies=[requiere("auditoria:ver")])
def acciones(db: DB) -> list[str]:
    return list(db.scalars(select(Auditoria.accion).distinct().order_by(Auditoria.accion)))


@router.get("/facturas/{factura_id}/historial", response_model=list[AuditoriaOut],
            dependencies=[requiere("facturas:leer")])
def historial_factura(db: DB, factura_id: int):
    """Quién creó, editó, confirmó o anuló la factura y cuándo."""
    stmt = select(Auditoria).where(Auditoria.entidad == "factura", Auditoria.entidad_id == str(factura_id))
    return _con_usuario(db, stmt.order_by(Auditoria.fecha, Auditoria.id))
