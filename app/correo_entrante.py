"""Importación de facturas que llegan por correo: se revisa una casilla IMAP y cada PDF o foto adjunta se
importa como factura (igual que si se subiera desde la pantalla)."""

import email
import imaplib
import logging
from email.message import Message
from email.policy import default as politica
from email.utils import parseaddr

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import importacion
from app.config import settings
from app.models import CorreoImportado

log = logging.getLogger(__name__)
EXTENSIONES = (".pdf", ".jpg", ".jpeg", ".png", ".webp")


def configurado() -> bool:
    return bool(settings.imap_host and settings.imap_usuario)


def remitente_permitido(remitente: str) -> bool:
    permitidos = [p.strip().lower() for p in settings.imap_remitentes.split(",") if p.strip()]
    if not permitidos:
        return True
    direccion = parseaddr(remitente)[1].lower()
    dominio = direccion.rsplit("@", 1)[-1]
    return any(p == direccion or p.lstrip("@") == dominio for p in permitidos)


def adjuntos(msg: Message) -> list[tuple[str, bytes]]:
    out = []
    for parte in msg.walk():
        nombre = parte.get_filename() or ""
        tipo = parte.get_content_type()
        if parte.is_multipart():
            continue
        if tipo in ("application/pdf", "image/jpeg", "image/png", "image/webp") or nombre.lower().endswith(EXTENSIONES):
            if data := parte.get_payload(decode=True):
                out.append((nombre or "adjunto", data))
    return out


def procesar_mensaje(db: Session, crudo: bytes) -> CorreoImportado | None:
    """Importa los adjuntos de un correo. Devuelve el registro, o None si ya se había procesado."""
    msg = email.message_from_bytes(crudo, policy=politica)
    message_id = (msg.get("Message-ID") or "").strip()[:512] or f"sin-id-{hash(crudo)}"
    if db.scalar(select(CorreoImportado).where(CorreoImportado.message_id == message_id)):
        return None
    remitente, asunto = str(msg.get("From") or ""), str(msg.get("Subject") or "")
    registro = CorreoImportado(message_id=message_id, remitente=remitente[:255], asunto=asunto[:512], facturas=[])
    notas = []
    if not remitente_permitido(remitente):
        notas.append("Remitente no autorizado: no se importó nada")
    else:
        for nombre, data in adjuntos(msg):
            try:
                with db.begin_nested():
                    f = importacion.importar_factura(db, data, nombre, None, origen="correo", remitente=remitente)
                registro.facturas = [*registro.facturas, f.id]
            except HTTPException as e:
                notas.append(f"{nombre}: {e.detail}")
        if not registro.facturas and not notas:
            notas.append("Sin adjuntos PDF o imagen")
    registro.detalle = "\n".join(notas) or None
    db.add(registro)
    db.commit()
    log.info("Correo de %s: %s factura(s) importada(s)", remitente, len(registro.facturas))
    return registro


def revisar_casilla(db: Session, conexion_factory=imaplib.IMAP4_SSL) -> int:
    """Lee los correos no leídos de la carpeta, importa sus adjuntos y los marca como leídos."""
    importadas = 0
    with conexion_factory(settings.imap_host, settings.imap_puerto) as imap:
        imap.login(settings.imap_usuario, settings.imap_password or "")
        imap.select(settings.imap_carpeta)
        _, datos = imap.search(None, "UNSEEN")
        for num in (datos[0] or b"").split():
            _, partes = imap.fetch(num, "(RFC822)")
            crudo = next((p[1] for p in partes if isinstance(p, tuple)), None)
            if crudo is None:
                continue
            if registro := procesar_mensaje(db, crudo):
                importadas += len(registro.facturas)
            imap.store(num, "+FLAGS", "\\Seen")
    return importadas
