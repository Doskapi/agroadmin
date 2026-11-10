"""Login, sesiones, cambio y recuperación de contraseña, y verificación en dos pasos."""

import hashlib
import logging
import secrets
from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select

from app import correo, dos_pasos, limite_login, sesiones
from app.auditoria import auditar
from app.config import settings
from app.deps import DB, SesionActual, UsuarioSin2FA
from app.models import Sesion, TokenRecuperacion, Usuario
from app.schemas import (
    CambiarPassword,
    CodigoIn,
    Desactivar2FA,
    Inicio2FA,
    Login2FA,
    LoginOut,
    Recuperar,
    Restablecer,
    SesionOut,
    UsuarioYo,
)
from app.security import hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])
log = logging.getLogger(__name__)

# Se verifica contra este hash cuando el email no existe, para que la respuesta tarde lo mismo
# y no se pueda averiguar qué emails tienen cuenta.
_HASH_FICTICIO = hash_password("no-es-una-clave-real")
VIGENCIA_RECUPERACION = timedelta(hours=1)


def ip_cliente(request: Request) -> str:
    # La API solo es accesible a través de nginx, que pone X-Real-IP con la IP del cliente.
    return request.headers.get("x-real-ip") or (request.client.host if request.client else "desconocida")


def _bloqueo(email: str, ip: str) -> None:
    if espera := limite_login.segundos_de_bloqueo(email, ip):
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"Demasiados intentos fallidos. Probá de nuevo en {(espera + 59) // 60} minuto(s)",
            headers={"Retry-After": str(espera)},
        )


def _iniciar_sesion(db: DB, request: Request, response: Response, usuario: Usuario) -> LoginOut:
    token = sesiones.crear(db, usuario.id)
    auditar(db, usuario.id, "login", "usuario", usuario.id)
    db.commit()
    sesiones.poner_cookie(response, request, token)
    limite_login.registrar_exito(usuario.email)
    # El navegador usa la cookie httpOnly; el token en el cuerpo es para clientes de la API (sin X-Requested-With).
    navegador = bool(request.headers.get(sesiones.HEADER_CSRF))
    return LoginOut(access_token=None if navegador else token)


@router.post("/login", response_model=LoginOut)
def login(db: DB, request: Request, response: Response, form: Annotated[OAuth2PasswordRequestForm, Depends()]):
    """Login con email (campo `username`) y contraseña. Si el usuario tiene verificación en dos pasos,
    responde `requiere_2fa` y un `desafio` para mandar a `/auth/login/2fa` junto con el código."""
    email = form.username.strip().lower()
    ip = ip_cliente(request)
    _bloqueo(email, ip)

    usuario = db.scalar(select(Usuario).where(Usuario.email == email))
    password_ok = verify_password(form.password, usuario.password_hash if usuario else _HASH_FICTICIO)
    if not usuario or not usuario.activo or not password_ok:
        limite_login.registrar_fallo(email, ip)
        auditar(db, usuario.id if usuario else None, "login_fallido", "usuario", usuario.id if usuario else None,
                email=email)
        db.commit()
        log.warning("Login fallido para %s desde %s", email, ip)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Email o contraseña incorrectos")

    if usuario.totp_activo:
        return LoginOut(requiere_2fa=True, desafio=dos_pasos.crear_desafio(usuario.id))
    return _iniciar_sesion(db, request, response, usuario)


@router.post("/login/2fa", response_model=LoginOut)
def login_2fa(db: DB, request: Request, response: Response, data: Login2FA):
    usuario_id = dos_pasos.leer_desafio(data.desafio)
    usuario = db.get(Usuario, usuario_id) if usuario_id else None
    if not usuario or not usuario.activo:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "El tiempo para ingresar el código venció. Volvé a empezar")
    ip = ip_cliente(request)
    _bloqueo(usuario.email, ip)
    if not dos_pasos.verificar(usuario, data.codigo):
        limite_login.registrar_fallo(usuario.email, ip)
        auditar(db, usuario.id, "login_fallido", "usuario", usuario.id, motivo="código 2FA incorrecto")
        db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Código incorrecto")
    return _iniciar_sesion(db, request, response, usuario)


@router.post("/logout", status_code=204)
def logout(db: DB, response: Response, sesion: SesionActual):
    sesiones.revocar(db, sesion.usuario_id, solo=sesion.id)
    auditar(db, sesion.usuario_id, "logout", "usuario", sesion.usuario_id)
    db.commit()
    sesiones.borrar_cookie(response)


@router.get("/yo", response_model=UsuarioYo)
def yo(usuario: UsuarioSin2FA):
    return UsuarioYo.model_validate(usuario).model_copy(update={"debe_activar_2fa": dos_pasos.debe_activar(usuario)})


# --- Sesiones ------------------------------------------------------------------


@router.get("/sesiones", response_model=list[SesionOut])
def mis_sesiones(db: DB, sesion: SesionActual):
    filas = db.scalars(
        select(Sesion).where(Sesion.usuario_id == sesion.usuario_id, Sesion.revocada.is_(None),
                             Sesion.expira > sesiones.ahora(),
                             Sesion.ultima_actividad > sesiones.ahora() - timedelta(minutes=settings.access_token_minutes))
        .order_by(Sesion.ultima_actividad.desc())
    ).all()
    return [SesionOut.model_validate(s).model_copy(update={"actual": s.id == sesion.id}) for s in filas]


