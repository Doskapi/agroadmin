"""Envío de correos por SMTP. Si no hay SMTP configurado, no se envía nada (y se avisa en el log)."""

import logging
import smtplib
from email.message import EmailMessage

from app.config import settings

log = logging.getLogger(__name__)


def configurado() -> bool:
    return bool(settings.smtp_host)


def enviar(destino: str, asunto: str, texto: str) -> bool:
    if not configurado():
        log.warning("SMTP no configurado: no se envió el correo '%s'", asunto)
        return False
    msg = EmailMessage()
    msg["From"] = settings.smtp_remitente
    msg["To"] = destino
    msg["Subject"] = asunto
    msg.set_content(texto)
    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as smtp:
            if settings.smtp_tls:
                smtp.starttls()
            if settings.smtp_usuario:
                smtp.login(settings.smtp_usuario, settings.smtp_password or "")
            smtp.send_message(msg)
        return True
    except (smtplib.SMTPException, OSError):
        log.exception("No se pudo enviar el correo '%s'", asunto)
        return False
