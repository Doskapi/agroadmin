"""Vinculación de ítems de factura con insumos normalizados.

Cuando alguien asigna un insumo a un ítem con "recordar", la descripción normalizada queda como alias:
los ítems con la misma descripción (los ya cargados y los que lleguen) se asignan solos.
"""

import re
import unicodedata

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models import FacturaItem, InsumoAlias


def normalizar(descripcion: str) -> str:
    """Minúsculas, sin tildes, sin signos y con espacios simples: "Glifosato  62% x 20 Lts." -> "glifosato 62 x 20 lts"."""
    s = unicodedata.normalize("NFKD", descripcion)
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return " ".join(s.split())[:512]


def autoasignar(db: Session, items: list[FacturaItem]) -> None:
    """Completa insumo_id en los ítems sin insumo cuya descripción tenga un alias."""
    pendientes = {normalizar(i.descripcion): i for i in items if i.insumo_id is None and i.descripcion}
    if not pendientes:
        return
    alias = dict(db.execute(select(InsumoAlias.descripcion, InsumoAlias.insumo_id)
                            .where(InsumoAlias.descripcion.in_(list(pendientes)))).all())
    for item in items:
        if item.insumo_id is None and item.descripcion:
            item.insumo_id = alias.get(normalizar(item.descripcion))


def recordar(db: Session, descripcion: str, insumo_id: int | None) -> int:
    """Guarda (o borra, si insumo_id es None) el alias y lo aplica a todos los ítems con esa descripción.
    Devuelve cuántos ítems se actualizaron."""
    clave = normalizar(descripcion)
    alias = db.get(InsumoAlias, clave)
    if insumo_id is None:
        if alias:
            db.delete(alias)
    elif alias:
        alias.insumo_id = insumo_id
    else:
        db.add(InsumoAlias(descripcion=clave, insumo_id=insumo_id))

    # La comparación se hace en Python porque la normalización no es trivial en SQL;
    # se acota a candidatos por una búsqueda aproximada.
    primera = clave.split(" ")[0] if clave else ""
    candidatos = db.execute(
        select(FacturaItem.id, FacturaItem.descripcion).where(FacturaItem.descripcion.ilike(f"%{primera}%"))
    ).all()
    ids = [i for i, d in candidatos if normalizar(d) == clave]
    if ids:
        db.execute(update(FacturaItem).where(FacturaItem.id.in_(ids)).values(insumo_id=insumo_id))
    return len(ids)
