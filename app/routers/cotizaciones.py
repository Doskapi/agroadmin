"""Cotizaciones del dólar por día, para expresar los reportes en moneda dura.

Se pueden cargar a mano o traer de la API pública del BCRA (tipo de cambio de referencia, Com. A 3500).
"""

import logging
from datetime import date, timedelta
from decimal import Decimal

import httpx
from fastapi import APIRouter, HTTPException
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert

from app.deps import DB, requiere
from app.models import Cotizacion
from app.schemas import CotizacionIn, CotizacionOut

router = APIRouter(prefix="/cotizaciones", tags=["cotizaciones"])
log = logging.getLogger(__name__)

BCRA_URL = "https://api.bcra.gob.ar/estadisticascambiarias/v1.0/Cotizaciones/USD"


@router.get("", response_model=list[CotizacionOut], dependencies=[requiere("catalogos:leer")])
def listar(db: DB, desde: date | None = None, hasta: date | None = None, limit: int = 400):
    stmt = select(Cotizacion).where(Cotizacion.moneda == "DOL")
    if desde:
        stmt = stmt.where(Cotizacion.fecha >= desde)
    if hasta:
        stmt = stmt.where(Cotizacion.fecha <= hasta)
    return db.scalars(stmt.order_by(Cotizacion.fecha.desc()).limit(min(limit, 5000))).all()


def _guardar(db: DB, valores: dict[date, Decimal]) -> int:
    if not valores:
        return 0
    stmt = insert(Cotizacion).values([{"moneda": "DOL", "fecha": f, "valor": v} for f, v in valores.items()])
    db.execute(stmt.on_conflict_do_update(index_elements=["moneda", "fecha"], set_={"valor": stmt.excluded.valor}))
    db.commit()
    return len(valores)


@router.put("", dependencies=[requiere("catalogos:escribir")])
def cargar(db: DB, data: list[CotizacionIn]) -> dict[str, int]:
    """Carga o corrige cotizaciones (pesos por dólar) por fecha."""
    return {"guardadas": _guardar(db, {c.fecha: c.valor for c in data})}


def traer_del_bcra(desde: date, hasta: date) -> dict[date, Decimal]:
    valores: dict[date, Decimal] = {}
    inicio = desde
    with httpx.Client(timeout=20) as client:
        while inicio <= hasta:
            fin = min(inicio + timedelta(days=365), hasta)
            r = client.get(BCRA_URL, params={"fechadesde": inicio.isoformat(), "fechahasta": fin.isoformat()})
            if r.status_code == 404:  # sin datos en el rango
                inicio = fin + timedelta(days=1)
                continue
            r.raise_for_status()
            for dia in r.json().get("results", []):
                for d in dia.get("detalle", []):
                    if d.get("codigoMoneda") == "USD" and d.get("tipoCotizacion"):
                        valores[date.fromisoformat(dia["fecha"])] = Decimal(str(d["tipoCotizacion"]))
            inicio = fin + timedelta(days=1)
    return valores


@router.post("/actualizar", dependencies=[requiere("catalogos:escribir")])
def actualizar(db: DB, desde: date | None = None, hasta: date | None = None) -> dict[str, int]:
    """Trae del BCRA las cotizaciones faltantes (por defecto, desde la última guardada o desde hace 3 años)."""
    hasta = hasta or date.today()
    if desde is None:
        ultima = db.scalar(select(func.max(Cotizacion.fecha)).where(Cotizacion.moneda == "DOL"))
        desde = ultima + timedelta(days=1) if ultima else hasta - timedelta(days=3 * 365)
    if desde > hasta:
        return {"guardadas": 0}
    try:
        valores = traer_del_bcra(desde, hasta)
    except httpx.HTTPError as e:
        log.warning("No se pudo consultar el BCRA: %s", e)
        raise HTTPException(502, "No se pudo consultar la API del BCRA. Probá más tarde o cargalas a mano.")
    return {"guardadas": _guardar(db, valores)}
