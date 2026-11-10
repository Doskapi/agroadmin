"""Registro de auditoría: quién hizo qué, cuándo y desde dónde."""

from datetime import date, datetime
from decimal import Decimal
from enum import Enum

from sqlalchemy.orm import Session

from app.contexto import ip_actual
from app.models import Auditoria


def _json(v):
    if isinstance(v, Decimal):
        return str(v)
    if isinstance(v, (date, datetime)):
        return v.isoformat()
    if isinstance(v, Enum):
        return v.value
    if isinstance(v, dict):
        return {k: _json(x) for k, x in v.items()}
    if isinstance(v, (list, tuple, set)):
        return [_json(x) for x in v]
    return v


def auditar(db: Session, usuario_id: int | None, accion: str, entidad: str | None = None,
            entidad_id: object = None, **detalle) -> None:
    """Agrega una entrada. Se guarda con el commit de la operación que se está auditando."""
    db.add(Auditoria(
        usuario_id=usuario_id, accion=accion, entidad=entidad,
        entidad_id=None if entidad_id is None else str(entidad_id),
        detalle=_json(detalle) or None, ip=ip_actual.get(),
    ))


def diferencias(obj, cambios: dict, ignorar: set[str] = frozenset()) -> dict:
    """{campo: [antes, después]} de los campos que cambian, para guardar en el detalle."""
    out = {}
    for k, nuevo in cambios.items():
        if k in ignorar:
            continue
        viejo = getattr(obj, k, None)
        if isinstance(viejo, Decimal) and isinstance(nuevo, (Decimal, int, float)):
            if viejo == Decimal(str(nuevo)):  # 121000.50 y 121000.5 son lo mismo
                continue
        if _json(viejo) != _json(nuevo):
            out[k] = [viejo, nuevo]
    return out
