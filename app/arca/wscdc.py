"""Constatación de comprobantes en ARCA con el web service WSCDC.

1. WSAA: con el certificado de la empresa se firma un pedido de acceso (CMS) y ARCA devuelve un token y
   una firma válidos por unas 12 horas (se guardan en disco para no pedir otro: ARCA lo rechaza si hay uno vigente).
2. WSCDC `ComprobanteConstatar`: devuelve "A" (aprobado) o "R" (rechazado, con observaciones) para un
   comprobante emitido a nuestro CUIT.

Probar primero con ARCA_ENTORNO=homologacion y un certificado de homologación.
"""

import base64
import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from xml.sax.saxutils import escape

import httpx
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.serialization import pkcs7
from defusedxml import ElementTree as ET  # las respuestas vienen de la red: parser seguro

from app.config import settings

log = logging.getLogger(__name__)

URLS = {
    "homologacion": ("https://wsaahomo.afip.gov.ar/ws/services/LoginCms",
                     "https://wswhomo.afip.gov.ar/WSCDC/service.asmx"),
    "produccion": ("https://wsaa.afip.gov.ar/ws/services/LoginCms",
                   "https://servicios1.afip.gov.ar/WSCDC/service.asmx"),
}
NS_WSCDC = "http://servicios1.afip.gob.ar/wscdc/"
SERVICIO = "wscdc"


class ErrorArca(Exception):
    def __init__(self, mensaje: str, reintentable: bool = False):
        super().__init__(mensaje)
        self.reintentable = reintentable


@dataclass
class Resultado:
    resultado: str  # "A" o "R"
    observaciones: list[str]


def configurado() -> bool:
    return bool(settings.arca_cuit and settings.arca_certificado and settings.arca_clave_privada)


# --- WSAA ------------------------------------------------------------------------------


def _tra(ahora: datetime) -> bytes:
    fmt = "%Y-%m-%dT%H:%M:%S%z"
    return (
        '<?xml version="1.0" encoding="UTF-8"?><loginTicketRequest version="1.0"><header>'
        f"<uniqueId>{int(ahora.timestamp())}</uniqueId>"
        f"<generationTime>{(ahora - timedelta(minutes=5)).strftime(fmt)}</generationTime>"
        f"<expirationTime>{(ahora + timedelta(hours=10)).strftime(fmt)}</expirationTime>"
        f"</header><service>{SERVICIO}</service></loginTicketRequest>"
    ).encode()


def firmar_tra(cert_pem: bytes, clave_pem: bytes, ahora: datetime | None = None) -> str:
    """CMS (PKCS#7 firmado, con el contenido adjunto) del pedido de acceso, en base64."""
    cert = x509.load_pem_x509_certificate(cert_pem)
    clave = serialization.load_pem_private_key(clave_pem, password=None)
    cms = (pkcs7.PKCS7SignatureBuilder().set_data(_tra(ahora or datetime.now(UTC)))
           .add_signer(cert, clave, hashes.SHA256()).sign(serialization.Encoding.DER, []))
    return base64.b64encode(cms).decode()


def _ruta_ticket() -> Path:
    return Path(settings.storage_dir) / f"arca_ta_{settings.arca_entorno}.json"


def _ticket_guardado() -> tuple[str, str] | None:
    try:
        d = json.loads(_ruta_ticket().read_text())
        if datetime.fromisoformat(d["expira"]) > datetime.now(UTC) + timedelta(minutes=10):
            return d["token"], d["sign"]
    except (OSError, ValueError, KeyError):
        pass
    return None


