"""Contraseñas y catálogo de permisos."""

from pwdlib import PasswordHash

_hasher = PasswordHash.recommended()  # argon2


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return _hasher.verify(password, password_hash)


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
    "auditoria:ver": "Ver el registro de auditoría (quién hizo qué)",
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
        ["catalogos:leer", "facturas:leer", "facturas:confirmar", "cartas_porte:leer", "reportes:ver",
         "auditoria:ver"],
    ),
    "campo": (
        "Personal de campo: cartas de porte",
        ["catalogos:leer", "cartas_porte:leer", "cartas_porte:escribir"],
    ),
}
