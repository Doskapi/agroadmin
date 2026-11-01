from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select

from app.deps import DB, UsuarioActual
from app.models import Usuario
from app.schemas import Token, UsuarioOut
from app.security import create_access_token, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=Token)
def login(db: DB, form: Annotated[OAuth2PasswordRequestForm, Depends()]):
    """Login con email (campo `username`) y contraseña. Devuelve un token Bearer."""
    usuario = db.scalar(select(Usuario).where(Usuario.email == form.username.lower()))
    if not usuario or not usuario.activo or not verify_password(form.password, usuario.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Email o contraseña incorrectos")
    return Token(access_token=create_access_token(usuario.id))


@router.get("/yo", response_model=UsuarioOut)
def yo(usuario: UsuarioActual):
    return usuario
