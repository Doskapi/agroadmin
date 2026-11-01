"""Contraseñas, tokens JWT y catálogo de permisos."""

from datetime import UTC, datetime, timedelta

import jwt
from pwdlib import PasswordHash

from app.config import settings

ALGORITHM = "HS256"
_hasher = PasswordHash.recommended()  # argon2


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return _hasher.verify(password, password_hash)


def create_access_token(usuario_id: int) -> str:
    expira = datetime.now(UTC) + timedelta(minutes=settings.access_token_minutes)
    return jwt.encode({"sub": str(usuario_id), "exp": expira}, settings.secret_key, algorithm=ALGORITHM)


def decode_access_token(token: str) -> int | None:
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
        return int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        return None


# Permisos que existen en el sistema. Se sincronizan con la tabla `permisos` en app/seed.py.
PERMISOS: dict[str, str] = {
    "usuarios:admin": "Crear usuarios y asignar roles",
    "catalogos:leer": "Ver proveedores, campos, lotes, campañas y categorías",
    "catalogos:escribir": "Crear y editar proveedores, campos, lotes, campañas y categorías",
    "facturas:leer": "Ver facturas",
    "facturas:escribir": "Cargar y editar facturas",
    "facturas:confirmar": "Confirmar facturas revisadas",
    "cartas_porte:leer": "Ver cartas de porte",
    "cartas_porte:escribir": "Cargar y editar cartas de porte",
    "reportes:ver": "Ver reportes y dashboards",
}

# Roles iniciales. Se pueden editar después desde la API.
ROLES_INICIALES: dict[str, tuple[str, list[str]]] = {
    "admin": ("Acceso total", list(PERMISOS)),
    "administrativo": (
        "Carga de facturas y cartas de porte",
        ["catalogos:leer", "catalogos:escribir", "facturas:leer", "facturas:escribir",
         "cartas_porte:leer", "cartas_porte:escribir", "reportes:ver"],
    ),
    "contador": (
        "Revisión y confirmación de facturas, reportes",
        ["catalogos:leer", "facturas:leer", "facturas:confirmar", "cartas_porte:leer", "reportes:ver"],
    ),
    "campo": (
        "Personal de campo: cartas de porte",
        ["catalogos:leer", "cartas_porte:leer", "cartas_porte:escribir"],
    ),
}
