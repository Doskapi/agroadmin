from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Usuario
from app.security import PERMISOS, decode_access_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

DB = Annotated[Session, Depends(get_db)]


def get_usuario_actual(db: DB, token: Annotated[str, Depends(oauth2_scheme)]) -> Usuario:
    usuario_id = decode_access_token(token)
    usuario = db.get(Usuario, usuario_id) if usuario_id else None
    if not usuario or not usuario.activo:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "Token inválido o vencido", headers={"WWW-Authenticate": "Bearer"}
        )
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
