import pymupdf
import pytest
from pydantic import ValidationError

from app.config import Settings
from tests.conftest import login
from tests.helpers import pdf_con_qr, png_qr, url_qr


def _importar(client, headers, data: bytes, nombre="f.pdf", tipo="application/pdf"):
    return client.post("/facturas/importar", headers=headers, files={"archivo": (nombre, data, tipo)})


# --- Configuración ----------------------------------------------------------


@pytest.mark.parametrize("clave", ["dev-inseguro-cambiar", "cambiar-por-una-clave-larga-y-aleatoria", "corta"])
def test_produccion_rechaza_secret_key_debil(clave):
    with pytest.raises(ValidationError, match="SECRET_KEY"):
        Settings(_env_file=None, entorno="produccion", secret_key=clave)


def test_desarrollo_acepta_valores_de_prueba():
    s = Settings(_env_file=None, entorno="desarrollo", secret_key="dev-inseguro-cambiar")
    assert s.secret_key == "dev-inseguro-cambiar"


def test_docs_ocultas(client):
    assert client.get("/docs").status_code == 404
    assert client.get("/openapi.json").status_code == 404


# --- Login ------------------------------------------------------------------


def test_bloqueo_por_intentos_fallidos(client):
    for _ in range(5):
        assert client.post("/auth/login", data={"username": "admin@test.com", "password": "mal"}).status_code == 401
    r = client.post("/auth/login", data={"username": "admin@test.com", "password": "admin-test-1234"})
    assert r.status_code == 429
    assert int(r.headers["Retry-After"]) > 0
    # otro usuario desde la misma IP todavía puede entrar
    assert client.post("/auth/login", data={"username": "otro@test.com", "password": "x"}).status_code == 401


def test_bloqueo_por_ip(client):
    for i in range(20):
        client.post("/auth/login", data={"username": f"u{i}@test.com", "password": "x"})
    r = client.post("/auth/login", data={"username": "admin@test.com", "password": "admin-test-1234"})
    assert r.status_code == 429
    # la IP la informa nginx; otra IP no está bloqueada
    r = client.post("/auth/login", data={"username": "admin@test.com", "password": "admin-test-1234"},
                    headers={"X-Real-IP": "10.0.0.99"})
    assert r.status_code == 200


def test_login_exitoso_reinicia_contador(client):
    for _ in range(4):
        client.post("/auth/login", data={"username": "admin@test.com", "password": "mal"})
    login(client, "admin@test.com", "admin-test-1234")
    for _ in range(4):
        client.post("/auth/login", data={"username": "admin@test.com", "password": "mal"})
    login(client, "admin@test.com", "admin-test-1234")


def test_password_debil_rechazada(client, admin):
    for clave in ("corta", "cambiar-esta-clave"):
        r = client.post("/usuarios", headers=admin,
                        json={"email": "x@test.com", "nombre": "x", "password": clave, "roles": []})
        assert r.status_code == 422, clave


# --- Último administrador ---------------------------------------------------


def _id_admin(client, admin):
    return client.get("/auth/yo", headers=admin).json()["id"]


def test_no_se_puede_desactivar_al_ultimo_admin(client, admin):
    uid = _id_admin(client, admin)
    assert client.patch(f"/usuarios/{uid}", headers=admin, json={"activo": False}).status_code == 409
    assert client.patch(f"/usuarios/{uid}", headers=admin, json={"roles": ["contador"]}).status_code == 409
    assert client.get("/auth/yo", headers=admin).json()["activo"] is True


def test_no_se_puede_quitar_el_permiso_de_admin_al_ultimo_rol(client, admin):
    r = client.put("/roles/admin", headers=admin, json={"nombre": "admin", "permisos": ["facturas:leer"]})
    assert r.status_code == 409
    assert "usuarios:admin" in client.get("/auth/yo", headers=admin).json()["permisos"]


def test_con_otro_admin_si_se_puede(client, admin):
    r = client.post("/usuarios", headers=admin, json={
        "email": "admin2@test.com", "nombre": "Otro", "password": "clave-segura-1", "roles": ["admin"]})
    assert r.status_code == 201
    uid = _id_admin(client, admin)
    assert client.patch(f"/usuarios/{uid}", headers=admin, json={"activo": False}).status_code == 200
    # se restaura para no afectar a los otros tests
    otro = login(client, "admin2@test.com", "clave-segura-1")
    assert client.patch(f"/usuarios/{uid}", headers=otro, json={"activo": True}).status_code == 200


# --- Archivos subidos -------------------------------------------------------


def test_tipo_se_detecta_por_contenido(client, admin):
    # un PNG que el navegador declara como PDF se guarda como imagen
    r = _importar(client, admin, png_qr(url_qr()), "factura.pdf", "application/pdf")
    assert r.status_code == 202
    fid = r.json()["id"]
    assert client.get(f"/facturas/{fid}/archivo", headers=admin).headers["content-type"] == "image/png"


def test_archivo_disfrazado_rechazado(client, admin):
    r = _importar(client, admin, b"<html><script>alert(1)</script></html>", "f.pdf", "application/pdf")
    assert r.status_code == 415


def test_pdf_danado(client, admin):
    assert _importar(client, admin, b"%PDF-1.7\nbasura").status_code == 422


def test_pdf_con_demasiadas_paginas(client, admin):
    doc = pymupdf.open()
    for _ in range(31):
        doc.new_page()
    assert _importar(client, admin, doc.tobytes()).status_code == 422


def test_pdf_con_contrasena(client, admin):
    doc = pymupdf.open(stream=pdf_con_qr(url_qr()), filetype="pdf")
    data = doc.tobytes(encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw="1234", owner_pw="1234")
    r = _importar(client, admin, data)
    assert r.status_code == 422
    assert "contraseña" in r.json()["detail"]


def test_archivo_demasiado_grande(client, admin, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "max_upload_mb", 1)
    assert _importar(client, admin, b"%PDF-" + b"0" * (1024 * 1024)).status_code == 413
