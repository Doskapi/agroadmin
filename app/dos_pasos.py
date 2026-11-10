"""Verificación en dos pasos con códigos TOTP (Google Authenticator, Authy, 1Password...)."""

import base64
import hashlib
import hmac
import json
import time

import cv2
import numpy as np
import pyotp
import zxingcpp

from app.config import settings
from app.models import Usuario

EMISOR = "Gestión Agro"
VIGENCIA_DESAFIO = 300  # segundos para ingresar el código después de la contraseña


def nuevo_secreto() -> str:
    return pyotp.random_base32()


def uri(usuario: Usuario) -> str:
    return pyotp.TOTP(usuario.totp_secreto).provisioning_uri(name=usuario.email, issuer_name=EMISOR)


def qr_png(texto: str) -> str:
    """PNG del QR en base64, para mostrar en el alta."""
    img = np.asarray(zxingcpp.create_barcode(texto, zxingcpp.BarcodeFormat.QRCode).to_image(scale=6))
    img = np.pad(img, 24, constant_values=255)  # margen blanco para que los lectores lo encuentren
    return base64.b64encode(cv2.imencode(".png", img)[1].tobytes()).decode()


def verificar(usuario: Usuario, codigo: str) -> bool:
    """Valida el código (acepta el paso anterior y el siguiente por desfasajes de reloj) y no deja reusarlo."""
    if not usuario.totp_secreto:
        return False
    codigo = "".join(c for c in codigo if c.isdigit())
    totp = pyotp.TOTP(usuario.totp_secreto)
    paso_actual = int(time.time()) // totp.interval
    for paso in (paso_actual - 1, paso_actual, paso_actual + 1):
        if hmac.compare_digest(totp.at(paso * totp.interval), codigo):
            if usuario.totp_ultimo_paso is not None and paso <= usuario.totp_ultimo_paso:
                return False  # código ya usado
            usuario.totp_ultimo_paso = paso
            return True
    return False


def debe_activar(usuario: Usuario) -> bool:
    return not usuario.totp_activo and bool(usuario.permisos & settings.permisos_con_2fa)


# --- Desafío entre la contraseña y el código -----------------------------------------


def _firma(datos: bytes) -> str:
    return hmac.new(settings.secret_key.encode(), datos, hashlib.sha256).hexdigest()


def crear_desafio(usuario_id: int) -> str:
    datos = base64.urlsafe_b64encode(json.dumps({"u": usuario_id, "e": int(time.time()) + VIGENCIA_DESAFIO}).encode())
    return f"{datos.decode()}.{_firma(datos)}"


def leer_desafio(desafio: str) -> int | None:
    try:
        datos, firma = desafio.rsplit(".", 1)
        if not hmac.compare_digest(_firma(datos.encode()), firma):
            return None
        contenido = json.loads(base64.urlsafe_b64decode(datos))
        return int(contenido["u"]) if contenido["e"] > time.time() else None
    except (ValueError, KeyError, json.JSONDecodeError):
        return None
