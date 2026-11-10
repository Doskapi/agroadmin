"""Sesiones del lado del servidor: se pueden cerrar (una, todas o las demás) y vencen por inactividad.

El navegador guarda el token en una cookie httpOnly (no accesible desde JavaScript). Para clientes de la API
el mismo token se puede mandar como `Authorization: Bearer`.
"""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from fastapi import Request, Response
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.config import settings
from app.contexto import ip_actual, user_agent_actual
from app.models import Sesion

COOKIE = "agro_sesion"
COOKIE_PATH = "/api"  # detrás de nginx la API vive en /api
# Header que exige la API a los pedidos que modifican datos y se autentican con la cookie (defensa CSRF)
HEADER_CSRF = "x-requested-with"


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def ahora() -> datetime:
    return datetime.now(UTC)


def crear(db: Session, usuario_id: int) -> str:
    token = secrets.token_urlsafe(32)
    db.add(Sesion(
        token_hash=_hash(token), usuario_id=usuario_id, expira=ahora() + timedelta(hours=settings.sesion_maxima_horas),
        ip=ip_actual.get(), user_agent=(user_agent_actual.get() or "")[:255] or None,
    ))
    return token


def buscar(db: Session, token: str) -> Sesion | None:
    """Sesión vigente para el token (y actualiza su última actividad), o None."""
    sesion = db.scalar(select(Sesion).where(Sesion.token_hash == _hash(token)))
    t = ahora()
    if (not sesion or sesion.revocada or sesion.expira <= t
            or sesion.ultima_actividad <= t - timedelta(minutes=settings.access_token_minutes)):
        return None
    if sesion.ultima_actividad <= t - timedelta(minutes=1):  # no escribir en cada pedido
        sesion.ultima_actividad = t
        db.commit()
    return sesion


def revocar(db: Session, usuario_id: int, *, excepto: int | None = None, solo: int | None = None) -> int:
    stmt = update(Sesion).where(Sesion.usuario_id == usuario_id, Sesion.revocada.is_(None))
    if excepto is not None:
        stmt = stmt.where(Sesion.id != excepto)
    if solo is not None:
        stmt = stmt.where(Sesion.id == solo)
    return db.execute(stmt.values(revocada=ahora())).rowcount


def poner_cookie(response: Response, request: Request, token: str) -> None:
    segura = settings.cookie_segura == "si" or (
        settings.cookie_segura == "auto" and request.headers.get("x-forwarded-proto", request.url.scheme) == "https")
    response.set_cookie(COOKIE, token, httponly=True, secure=segura, samesite="strict", path=COOKIE_PATH,
                        max_age=settings.sesion_maxima_horas * 3600)


def borrar_cookie(response: Response) -> None:
    response.delete_cookie(COOKIE, path=COOKIE_PATH)
