"""Worker: ejecuta la cola de trabajos y las tareas periódicas.

Uso: python -m app.worker
"""

import logging
import signal
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app import trabajos
from app.config import settings
from app.db import SessionLocal
from app.extraccion import pipeline  # noqa: F401  (registra el handler "procesar_factura")
from app.logs import configurar_logs
from app.models import Cotizacion, EstadoFactura, Factura, TareaProgramada, Trabajo
from app.routers.cotizaciones import _guardar, traer_del_bcra
from app.sesiones import ahora

log = logging.getLogger("app.worker")

LATIDO = "_latido"
ESPERA_SIN_TRABAJO = 2  # segundos


@dataclass
class Programada:
    nombre: str
    cada: timedelta
    fn: Callable[[Session], None]
    activa: Callable[[], bool] = lambda: True


def _actualizar_cotizaciones(db: Session) -> None:
    ultima = db.scalar(select(func.max(Cotizacion.fecha)).where(Cotizacion.moneda == "DOL"))
    if ultima is None:
        return  # nunca se usaron: no se empieza a traer historia sin que nadie lo pida
    hasta = date.today()
    if ultima < hasta:
        n = _guardar(db, traer_del_bcra(ultima + timedelta(days=1), hasta))
        log.info("Cotizaciones del BCRA actualizadas: %s nuevas", n)


PROGRAMADAS: list[Programada] = [
    Programada("actualizar_cotizaciones", timedelta(hours=6), _actualizar_cotizaciones,
               lambda: settings.cotizaciones_automaticas),
]


def registrar(p: Programada) -> None:
    """Para que otros módulos agreguen tareas periódicas."""
    PROGRAMADAS.append(p)


def _marcar(db: Session, nombre: str) -> None:
    stmt = insert(TareaProgramada).values(nombre=nombre, ultima_ejecucion=ahora())
    db.execute(stmt.on_conflict_do_update(index_elements=["nombre"], set_={"ultima_ejecucion": ahora()}))
    db.commit()


def correr_programadas() -> None:
    for p in PROGRAMADAS:
        if not p.activa():
            continue
        with SessionLocal() as db:
            # FOR UPDATE: si hubiera dos workers, solo uno la ejecuta
            fila = db.scalar(select(TareaProgramada).where(TareaProgramada.nombre == p.nombre)
                             .with_for_update(skip_locked=True))
            if fila and fila.ultima_ejecucion > ahora() - p.cada:
                continue
            try:
                p.fn(db)
                db.commit()
            except Exception:
                db.rollback()
                log.exception("Falló la tarea programada %s", p.nombre)
            _marcar(db, p.nombre)


def recuperar_huerfanas() -> int:
    """Facturas que quedaron `procesando` sin trabajo (ej. importadas antes de existir la cola)."""
    with SessionLocal() as db:
        con_trabajo = select(Trabajo.payload["factura_id"].as_integer()).where(
            Trabajo.tipo == "procesar_factura", Trabajo.estado.in_(trabajos.ACTIVOS))
        huerfanas = db.scalars(select(Factura).where(Factura.estado == EstadoFactura.procesando,
                                                     Factura.id.not_in(con_trabajo))).all()
        for f in huerfanas:
            pipeline.encolar(db, f)
        db.commit()
        return len(huerfanas)


def latido() -> None:
    with SessionLocal() as db:
        _marcar(db, LATIDO)


def main() -> None:
    configurar_logs()
    detener = False

    def _parar(*_):
        nonlocal detener
        detener = True
        log.info("Deteniendo el worker al terminar el trabajo en curso…")

    signal.signal(signal.SIGTERM, _parar)
    signal.signal(signal.SIGINT, _parar)

    if n := recuperar_huerfanas():
        log.info("Se encolaron %s facturas que habían quedado procesando", n)
    log.info("Worker listo")
    ultimo_latido = 0.0
    while not detener:
        if time.monotonic() - ultimo_latido > 30:
            latido()
            correr_programadas()
            ultimo_latido = time.monotonic()
        if not trabajos.ejecutar_uno():
            time.sleep(ESPERA_SIN_TRABAJO)


if __name__ == "__main__":
    main()
