import base64
import json

import cv2
import numpy as np
import pymupdf
import zxingcpp


def url_qr(**overrides) -> str:
    datos = {
        "ver": 1, "fecha": "2026-10-15", "cuit": 30712345678, "ptoVta": 3, "tipoCmp": 1, "nroCmp": 1542,
        "importe": 121000.50, "moneda": "PES", "ctz": 1, "tipoDocRec": 80, "nroDocRec": 20111111112,
        "tipoCodAut": "E", "codAut": 76543210987654,
    } | overrides
    p = base64.b64encode(json.dumps(datos).encode()).decode()
    return f"https://www.afip.gob.ar/fe/qr/?p={p}"


def png_qr(texto: str) -> bytes:
    img = np.asarray(zxingcpp.create_barcode(texto, zxingcpp.BarcodeFormat.QRCode).to_image(scale=4))
    return cv2.imencode(".png", img)[1].tobytes()


def pdf_con_qr(texto_qr: str, con_link: bool = False) -> bytes:
    """Arma un PDF de factura falso con el QR como imagen (como lo generan la mayoría de los sistemas)."""
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), "FACTURA A  N° 0003-00001542\nAgroinsumos del Sur SA")
    rect = pymupdf.Rect(72, 600, 222, 750)
    page.insert_image(rect, stream=png_qr(texto_qr))
    if con_link:
        page.insert_link({"kind": pymupdf.LINK_URI, "from": rect, "uri": texto_qr})
    return doc.tobytes()
