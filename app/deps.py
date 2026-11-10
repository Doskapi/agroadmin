from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app import dos_pasos, sesiones
from app.db import get_db
from app.models import Sesion, Usuario
from app.security import PERMISOS

DB = Annotated[Session, Depends(get_db)]
_bearer = HTTPBearer(auto_error=False)

METODOS_SEGUROS = {"GET", "HEAD", "OPTIONS"}


def _no_autenticado(msg: str = "Sesión vencida o inválida. Volvé a ingresar"):
    return HTTPException(status.HTTP_401_UNAUTHORIZED, msg, headers={"WWW-Authenticate": "Bearer"})


def get_sesion(db: DB, request: Request,
               bearer: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)]) -> Sesion:
    """Sesión del pedido: token Bearer (clientes de la API) o cookie (navegador)."""
    if bearer:
        token = bearer.credentials
    else:
        token = request.cookies.get(sesiones.COOKIE)
        # Con cookie, los pedidos que modifican datos tienen que traer un header que un sitio ajeno no puede
        # mandar sin permiso de CORS (defensa contra CSRF, además de SameSite=Strict).
        if token and request.method not in METODOS_SEGUROS and not request.headers.get(sesiones.HEADER_CSRF):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Falta el header X-Requested-With")
    if not token:
        raise _no_autenticado("No autenticado")
    sesion = sesiones.buscar(db, token)
    if not sesion:
        raise _no_autenticado()
    return sesion


SesionActual = Annotated[Sesion, Depends(get_sesion)]


def get_usuario_sin_2fa(db: DB, sesion: SesionActual) -> Usuario:
    """Usuario de la sesión, aunque todavía deba activar la verificación en dos pasos (para /auth)."""
    usuario = db.get(Usuario, sesion.usuario_id)
    if not usuario or not usuario.activo:
        raise _no_autenticado()
    return usuario


UsuarioSin2FA = Annotated[Usuario, Depends(get_usuario_sin_2fa)]


def get_usuario_actual(usuario: UsuarioSin2FA) -> Usuario:
    if dos_pasos.debe_activar(usuario):
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            "Tenés que activar la verificación en dos pasos para seguir usando el sistema")
    return usuario


UsuarioActual = Annotated[Usuario, Depends(get_usuario_actual)]


def requiere(permiso: str):
    """Dependencia que exige un permiso: `Depends(requiere("facturas:escribir"))`."""
    if permiso not in PERMISOS:
        raise ValueError(f"Permiso desconocido: {permiso}")

    def _check(usuario: UsuarioActual) -> Usuario:
        if permiso not in usuario.permisos:
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"Falta el permiso '{permiso}'")
        return usuario

    return Depends(_check)