def ticket_de_acceso(client: httpx.Client) -> tuple[str, str]:
    if t := _ticket_guardado():
        return t
    cms = firmar_tra(Path(settings.arca_certificado).read_bytes(), Path(settings.arca_clave_privada).read_bytes())
    sobre = (
        '<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" '
        'xmlns:wsaa="http://wsaa.view.sua.dvadac.desein.afip.gov"><soapenv:Body>'
        f"<wsaa:loginCms><wsaa:in0>{cms}</wsaa:in0></wsaa:loginCms></soapenv:Body></soapenv:Envelope>"
    )
    r = client.post(URLS[settings.arca_entorno][0], content=sobre,
                    headers={"Content-Type": "text/xml; charset=utf-8", "SOAPAction": '""'})
    raiz = ET.fromstring(r.content)
    if r.status_code != 200:
        falla = raiz.findtext(".//faultstring") or f"HTTP {r.status_code}"
        raise ErrorArca(f"WSAA rechazó el acceso: {falla}", reintentable=r.status_code >= 500)
    retorno = next((e.text for e in raiz.iter() if e.tag.endswith("loginCmsReturn")), None)
    if not retorno:
        raise ErrorArca("Respuesta inesperada del WSAA")
    ta = ET.fromstring(retorno)
    token, sign, expira = ta.findtext(".//token"), ta.findtext(".//sign"), ta.findtext(".//expirationTime")
    try:
        _ruta_ticket().write_text(json.dumps({"token": token, "sign": sign, "expira": expira}))
    except OSError:
        log.warning("No se pudo guardar el ticket de acceso de ARCA")
    return token, sign


# --- WSCDC ------------------------------------------------------------------------------


def constatar(cuit_emisor: str, tipo: int, punto_venta: int, numero: int, fecha, total, cae: str,
              client: httpx.Client | None = None) -> Resultado:
    if not configurado():
        raise ErrorArca("La verificación con ARCA no está configurada (ARCA_CUIT, ARCA_CERTIFICADO, ARCA_CLAVE_PRIVADA)")
    propio = client is None
    client = client or httpx.Client(timeout=30)
    try:
        token, sign = ticket_de_acceso(client)
        campos = {
            "CbteModo": "CAE", "CuitEmisor": cuit_emisor, "PtoVta": punto_venta, "CbteTipo": tipo, "CbteNro": numero,
            "CbteFch": fecha.strftime("%Y%m%d"), "ImpTotal": f"{total:.2f}", "CodAutorizacion": cae,
            "DocTipoReceptor": "80", "DocNroReceptor": settings.arca_cuit,
        }
        cmp = "".join(f"<w:{k}>{escape(str(v))}</w:{k}>" for k, v in campos.items())
        sobre = (
            f'<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/" xmlns:w="{NS_WSCDC}">'
            "<soap:Body><w:ComprobanteConstatar>"
            f"<w:Auth><w:Token>{escape(token)}</w:Token><w:Sign>{escape(sign)}</w:Sign>"
            f"<w:Cuit>{settings.arca_cuit}</w:Cuit></w:Auth>"
            f"<w:CmpReq>{cmp}</w:CmpReq></w:ComprobanteConstatar></soap:Body></soap:Envelope>"
        )
        try:
            r = client.post(URLS[settings.arca_entorno][1], content=sobre, headers={
                "Content-Type": "text/xml; charset=utf-8", "SOAPAction": f'"{NS_WSCDC}ComprobanteConstatar"'})
        except httpx.HTTPError as e:
            raise ErrorArca(f"No se pudo conectar con ARCA: {e}", reintentable=True) from e
        if r.status_code >= 500:
            raise ErrorArca(f"ARCA respondió con error {r.status_code}", reintentable=True)
        raiz = ET.fromstring(r.content)

        def textos(etiqueta: str) -> list[str]:
            out = []
            for e in raiz.iter():
                if e.tag.endswith("}" + etiqueta):
                    code = next((x.text for x in e if x.tag.endswith("Code")), None)
                    msg = next((x.text for x in e if x.tag.endswith("Msg")), None)
                    out.append(f"{code}: {msg}" if code else (msg or ""))
            return out

        errores = textos("Err")
        resultado = next((e.text for e in raiz.iter() if e.tag.endswith("}Resultado")), None)
        if not resultado:
            raise ErrorArca("; ".join(errores) or "Respuesta inesperada de WSCDC")
        return Resultado(resultado=resultado, observaciones=textos("Obs") + errores)
    finally:
        if propio:
            client.close()

