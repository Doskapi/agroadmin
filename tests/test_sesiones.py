"""Fase 3: sesiones revocables con cookie, CSRF, contraseña, verificación en dos pasos y auditoría."""

import time

import pyotp
import pytest
from sqlalchemy import text

from app import correo
from app.config import settings
from app.db import engine
from tests.conftest import login
from tests.helpers import importar, pdf_con_qr, url_qr

ADMIN = ("admin@test.com", "admin-test-1234")


def _crear(client, admin, email="ana@test.com", rol="administrativo", password="clave-segura-1"):
    r = client.post("/usuarios", headers=admin, json={"email": email, "nombre": "Ana", "password": password,
                                                      "roles": [rol]})
    assert r.status_code == 201, r.text
    return r.json()


# --- Cookie y CSRF --------------------------------------------------------------


def test_login_de_navegador_usa_cookie(client):
    r = client.post("/auth/login", data={"username": ADMIN[0], "password": ADMIN[1]},
                    headers={"X-Requested-With": "agroadmin"})
    assert r.status_code == 200
    assert r.json()["access_token"] is None  # el navegador no recibe el token en el cuerpo
    cookie = r.headers["set-cookie"]
    assert "agro_sesion=" in cookie and "HttpOnly" in cookie and "SameSite=strict" in cookie and "Path=/api" in cookie
    assert "Secure" not in cookie  # el pedido fue por http
    r = client.post("/auth/login", data={"username": ADMIN[0], "password": ADMIN[1]},
                    headers={"X-Requested-With": "agroadmin", "X-Forwarded-Proto": "https"})
    assert "Secure" in r.headers["set-cookie"]


def test_cookie_exige_header_csrf_en_escrituras(client):
    r = client.post("/auth/login", data={"username": ADMIN[0], "password": ADMIN[1]},
                    headers={"X-Requested-With": "agroadmin"})
    token = r.cookies["agro_sesion"]
    cookies = {"agro_sesion": token}
    assert client.get("/auth/yo", cookies=cookies).status_code == 200
    r = client.post("/categorias", cookies=cookies, json={"nombre": "nueva"})
    assert r.status_code == 403 and "X-Requested-With" in r.json()["detail"]
    r = client.post("/categorias", cookies=cookies, json={"nombre": "nueva"}, headers={"X-Requested-With": "x"})
    assert r.status_code == 201


# --- Sesiones -----------------------------------------------------------------------


def test_logout_revoca_el_token(client, admin):
    assert client.post("/auth/logout", headers=admin).status_code == 204
    assert client.get("/auth/yo", headers=admin).status_code == 401


def test_cerrar_otras_sesiones(client, admin):
    otra = login(client, *ADMIN)
    sesiones = client.get("/auth/sesiones", headers=admin).json()
    assert len(sesiones) == 2
    assert sum(s["actual"] for s in sesiones) == 1
    assert client.post("/auth/sesiones/cerrar-otras", headers=admin).json() == {"cerradas": 1}
    assert client.get("/auth/yo", headers=otra).status_code == 401
    assert client.get("/auth/yo", headers=admin).status_code == 200


def test_cerrar_una_sesion_de_otro_usuario_no_se_puede(client, admin):
    _crear(client, admin)
    ana = login(client, "ana@test.com", "clave-segura-1")
    id_ana = client.get("/auth/sesiones", headers=ana).json()[0]["id"]
    assert client.delete(f"/auth/sesiones/{id_ana}", headers=admin).status_code == 404
    assert client.get("/auth/yo", headers=ana).status_code == 200


def test_sesion_vence_por_inactividad(client, admin):
    with engine.begin() as c:
        c.execute(text("UPDATE sesiones SET ultima_actividad = now() - interval '9 hours'"))
    assert client.get("/auth/yo", headers=admin).status_code == 401


def test_desactivar_usuario_cierra_sus_sesiones(client, admin):
    u = _crear(client, admin)
    ana = login(client, "ana@test.com", "clave-segura-1")
    client.patch(f"/usuarios/{u['id']}", headers=admin, json={"activo": False})
    client.patch(f"/usuarios/{u['id']}", headers=admin, json={"activo": True})
    assert client.get("/auth/yo", headers=ana).status_code == 401


