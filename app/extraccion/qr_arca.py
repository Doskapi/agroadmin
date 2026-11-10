"""Lectura del código QR de facturas electrónicas de ARCA (ex AFIP).

El QR contiene una URL del tipo https://www.afip.gob.ar/fe/qr/?p=<JSON en base64> con:
ver, fecha, cuit, ptoVta, tipoCmp, nroCmp, importe, moneda, ctz, tipoDocRec, nroDocRec, tipoCodAut, codAut.
Son datos oficiales del comprobante, así que tienen prioridad sobre cualquier otra extracción.
"""

import base64
import json
import os
import re
from dataclasses import asdict, dataclass
from datetime import date
from decimal import Decimal
from urllib.parse import parse_qs, unquote, urlparse

# Tope de píxeles al decodificar imágenes: evita que una imagen chica en bytes pero enorme
# en resolución ("bomba de descompresión") se coma la memoria. 60 MP sobra para una foto de celular.
os.environ.setdefault("OPENCV_IO_MAX_IMAGE_PIXELS", str(60_000_000))

import cv2  # noqa: E402
import numpy as np  # noqa: E402
import zxingcpp  # noqa: E402

_URL_RE = re.compile(r"https?://(?:www\.)?(?:afip|arca)\.gob\.ar/fe/qr/?\?p=[A-Za-z0-9+/=_%\-]+", re.IGNORECASE)


@dataclass
class DatosQR:
    fecha: date
    cuit_emisor: str
    punto_venta: int
    tipo_comprobante: int
    numero: int
    importe: Decimal
    moneda: str
    cotizacion: Decimal
    cae: str | None
    nro_doc_receptor: str | None

    def to_json(self) -> dict:
        d = asdict(self)
        d["fecha"] = self.fecha.isoformat()
        d["importe"] = str(self.importe)
        d["cotizacion"] = str(self.cotizacion)
        return d


def parsear_url(url: str) -> DatosQR | None:
    if not _URL_RE.match(url.strip()):
        return None
    p = parse_qs(urlparse(url.strip()).query).get("p", [None])[0]
    if not p:
        return None
    p = unquote(p)
    try:
        raw = base64.b64decode(p + "=" * (-len(p) % 4), altchars=b"-_" if ("-" in p or "_" in p) else None)
        d = json.loads(raw)
        return DatosQR(
            fecha=date.fromisoformat(str(d["fecha"])[:10]),
            cuit_emisor=str(d["cuit"]),
            punto_venta=int(d["ptoVta"]),
            tipo_comprobante=int(d["tipoCmp"]),
            numero=int(d["nroCmp"]),
            importe=Decimal(str(d["importe"])),
            moneda=str(d.get("moneda", "PES")),
            cotizacion=Decimal(str(d.get("ctz", 1))),
            cae=str(d["codAut"]) if d.get("codAut") else None,
            nro_doc_receptor=str(d["nroDocRec"]) if d.get("nroDocRec") else None,
        )
    except (ValueError, KeyError, TypeError, json.JSONDecodeError):
        return None


def buscar_urls_en_texto(texto: str) -> list[str]:
    return _URL_RE.findall(texto or "")


def leer_qrs_en_imagen(imagen: bytes) -> list[str]:
    """Devuelve el contenido de todos los QR que encuentre en la imagen (PNG, JPG, WEBP...)."""
    arr = cv2.imdecode(np.frombuffer(imagen, np.uint8), cv2.IMREAD_GRAYSCALE)
    if arr is None:
        return []
    # zxing-cpp es bastante más robusto que el detector de OpenCV con fotos y escaneos.
    return [r.text for r in zxingcpp.read_barcodes(arr, formats=zxingcpp.BarcodeFormat.QRCode) if r.text]


def primer_qr_valido(candidatos: list[str]) -> DatosQR | None:
    for c in candidatos:
        datos = parsear_url(c)
        if datos:
            return datos
    return None
