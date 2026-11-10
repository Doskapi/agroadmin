"""Recorre TODAS las rutas de la API y verifica que exijan sesión y el permiso que corresponde.

Si se agrega un endpoint sin protección, este test falla.
"""

import re

import pytest
from fastapi import routing

from app.main import app
from tests.conftest import login

# Rutas que se usan sin sesión
PUBLICAS = {"/salud", "/docs", "/openapi.json", "/auth/login", "/auth/login/2fa", "/auth/recuperar", "/auth/restablecer"}
# Rutas que solo exigen sesión (cualquier usuario): las de la propia cuenta
SOLO_SESION = {"/auth/logout", "/auth/yo", "/auth/sesiones", "/auth/sesiones/{sesion_id}", "/auth/sesiones/cerrar-otras",
               "/auth/cambiar-password", "/auth/2fa/iniciar", "/auth/2fa/activar", "/auth/2fa/desactivar"}


def _permisos(dependant) -> set[str]:
    out = set()
    for d in dependant.dependencies:
        if p := getattr(d.call, "permiso", None):
            out.add(p)
        out |= _permisos(d)
    return out


def _rutas():
    # FastAPI >= 0.16x envuelve los routers incluidos; iter_route_contexts devuelve las rutas efectivas
    if hasattr(routing, "iter_route_contexts"):
        return [r for r in routing.iter_route_contexts(app.routes) if hasattr(r, "dependant")]
    return [r for r in app.routes if isinstance(r, routing.APIRoute)]


RUTAS = [(m, r.path, _permisos(r.dependant)) for r in _rutas() for m in sorted(r.methods - {"HEAD"})]


def test_se_encontraron_las_rutas():
    assert len(RUTAS) > 60  # si cambia la forma de listar rutas, que falle en vez de no revisar nada


def _url(path: str) -> str:
    return re.sub(r"\{[^}]+\}", "1", path)


def test_todas_las_rutas_estan_clasificadas():
    """Cada ruta es pública, de la propia cuenta, o exige un permiso (salvo /facturas/acciones, que lo
    controla adentro según la acción)."""
    sin_clasificar = [(m, p) for m, p, perms in RUTAS
                      if not perms and p not in PUBLICAS | SOLO_SESION and p != "/facturas/acciones"]
    assert sin_clasificar == []


@pytest.mark.parametrize("metodo,path,permisos", [r for r in RUTAS if r[1] not in PUBLICAS],
                         ids=[f"{m} {p}" for m, p, _ in RUTAS if p not in PUBLICAS])
def test_sin_sesion_401(client, metodo, path, permisos):
    assert client.request(metodo, _url(path)).status_code == 401


@pytest.mark.parametrize("metodo,path,permisos", [r for r in RUTAS if r[2]],
                         ids=[f"{m} {p}" for m, p, perms in RUTAS if perms])
def test_sin_el_permiso_403(client, admin, metodo, path, permisos):
    client.post("/usuarios", headers=admin, json={"email": "nadie@test.com", "nombre": "Sin rol",
                                                   "password": "clave-segura-1", "roles": []})
    h = login(client, "nadie@test.com", "clave-segura-1")
    r = client.request(metodo, _url(path), headers=h, json={})
    assert r.status_code == 403, r.text
    assert any(p in r.json()["detail"] for p in permisos)