# --- Contraseña ----------------------------------------------------------------------


def test_cambiar_password_cierra_las_otras_sesiones(client, admin):
    _crear(client, admin)
    ana = login(client, "ana@test.com", "clave-segura-1")
    ana2 = login(client, "ana@test.com", "clave-segura-1")
    r = client.post("/auth/cambiar-password", headers=ana, json={"actual": "mal", "nueva": "otra-clave-larga"})
    assert r.status_code == 422
    r = client.post("/auth/cambiar-password", headers=ana, json={"actual": "clave-segura-1", "nueva": "otra-clave-larga"})
    assert r.status_code == 204
    assert client.get("/auth/yo", headers=ana).status_code == 200
    assert client.get("/auth/yo", headers=ana2).status_code == 401
    login(client, "ana@test.com", "otra-clave-larga")


def test_recuperar_password(client, admin, monkeypatch):
    _crear(client, admin)
    enviados = []
    monkeypatch.setattr(correo, "enviar", lambda destino, asunto, texto: enviados.append((destino, texto)) or True)

    r = client.post("/auth/recuperar", json={"email": "nadie@test.com"})
    assert r.status_code == 202
    assert enviados == []  # misma respuesta, pero sin correo
    r2 = client.post("/auth/recuperar", json={"email": "ANA@test.com"})
    assert r2.json() == r.json()
    destino, texto = enviados[0]
    assert destino == "ana@test.com"
    token = texto.split("token=")[1].split()[0]

    assert client.post("/auth/restablecer", json={"token": "x", "nueva": "nueva-clave-123"}).status_code == 422
    assert client.post("/auth/restablecer", json={"token": token, "nueva": "nueva-clave-123"}).status_code == 204
    login(client, "ana@test.com", "nueva-clave-123")
    # el link es de un solo uso
    assert client.post("/auth/restablecer", json={"token": token, "nueva": "otra-clave-123"}).status_code == 422


# --- Verificación en dos pasos ----------------------------------------------------------


def _activar_2fa(client, headers) -> pyotp.TOTP:
    r = client.post("/auth/2fa/iniciar", headers=headers).json()
    assert r["uri"].startswith("otpauth://totp/")
    assert len(r["qr_png"]) > 100
    totp = pyotp.TOTP(r["secreto"])
    assert client.post("/auth/2fa/activar", headers=headers, json={"codigo": "000000"}).status_code == 422
    assert client.post("/auth/2fa/activar", headers=headers, json={"codigo": totp.now()}).status_code == 204
    return totp


def _codigo_siguiente(totp: pyotp.TOTP) -> str:
    # El código ya usado no se acepta de nuevo: usamos el del próximo intervalo (se acepta ±1 paso)
    return totp.at(time.time() + totp.interval)


def test_login_con_2fa(client, admin):
    _crear(client, admin)
    ana = login(client, "ana@test.com", "clave-segura-1")
    totp = _activar_2fa(client, ana)

    r = client.post("/auth/login", data={"username": "ana@test.com", "password": "clave-segura-1"}).json()
    assert r["requiere_2fa"] and r["access_token"] is None
    assert client.post("/auth/login/2fa", json={"desafio": r["desafio"], "codigo": "123456"}).status_code == 401
    assert client.post("/auth/login/2fa", json={"desafio": r["desafio"] + "x", "codigo": totp.now()}).status_code == 401
    ok = client.post("/auth/login/2fa", json={"desafio": r["desafio"], "codigo": _codigo_siguiente(totp)})
    assert ok.status_code == 200
    h = {"Authorization": f"Bearer {ok.json()['access_token']}"}
    assert client.get("/auth/yo", headers=h).json()["totp_activo"] is True
    # el mismo código no sirve dos veces
    r = client.post("/auth/login", data={"username": "ana@test.com", "password": "clave-segura-1"}).json()
    assert client.post("/auth/login/2fa", json={"desafio": r["desafio"], "codigo": _codigo_siguiente(totp)}).status_code == 401


