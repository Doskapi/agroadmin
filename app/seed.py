"""Carga inicial idempotente: permisos, roles, categorías y usuario admin.

Uso: python -m app.seed
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import SessionLocal
from app.models import Categoria, Permiso, Rol, Usuario
from app.security import PERMISOS, ROLES_INICIALES, hash_password

CATEGORIAS = [
    "semillas", "agroquimicos", "fertilizantes", "combustible", "fletes", "servicios",
    "maquinaria", "repuestos", "honorarios", "arrendamiento", "otros",
]


def seed(db: Session) -> None:
    existentes = {p.codigo: p for p in db.scalars(select(Permiso))}
    for codigo, desc in PERMISOS.items():
        if codigo in existentes:
            existentes[codigo].descripcion = desc
        else:
            db.add(Permiso(codigo=codigo, descripcion=desc))
    db.flush()

    permisos = {p.codigo: p for p in db.scalars(select(Permiso))}
    for nombre, (desc, codigos) in ROLES_INICIALES.items():
        if not db.scalar(select(Rol).where(Rol.nombre == nombre)):
            db.add(Rol(nombre=nombre, descripcion=desc, permisos=[permisos[c] for c in codigos]))
    # El rol admin siempre tiene todos los permisos, incluidos los que se agreguen en el futuro.
    db.flush()
    admin_rol = db.scalar(select(Rol).where(Rol.nombre == "admin"))
    admin_rol.permisos = list(permisos.values())

    for nombre in CATEGORIAS:
        if not db.scalar(select(Categoria).where(Categoria.nombre == nombre)):
            db.add(Categoria(nombre=nombre))

    email = settings.admin_email.lower()
    if not db.scalar(select(Usuario).where(Usuario.email == email)):
        db.add(Usuario(email=email, nombre="Administrador", password_hash=hash_password(settings.admin_password),
                       roles=[admin_rol]))
    db.commit()


if __name__ == "__main__":
    with SessionLocal() as db:
        seed(db)
    print("Datos iniciales cargados")
