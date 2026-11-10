"""Carga inicial idempotente: permisos, roles, categorías y usuario admin.

Uso: python -m app.seed
"""

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.config import password_debil, settings
from app.db import SessionLocal
from app.models import Categoria, Permiso, Rol, Usuario
from app.security import PERMISOS, ROLES_INICIALES, hash_password

CATEGORIAS = [
    "semillas", "agroquimicos", "fertilizantes", "combustible", "fletes", "servicios",
    "maquinaria", "repuestos", "honorarios", "arrendamiento", "otros",
]


def seed(db: Session) -> None:
    existentes = {p.codigo: p for p in db.scalars(select(Permiso))}
    nuevos = set()
    for codigo, desc in PERMISOS.items():
        if codigo in existentes:
            existentes[codigo].descripcion = desc
        else:
            db.add(Permiso(codigo=codigo, descripcion=desc))
            nuevos.add(codigo)
    db.flush()

    permisos = {p.codigo: p for p in db.scalars(select(Permiso))}
    for nombre, (desc, codigos) in ROLES_INICIALES.items():
        rol = db.scalar(select(Rol).where(Rol.nombre == nombre))
        if not rol:
            db.add(Rol(nombre=nombre, descripcion=desc, permisos=[permisos[c] for c in codigos]))
        elif existentes:
            # Permisos que se agregaron al sistema en esta versión: se suman a los roles iniciales que los llevan
            # (si alguien los quitó de un rol después, no se vuelven a agregar).
            rol.permisos += [permisos[c] for c in codigos if c in nuevos]
    # El rol admin siempre tiene todos los permisos, incluidos los que se agreguen en el futuro.
    db.flush()
    admin_rol = db.scalar(select(Rol).where(Rol.nombre == "admin"))
    admin_rol.permisos = list(permisos.values())

    for nombre in CATEGORIAS:
        if not db.scalar(select(Categoria).where(Categoria.nombre == nombre)):
            db.add(Categoria(nombre=nombre))

    email = settings.admin_email.lower()
    if not db.scalar(select(Usuario).where(Usuario.email == email)):
        if settings.es_produccion and (motivo := password_debil(settings.admin_password)):
            raise SystemExit(f"ADMIN_PASSWORD {motivo}. Cambiala en el .env antes de crear el administrador.")
        db.add(Usuario(email=email, nombre="Administrador", password_hash=hash_password(settings.admin_password),
                       roles=[admin_rol]))
    db.commit()
    if settings.lector_db_password:
        crear_lector(db, settings.lector_db_password)


# Tablas con datos sensibles que el usuario de solo lectura no ve (de `usuarios` solo ve algunas columnas).
TABLAS_PRIVADAS = ["usuarios", "sesiones", "tokens_recuperacion", "alembic_version"]


def crear_lector(db: Session, password: str) -> None:
    """Crea (o actualiza) el rol `lector` de Postgres, de solo lectura, para Metabase u otras herramientas."""
    db.execute(text("""
        DO $$ BEGIN
            IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'lector') THEN CREATE ROLE lector LOGIN; END IF;
        END $$"""))
    # ALTER ROLE no acepta parámetros: se arma con format() y %L para escapar la contraseña
    sql = db.scalar(text("SELECT format('ALTER ROLE lector WITH LOGIN PASSWORD %L', CAST(:p AS text))"), {"p": password})
    db.execute(text(sql))
    base = db.scalar(text("SELECT current_database()"))
    for s in [
        f'GRANT CONNECT ON DATABASE "{base}" TO lector',
        "GRANT USAGE ON SCHEMA public TO lector",
        "GRANT SELECT ON ALL TABLES IN SCHEMA public TO lector",
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO lector",
        *[f"REVOKE ALL ON TABLE {t} FROM lector" for t in TABLAS_PRIVADAS],
        "GRANT SELECT (id, nombre, email, activo) ON TABLE usuarios TO lector",
    ]:
        db.execute(text(s))
    db.commit()


if __name__ == "__main__":
    with SessionLocal() as db:
        seed(db)
    print("Datos iniciales cargados")