def test_2fa_obligatoria_por_rol(client, admin, monkeypatch):
    _crear(client, admin, rol="contador")
    conta = login(client, "ana@test.com", "clave-segura-1")
    monkeypatch.setattr(settings, "exigir_2fa", "facturas:confirmar")
    assert client.get("/auth/yo", headers=conta).json()["debe_activar_2fa"] is True
    r = client.get("/facturas", headers=conta)
    assert r.status_code == 403 and "dos pasos" in r.json()["detail"]
    totp = _activar_2fa(client, conta)
    assert client.get("/facturas", headers=conta).status_code == 200
    # no la puede desactivar
    r = client.post("/auth/2fa/desactivar", headers=conta,
                    json={"password": "clave-segura-1", "codigo": _codigo_siguiente(totp)})
    assert r.status_code == 409


def test_admin_reinicia_2fa(client, admin):
    u = _crear(client, admin)
    ana = login(client, "ana@test.com", "clave-segura-1")
    _activar_2fa(client, ana)
    r = client.post(f"/usuarios/{u['id']}/2fa/reiniciar", headers=admin)
    assert r.json()["totp_activo"] is False
    assert client.get("/auth/yo", headers=ana).status_code == 401  # se le cerraron las sesiones
    login(client, "ana@test.com", "clave-segura-1")  # entra sin código


# --- Auditoría ---------------------------------------------------------------------------


def test_auditoria_de_factura(client, admin):
    fid = importar(client, admin, pdf_con_qr(url_qr())).json()["id"]
    client.patch(f"/facturas/{fid}", headers=admin, json={"observaciones": "revisada", "total": 121000.5})
    assert client.post(f"/facturas/{fid}/anular", headers=admin, json={}).status_code == 422  # falta el motivo
    assert client.post(f"/facturas/{fid}/anular", headers=admin, json={"motivo": "duplicada en papel"}).status_code == 200

    hist = client.get(f"/facturas/{fid}/historial", headers=admin).json()
    assert [h["accion"] for h in hist] == ["factura_creada", "factura_procesada", "factura_editada", "factura_anulada"]
    editada = hist[2]
    assert editada["usuario"] == "Administrador"
    assert editada["detalle"]["cambios"] == {"observaciones": [None, "revisada"]}  # el total no cambió
    assert hist[3]["detalle"]["motivo"] == "duplicada en papel"
    assert hist[1]["usuario_id"] is None  # lo hizo el sistema


def test_auditoria_logins_y_permisos(client, admin):
    client.post("/auth/login", data={"username": "admin@test.com", "password": "mal"})
    u = _crear(client, admin, rol="campo")
    campo = login(client, "ana@test.com", "clave-segura-1")
    assert client.get("/auditoria", headers=campo).status_code == 403

    r = client.get("/auditoria?accion=login_fallido", headers=admin).json()
    assert r["total"] == 1
    assert r["items"][0]["detalle"] == {"email": "admin@test.com"}
    creado = client.get(f"/auditoria?entidad=usuario&entidad_id={u['id']}", headers=admin).json()["items"]
    assert "usuario_creado" in [x["accion"] for x in creado]
    assert "login_fallido" in client.get("/auditoria/acciones", headers=admin).json()


def test_contador_ve_la_auditoria(client, admin):
    _crear(client, admin, rol="contador")
    conta = login(client, "ana@test.com", "clave-segura-1")
    assert client.get("/auditoria", headers=conta).status_code == 200


# --- Usuario de solo lectura ----------------------------------------------------------


def test_usuario_lector(client):
    from sqlalchemy import create_engine

    from app.db import SessionLocal
    from app.seed import crear_lector

    with SessionLocal() as db:
        crear_lector(db, "clave'con-comilla")
    url = engine.url.set(username="lector", password="clave'con-comilla")
    lector = create_engine(url)
    with lector.connect() as c:
        assert c.execute(text("SELECT count(*) FROM facturas")).scalar() == 0
        assert c.execute(text("SELECT email FROM usuarios")).scalars().all() == ["admin@test.com"]
        with pytest.raises(Exception, match="permission denied"):
            c.execute(text("SELECT password_hash FROM usuarios"))
        c.rollback()
        with pytest.raises(Exception, match="permission denied"):
            c.execute(text("SELECT * FROM sesiones"))
        c.rollback()
        with pytest.raises(Exception, match="permission denied"):
            c.execute(text("INSERT INTO categorias (nombre) VALUES ('x')"))
    lector.dispose()
