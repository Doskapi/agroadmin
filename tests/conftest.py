"""Los tests usan una base Postgres aparte (agro_test) y corren las migraciones reales."""

import os
import tempfile

_base = os.environ.get("DATABASE_URL", "postgresql+psycopg://agro:agro@localhost:5432/agro")
os.environ["DATABASE_URL"] = _base.rsplit("/", 1)[0] + "/agro_test"
os.environ["STORAGE_DIR"] = tempfile.mkdtemp()
os.environ["ANTHROPIC_API_KEY"] = ""
os.environ["ADMIN_EMAIL"] = "admin@test.com"
os.environ["ADMIN_PASSWORD"] = "admin-test-1234"

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402

from app.db import SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.seed import seed  # noqa: E402

TABLAS_DATOS = "factura_items, facturas, archivos, proveedores, cartas_porte, lotes, campos, campanias"


@pytest.fixture(scope="session", autouse=True)
def base_de_datos():
    admin = create_engine(_base, isolation_level="AUTOCOMMIT")
    with admin.connect() as c:
        c.execute(text("DROP DATABASE IF EXISTS agro_test WITH (FORCE)"))
        c.execute(text("CREATE DATABASE agro_test"))
    admin.dispose()
    command.upgrade(Config("alembic.ini"), "head")
    with SessionLocal() as db:
        seed(db)
    yield
    engine.dispose()


@pytest.fixture(autouse=True)
def limpiar():
    yield
    with engine.begin() as c:
        c.execute(text(f"TRUNCATE {TABLAS_DATOS} RESTART IDENTITY CASCADE"))
        c.execute(text("DELETE FROM usuarios WHERE email <> 'admin@test.com'"))


@pytest.fixture
def client():
    return TestClient(app)


def login(client, email, password) -> dict:
    r = client.post("/auth/login", data={"username": email, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture
def admin(client):
    return login(client, "admin@test.com", "admin-test-1234")