@router.delete("/sesiones/{sesion_id}", status_code=204)
def cerrar_sesion(db: DB, sesion_id: int, sesion: SesionActual):
    if not sesiones.revocar(db, sesion.usuario_id, solo=sesion_id):
        raise HTTPException(404, "Sesión no encontrada")
    auditar(db, sesion.usuario_id, "sesion_cerrada", "usuario", sesion.usuario_id, sesion=sesion_id)
    db.commit()


@router.post("/sesiones/cerrar-otras")
def cerrar_otras(db: DB, sesion: SesionActual) -> dict[str, int]:
    n = sesiones.revocar(db, sesion.usuario_id, excepto=sesion.id)
    auditar(db, sesion.usuario_id, "sesiones_cerradas", "usuario", sesion.usuario_id, cantidad=n)
    db.commit()
    return {"cerradas": n}


# --- Contraseña ------------------------------------------------------------------


@router.post("/cambiar-password", status_code=204)
def cambiar_password(db: DB, data: CambiarPassword, usuario: UsuarioSin2FA, sesion: SesionActual):
    """Cambia la contraseña propia y cierra las demás sesiones."""
    if not verify_password(data.actual, usuario.password_hash):
        raise HTTPException(422, "La contraseña actual no es correcta")
    usuario.password_hash = hash_password(data.nueva)
    sesiones.revocar(db, usuario.id, excepto=sesion.id)
    auditar(db, usuario.id, "password_cambiada", "usuario", usuario.id)
    db.commit()


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


@router.post("/recuperar", status_code=202)
def recuperar(db: DB, request: Request, data: Recuperar) -> dict[str, str]:
    """Manda por correo un link para elegir una contraseña nueva (vale 1 hora). Responde lo mismo exista
    o no el email, para no revelar qué cuentas existen."""
    email = data.email.strip().lower()
    _bloqueo(email, ip_cliente(request))
    limite_login.registrar_fallo(email, ip_cliente(request))  # cuenta como intento: evita usarlo para spamear
    usuario = db.scalar(select(Usuario).where(Usuario.email == email))
    if usuario and usuario.activo:
        token = secrets.token_urlsafe(32)
        db.add(TokenRecuperacion(token_hash=_hash_token(token), usuario_id=usuario.id,
                                 expira=sesiones.ahora() + VIGENCIA_RECUPERACION))
        auditar(db, usuario.id, "recuperacion_pedida", "usuario", usuario.id)
        db.commit()
        link = f"{settings.url_publica.rstrip('/')}/restablecer?token={token}"
        correo.enviar(usuario.email, "Restablecer tu contraseña de Gestión Agro",
                      f"Hola {usuario.nombre}:\n\nPara elegir una contraseña nueva entrá a este link (vale 1 hora):\n"
                      f"{link}\n\nSi no lo pediste vos, ignorá este correo.")
    return {"detail": "Si el email corresponde a una cuenta, te enviamos un link para restablecer la contraseña."}


@router.post("/restablecer", status_code=204)
def restablecer(db: DB, data: Restablecer):
    tok = db.scalar(select(TokenRecuperacion).where(TokenRecuperacion.token_hash == _hash_token(data.token)))
    if not tok or tok.usado or tok.expira <= sesiones.ahora():
        raise HTTPException(422, "El link no es válido o ya venció. Pedí uno nuevo")
    usuario = db.get(Usuario, tok.usuario_id)
    usuario.password_hash = hash_password(data.nueva)
    tok.usado = sesiones.ahora()
    sesiones.revocar(db, usuario.id)
    auditar(db, usuario.id, "password_restablecida", "usuario", usuario.id)
    db.commit()


# --- Verificación en dos pasos --------------------------------------------------------


@router.post("/2fa/iniciar", response_model=Inicio2FA)
def iniciar_2fa(db: DB, usuario: UsuarioSin2FA):
    """Genera un secreto nuevo. Queda pendiente hasta confirmar un código con `/auth/2fa/activar`."""
    if usuario.totp_activo:
        raise HTTPException(409, "La verificación en dos pasos ya está activa")
    usuario.totp_secreto = dos_pasos.nuevo_secreto()
    usuario.totp_ultimo_paso = None
    db.commit()
    uri = dos_pasos.uri(usuario)
    return Inicio2FA(secreto=usuario.totp_secreto, uri=uri, qr_png=dos_pasos.qr_png(uri))


@router.post("/2fa/activar", status_code=204)
def activar_2fa(db: DB, data: CodigoIn, usuario: UsuarioSin2FA):
    if usuario.totp_activo:
        raise HTTPException(409, "La verificación en dos pasos ya está activa")
    if not dos_pasos.verificar(usuario, data.codigo):
        raise HTTPException(422, "Código incorrecto. Revisá que la hora del celular esté bien")
    usuario.totp_activo = True
    auditar(db, usuario.id, "2fa_activada", "usuario", usuario.id)
    db.commit()


@router.post("/2fa/desactivar", status_code=204)
def desactivar_2fa(db: DB, data: Desactivar2FA, usuario: UsuarioSin2FA):
    if not verify_password(data.password, usuario.password_hash) or not dos_pasos.verificar(usuario, data.codigo):
        raise HTTPException(422, "Contraseña o código incorrectos")
    if usuario.permisos & settings.permisos_con_2fa:
        raise HTTPException(409, "Tu rol exige verificación en dos pasos: no se puede desactivar")
    usuario.totp_activo = False
    usuario.totp_secreto = None
    auditar(db, usuario.id, "2fa_desactivada", "usuario", usuario.id)
    db.commit()
