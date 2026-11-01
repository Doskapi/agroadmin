from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.deps import DB, requiere
from app.models import Permiso, Rol, Usuario
from app.schemas import RolIn, RolOut, UsuarioIn, UsuarioOut, UsuarioUpdate
from app.security import PERMISOS, hash_password

router = APIRouter(tags=["usuarios"], dependencies=[requiere("usuarios:admin")])


def _roles(db: DB, nombres: list[str]) -> list[Rol]:
    roles = list(db.scalars(select(Rol).where(Rol.nombre.in_(nombres))))
    faltan = set(nombres) - {r.nombre for r in roles}
    if faltan:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Roles inexistentes: {sorted(faltan)}")
    return roles


@router.get("/usuarios", response_model=list[UsuarioOut])
def listar_usuarios(db: DB):
    return db.scalars(select(Usuario).order_by(Usuario.nombre)).all()


@router.post("/usuarios", response_model=UsuarioOut, status_code=201)
def crear_usuario(db: DB, data: UsuarioIn):
    email = data.email.lower()
    if db.scalar(select(Usuario).where(Usuario.email == email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Ya existe un usuario con ese email")
    usuario = Usuario(email=email, nombre=data.nombre, password_hash=hash_password(data.password),
                      roles=_roles(db, data.roles))
    db.add(usuario)
    db.commit()
    return usuario


@router.patch("/usuarios/{usuario_id}", response_model=UsuarioOut)
def editar_usuario(db: DB, usuario_id: int, data: UsuarioUpdate):
    usuario = db.get(Usuario, usuario_id)
    if not usuario:
        raise HTTPException(404, "Usuario no encontrado")
    if data.nombre is not None:
        usuario.nombre = data.nombre
    if data.password is not None:
        usuario.password_hash = hash_password(data.password)
    if data.activo is not None:
        usuario.activo = data.activo
    if data.roles is not None:
        usuario.roles = _roles(db, data.roles)
    db.commit()
    return usuario


@router.get("/roles", response_model=list[RolOut])
def listar_roles(db: DB):
    return db.scalars(select(Rol).order_by(Rol.nombre)).all()


@router.get("/permisos")
def listar_permisos() -> dict[str, str]:
    return PERMISOS


@router.put("/roles/{nombre}", response_model=RolOut)
def guardar_rol(db: DB, nombre: str, data: RolIn):
    """Crea o reemplaza un rol con la lista de permisos indicada."""
    invalidos = set(data.permisos) - set(PERMISOS)
    if invalidos:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Permisos inexistentes: {sorted(invalidos)}")
    rol = db.scalar(select(Rol).where(Rol.nombre == nombre)) or Rol(nombre=nombre)
    rol.descripcion = data.descripcion
    rol.permisos = list(db.scalars(select(Permiso).where(Permiso.codigo.in_(data.permisos))))
    db.add(rol)
    db.commit()
    return rol
