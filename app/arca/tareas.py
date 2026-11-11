"""Trabajo del worker: verificar una factura en ARCA."""

from sqlalchemy.orm import Session

from app import trabajos
from app.arca import wscdc
from app.auditoria import auditar
from app.models import Factura
from app.sesiones import ahora


def faltan_datos(f: Factura) -> list[str]:
    return [c for c in ("cuit_emisor", "tipo_comprobante", "punto_venta", "numero", "fecha_emision", "total", "cae")
            if getattr(f, c) is None]


def encolar(db: Session, factura: Factura) -> bool:
    """Encola la verificación si ARCA está configurado y la factura tiene los datos necesarios."""
    if not wscdc.configurado() or faltan_datos(factura):
        return False
    trabajos.encolar(db, "constatar_factura", {"factura_id": factura.id})
    return True


@trabajos.handler("constatar_factura")
def constatar(db: Session, payload: dict) -> None:
    f = db.get(Factura, payload["factura_id"])
    if not f or faltan_datos(f):
        return
    try:
        r = wscdc.constatar(f.cuit_emisor, f.tipo_comprobante, f.punto_venta, f.numero, f.fecha_emision, f.total,
                            f.cae)
    except wscdc.ErrorArca as e:
        if e.reintentable:
            raise trabajos.Reintentar(str(e)) from e
        f.arca_resultado, f.arca_observaciones = None, str(e)
        f.arca_verificado = ahora()
        return
    f.arca_resultado = r.resultado
    f.arca_observaciones = "\n".join(r.observaciones) or None
    f.arca_verificado = ahora()
    auditar(db, None, "factura_verificada_arca", "factura", f.id, resultado=r.resultado, observaciones=r.observaciones)
