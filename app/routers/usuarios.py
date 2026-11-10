from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func, select

from app import sesiones
from app.auditoria import auditar, diferencias
from app.deps import DB, requiere
from app.models import Permiso, Rol, Usuario, rol_permisos, usuario_roles
from app.schemas import RolIn, RolOut, UsuarioIn, UsuarioOut, UsuarioUpdate
from app.security import PERMISOS, hash_password

router = APIRouter(tags=["usuarios"])
ADMIN = requiere("usuarios:admin")


def _roles(db: DB, nombres: list[str]) -> list[Rol]:
    roles = list(db.scalars(select(Rol).where(Rol.nombre.in_(nombres))))
    faltan = set(nombres) - {r.nombre for r in roles}
    if faltan:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Roles inexistentes: {sorted(faltan)}")
    return roles


def _commit_sin_perder_admin(db: DB) -> None:
    """Guarda los cambios salvo que dejen al sistema sin ningún usuario activo que pueda administrar."""
    db.flush()
    admins = db.scalar(
        select(func.count(func.distinct(Usuario.id)))
        .join(usuario_roles, usuario_roles.c.usuario_id == Usuario.id)
        .join(rol_permisos, rol_permisos.c.rol_id == usuario_roles.c.rol_id)
        .where(Usuario.activo, rol_permisos.c.permiso_codigo == "usuarios:admin")
    )
    if not admins:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "El cambio dejaría al sistema sin ningún administrador activo")
    db.commit()


@router.get("/usuarios", response_model=list[UsuarioOut], dependencies=[ADMIN])
def listar_usuarios(db: DB):
    return db.scalars(select(Usuario).order_by(Usuario.nombre)).all()


@router.post("/usuarios", response_model=UsuarioOut, status_code=201)
def crear_usuario(db: DB, data: UsuarioIn, admin: Usuario = ADMIN):
    email = data.email.lower()
    if db.scalar(select(Usuario).where(Usuario.email == email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Ya existe un usuario con ese email")
    usuario = Usuario(email=email, nombre=data.nombre, password_hash=hash_password(data.password),
                      roles=_roles(db, data.roles))
    db.add(usuario)
    db.flush()
    auditar(db, admin.id, "usuario_creado", "usuario", usuario.id, email=email, roles=data.roles)
    db.commit()
    return usuario


@router.patch("/usuarios/{usuario_id}", response_model=UsuarioOut)
def editar_usuario(db: DB, usuario_id: int, data: UsuarioUpdate, admin: Usuario = ADMIN):
    usuario = db.get(Usuario, usuario_id)
    if not usuario:
        raise HTTPException(404, "Usuario no encontrado")
    cambios = diferencias(usuario, data.model_dump(exclude_unset=True, exclude={"password", "roles"}))
    if data.roles is not None and sorted(data.roles) != sorted(r.nombre for r in usuario.roles):
        cambios["roles"] = [sorted(r.nombre for r in usuario.roles), sorted(data.roles)]
    if data.password is not None:
        cambios["password"] = "cambiada"
    # Al desactivar o cambiarle la contraseña, se le cierran todas las sesiones
    if data.activo is False or data.password is not None:
        sesiones.revocar(db, usuario.id)
    if data.nombre is not None:
        usuario.nombre = data.nombre
    if data.password is not None:
        usuario.password_hash = hash_password(data.password)
    if data.activo is not None:
        usuario.activo = data.activo
    if data.roles is not None:
        usuario.roles = _roles(db, data.roles)
    if cambios:
        auditar(db, admin.id, "usuario_editado", "usuario", usuario.id, cambios=cambios)
    _commit_sin_perder_admin(db)
    return usuario


@router.post("/usuarios/{usuario_id}/2fa/reiniciar", response_model=UsuarioOut)
def reiniciar_2fa(db: DB, usuario_id: int, admin: Usuario = ADMIN):
    """Para quien perdió el celular: borra su verificación en dos pasos (la vuelve a configurar al entrar)
    y le cierra las sesiones."""
    usuario = db.get(Usuario, usuario_id)
    if not usuario:
        raise HTTPException(404, "Usuario no encontrado")
    usuario.totp_activo = False
    usuario.totp_secreto = None
    usuario.totp_ultimo_paso = None
    sesiones.revocar(db, usuario.id)
    auditar(db, admin.id, "2fa_reiniciada", "usuario", usuario.id)
    db.commit()
    return usuario


@router.get("/roles", response_model=list[RolOut], dependencies=[ADMIN])
def listar_roles(db: DB):
    return db.scalars(select(Rol).order_by(Rol.nombre)).all()


@router.get("/permisos", dependencies=[ADMIN])
def listar_permisos() -> dict[str, str]:
    return PERMISOS


@router.put("/roles/{nombre}", response_model=RolOut)
def guardar_rol(db: DB, nombre: str, data: RolIn, admin: Usuario = ADMIN):
    """Crea o reemplaza un rol con la lista de permisos indicada."""
    invalidos = set(data.permisos) - set(PERMISOS)
    if invalidos:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Permisos inexistentes: {sorted(invalidos)}")
    rol = db.scalar(select(Rol).where(Rol.nombre == nombre)) or Rol(nombre=nombre)
    antes = sorted(p.codigo for p in rol.permisos) if rol.id else []
    auditar(db, admin.id, "rol_guardado", "rol", nombre, permisos=[antes, sorted(data.permisos)])
    rol.descripcion = data.descripcion
    rol.permisos = list(db.scalars(select(Permiso).where(Permiso.codigo.in_(data.permisos))))
    db.add(rol)
    _commit_sin_perder_admin(db)
    return rol
