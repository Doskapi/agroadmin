import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select

from app import limite_login
from app.deps import DB, UsuarioActual
from app.models import Usuario
from app.schemas import Token, UsuarioOut
from app.security import create_access_token, hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])
log = logging.getLogger(__name__)

# Se verifica contra este hash cuando el email no existe, para que la respuesta tarde lo mismo
# y no se pueda averiguar qué emails tienen cuenta.
_HASH_FICTICIO = hash_password("no-es-una-clave-real")


def ip_cliente(request: Request) -> str:
    # La API solo es accesible a través de nginx, que pone X-Real-IP con la IP del cliente.
    return request.headers.get("x-real-ip") or (request.client.host if request.client else "desconocida")


@router.post("/login", response_model=Token)
def login(db: DB, request: Request, form: Annotated[OAuth2PasswordRequestForm, Depends()]):
    """Login con email (campo `username`) y contraseña. Devuelve un token Bearer."""
    email = form.username.strip().lower()
    ip = ip_cliente(request)

    if espera := limite_login.segundos_de_bloqueo(email, ip):
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"Demasiados intentos fallidos. Probá de nuevo en {(espera + 59) // 60} minuto(s)",
            headers={"Retry-After": str(espera)},
        )

    usuario = db.scalar(select(Usuario).where(Usuario.email == email))
    password_ok = verify_password(form.password, usuario.password_hash if usuario else _HASH_FICTICIO)
    if not usuario or not usuario.activo or not password_ok:
        limite_login.registrar_fallo(email, ip)
        log.warning("Login fallido para %s desde %s", email, ip)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Email o contraseña incorrectos")

    limite_login.registrar_exito(email)
    return Token(access_token=create_access_token(usuario.id))


@router.get("/yo", response_model=UsuarioOut)
def yo(usuario: UsuarioActual):
    return usuario
