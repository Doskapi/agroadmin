"""Lectura de cartas de porte electrónicas (CPE) en PDF o foto, con Claude."""

import logging
from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app import storage, trabajos
from app.extraccion import ia
from app.models import Archivo, CartaPorte, EstadoCartaPorte

log = logging.getLogger(__name__)

PROMPT = """Sos un asistente administrativo de una empresa agropecuaria argentina.
Extraé los datos de esta carta de porte electrónica (CPE) de granos.

- Kilos como números (45.000 en el papel -> 45000).
- Fechas en formato AAAA-MM-DD. fecha_carga es la fecha de partida/carga.
- CUIT solo dígitos, sin guiones. Patentes sin espacios.
- numero_ctg: el Código de Trazabilidad de Granos (CTG), solo dígitos.
- grano: en minúsculas (soja, maíz, trigo, girasol, sorgo, cebada...).
- destino: la planta o localidad de destino.
- Si un dato no figura o no es legible, dejalo vacío: no lo inventes.
"""


class CartaPorteExtraida(BaseModel):
    numero_ctg: str | None = None
    fecha_carga: str | None = None
    grano: str | None = None
    kilos_brutos: float | None = None
    kilos_tara: float | None = None
    kilos_netos: float | None = None
    destino: str | None = None
    destinatario_cuit: str | None = None
    transportista_cuit: str | None = None
    chofer_cuit: str | None = None
    patente_camion: str | None = None
    patente_acoplado: str | None = None
    km_recorrer: int | None = Field(default=None, description="kilómetros a recorrer")


def _cuit(v: str | None) -> str | None:
    d = "".join(c for c in v or "" if c.isdigit())
    return d if len(d) == 11 else None


def _kilos(v: float | None) -> Decimal | None:
    return None if v is None else Decimal(str(v)).quantize(Decimal("0.01"))


def aplicar(cp: CartaPorte, ext: CartaPorteExtraida) -> None:
    try:
        cp.fecha_carga = date.fromisoformat(ext.fecha_carga[:10]) if ext.fecha_carga else None
    except ValueError:
        cp.fecha_carga = None
    cp.numero_ctg = "".join(c for c in ext.numero_ctg or "" if c.isdigit())[:20] or None
    cp.grano = (ext.grano or "").strip().lower()[:64] or None
    cp.kilos_brutos, cp.kilos_tara, cp.kilos_netos = map(_kilos, (ext.kilos_brutos, ext.kilos_tara, ext.kilos_netos))
    if cp.kilos_netos is None and cp.kilos_brutos is not None and cp.kilos_tara is not None:
        cp.kilos_netos = cp.kilos_brutos - cp.kilos_tara
    cp.destino = (ext.destino or "")[:255] or None
    cp.destinatario_cuit, cp.transportista_cuit, cp.chofer_cuit = map(
        _cuit, (ext.destinatario_cuit, ext.transportista_cuit, ext.chofer_cuit))
    cp.patente_camion = (ext.patente_camion or "").replace(" ", "").upper()[:10] or None
    cp.patente_acoplado = (ext.patente_acoplado or "").replace(" ", "").upper()[:10] or None
    cp.km_recorrer = ext.km_recorrer


def _marcar_error(db: Session, cp_id: int, mensaje: str = "No se pudo leer el archivo. Cargala a mano") -> None:
    cp = db.get(CartaPorte, cp_id)
    if cp and cp.estado == EstadoCartaPorte.procesando:
        cp.estado = EstadoCartaPorte.borrador
        cp.error_extraccion = mensaje
        db.commit()


@trabajos.handler("procesar_carta_porte", al_fallar=lambda db, p: _marcar_error(db, p["carta_porte_id"]))
def procesar(db: Session, payload: dict) -> None:
    cp = db.get(CartaPorte, payload["carta_porte_id"])
    if not cp or cp.estado != EstadoCartaPorte.procesando:
        return
    archivo = db.get(Archivo, cp.archivo_id)
    try:
        ext, _ = ia.llamar(storage.leer(archivo.ruta), archivo.content_type, PROMPT, CartaPorteExtraida)
    except ia.ErrorExtraccionIA as e:
        if e.reintentable:
            raise trabajos.Reintentar(str(e)) from e
        cp.estado = EstadoCartaPorte.borrador
        cp.error_extraccion = str(e)
        return
    aplicar(cp, ext)
    cp.datos_extraidos = ext.model_dump()
    cp.error_extraccion = None
    cp.estado = EstadoCartaPorte.borrador
