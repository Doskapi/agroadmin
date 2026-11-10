"""Cola de trabajos sobre Postgres (`SELECT ... FOR UPDATE SKIP LOCKED`), sin servicios extra.

- La API encola (`encolar`) y responde enseguida; el worker (`app.worker`) los ejecuta.
- Si un trabajo falla se reintenta con espera creciente; tras `max_intentos` queda en `error`.
- Si el worker se cae a mitad de un trabajo, al vencer `bloqueado_hasta` otro lo retoma.
"""

import logging
from collections.abc import Callable
from datetime import timedelta

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import EstadoTrabajo, Trabajo
from app.sesiones import ahora

log = logging.getLogger(__name__)

TIEMPO_MAXIMO = timedelta(minutes=10)  # si un trabajo tarda más, se considera abandonado
ESPERA_BASE = timedelta(seconds=30)

ACTIVOS = (EstadoTrabajo.pendiente, EstadoTrabajo.en_curso)


class Reintentar(Exception):
    """El trabajo no se pudo hacer ahora (ej. límite de la API de Claude) pero conviene reintentar."""


# tipo -> (función que lo ejecuta, función a llamar si falla definitivamente)
Handler = Callable[[Session, dict], None]
_handlers: dict[str, tuple[Handler, Handler | None]] = {}


def handler(tipo: str, al_fallar: Handler | None = None):
    def registrar(fn: Handler) -> Handler:
        _handlers[tipo] = (fn, al_fallar)
        return fn
    return registrar


def encolar(db: Session, tipo: str, payload: dict | None = None, *, max_intentos: int = 5) -> Trabajo:
    """Agrega un trabajo (se guarda con el commit de quien llama). Si ya hay uno igual sin terminar, lo reusa."""
    payload = payload or {}
    existente = db.scalar(select(Trabajo).where(Trabajo.tipo == tipo, Trabajo.payload == payload,
                                                Trabajo.estado.in_(ACTIVOS)))
    if existente:
        return existente
    t = Trabajo(tipo=tipo, payload=payload, max_intentos=max_intentos, intentos=0, estado=EstadoTrabajo.pendiente,
                ejecutar_desde=ahora())
    db.add(t)
    return t


def _tomar(db: Session) -> Trabajo | None:
    t_ahora = ahora()
    trabajo = db.scalar(
        select(Trabajo)
        .where(or_(
            and_(Trabajo.estado == EstadoTrabajo.pendiente, Trabajo.ejecutar_desde <= t_ahora),
            and_(Trabajo.estado == EstadoTrabajo.en_curso, Trabajo.bloqueado_hasta < t_ahora),
        ))
        .order_by(Trabajo.ejecutar_desde, Trabajo.id)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    if trabajo:
        trabajo.estado = EstadoTrabajo.en_curso
        trabajo.intentos += 1
        trabajo.bloqueado_hasta = t_ahora + TIEMPO_MAXIMO
        db.commit()
    return trabajo


def ejecutar_uno() -> bool:
    """Ejecuta el próximo trabajo disponible. Devuelve False si no había ninguno."""
    with SessionLocal() as db:
        trabajo = _tomar(db)
        if not trabajo:
            return False
        tid, tipo, payload, intentos, maximo = (trabajo.id, trabajo.tipo, dict(trabajo.payload), trabajo.intentos,
                                               trabajo.max_intentos)

    fn, al_fallar = _handlers.get(tipo, (None, None))
    error: str | None = None
    with SessionLocal() as db:
        try:
            if fn is None:
                raise RuntimeError(f"Tipo de trabajo desconocido: {tipo}")
            fn(db, payload)
            db.commit()
        except Exception as e:  # cualquier error del handler se registra y se reintenta
            db.rollback()
            error = f"{type(e).__name__}: {e}"[:2000]
            if isinstance(e, Reintentar):
                log.warning("Trabajo %s (%s) se reintentará: %s", tid, tipo, e)
            else:
                log.exception("Falló el trabajo %s (%s), intento %s de %s", tid, tipo, intentos, maximo)

    with SessionLocal() as db:
        trabajo = db.get(Trabajo, tid)
        if error is None:
            trabajo.estado = EstadoTrabajo.hecho
            trabajo.terminado = ahora()
            trabajo.error = None
        elif intentos >= maximo:
            trabajo.estado = EstadoTrabajo.error
            trabajo.terminado = ahora()
            trabajo.error = error
            if al_fallar:
                try:
                    al_fallar(db, payload)
                except Exception:
                    log.exception("Falló el manejo del error del trabajo %s", tid)
        else:
            trabajo.estado = EstadoTrabajo.pendiente
            trabajo.error = error
            trabajo.ejecutar_desde = ahora() + ESPERA_BASE * 2 ** (intentos - 1)
        trabajo.bloqueado_hasta = None
        db.commit()
    return True


def ejecutar_pendientes(limite: int = 100) -> int:
    """Ejecuta todo lo que esté listo (para tests y para correr a mano)."""
    n = 0
    while n < limite and ejecutar_uno():
        n += 1
    return n
