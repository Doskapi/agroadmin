"""Fase 4: cola de trabajos, worker, tareas programadas, salud y logs."""

import json
import logging
from datetime import timedelta

from sqlalchemy import select, text

from app import trabajos, worker
from app.db import SessionLocal, engine
from app.extraccion import ia
from app.logs import FormatoJSON
from app.models import EstadoTrabajo, Factura, TareaProgramada, Trabajo
from app.sesiones import ahora
from tests.helpers import pdf_con_qr, png_qr, procesar_cola, url_qr


def _subir(client, admin, data=None, nombre="f.pdf", tipo="application/pdf"):
    r = client.post("/facturas/importar", headers=admin, files={"archivo": (nombre, data or pdf_con_qr(url_qr()), tipo)})
    assert r.status_code == 202, r.text
    return r.json()["id"]


def _trabajo(fid) -> Trabajo:
    with SessionLocal() as db:
        return db.scalar(select(Trabajo).where(Trabajo.payload["factura_id"].as_integer() == fid))


def test_importar_encola_y_el_worker_procesa(client, admin):
    fid = _subir(client, admin)
    assert client.get(f"/facturas/{fid}", headers=admin).json()["estado"] == "procesando"
    assert _trabajo(fid).estado == EstadoTrabajo.pendiente
    assert procesar_cola() == 1
    assert client.get(f"/facturas/{fid}", headers=admin).json()["estado"] == "pendiente_revision"
    t = _trabajo(fid)
    assert (t.estado, t.intentos) == (EstadoTrabajo.hecho, 1)


def test_reprocesar_no_duplica_trabajos(client, admin):
    fid = _subir(client, admin)
    client.post(f"/facturas/{fid}/reprocesar", headers=admin)
    with SessionLocal() as db:
        assert db.scalar(select(text("count(*)")).select_from(Trabajo)) == 1


def test_error_pasajero_de_la_ia_se_reintenta(client, admin, monkeypatch):
    monkeypatch.setattr(ia, "disponible", lambda: True)

    def limite(data, ct):
        raise ia.ErrorExtraccionIA("Límite de uso de la API de Claude alcanzado", reintentable=True)

    monkeypatch.setattr(ia, "extraer", limite)
    fid = _subir(client, admin, png_qr("sin datos de arca"), "foto.png", "image/png")  # sin QR válido
    procesar_cola()
    t = _trabajo(fid)
    assert t.estado == EstadoTrabajo.pendiente and t.intentos == 1
    assert t.ejecutar_desde > ahora()  # espera antes de reintentar
    assert "Límite" in t.error
    assert client.get(f"/facturas/{fid}", headers=admin).json()["estado"] == "procesando"

    # Si sigue fallando hasta agotar los intentos, la factura queda en error con un mensaje claro
    for _ in range(4):
        with engine.begin() as c:
            c.execute(text("UPDATE trabajos SET ejecutar_desde = now() - interval '1 second'"))
        procesar_cola()
    assert _trabajo(fid).estado == EstadoTrabajo.error
    f = client.get(f"/facturas/{fid}", headers=admin).json()
    assert f["estado"] == "error" and "reprocesarlo" in f["error_extraccion"]


def test_error_de_la_ia_con_qr_no_se_reintenta(client, admin, monkeypatch):
    monkeypatch.setattr(ia, "disponible", lambda: True)
    monkeypatch.setattr(ia, "extraer", lambda d, c: (_ for _ in ()).throw(ia.ErrorExtraccionIA("caído", True)))
    fid = _subir(client, admin)
    procesar_cola()
    f = client.get(f"/facturas/{fid}", headers=admin).json()
    assert f["estado"] == "pendiente_revision"  # alcanza con el QR
    assert "caído" in f["datos_extraidos"]["advertencias"]


def test_trabajo_abandonado_se_retoma(client, admin):
    fid = _subir(client, admin)
    with engine.begin() as c:  # como si un worker lo hubiera tomado y se hubiera caído
        c.execute(text("UPDATE trabajos SET estado = 'en_curso', intentos = 1, "
                       "bloqueado_hasta = now() - interval '1 minute'"))
    assert procesar_cola() == 1
    assert _trabajo(fid).intentos == 2
    assert client.get(f"/facturas/{fid}", headers=admin).json()["estado"] == "pendiente_revision"


def test_trabajo_en_curso_vigente_no_se_toma_dos_veces(client, admin):
    _subir(client, admin)
    with engine.begin() as c:
        c.execute(text("UPDATE trabajos SET estado = 'en_curso', bloqueado_hasta = now() + interval '5 minutes'"))
    assert procesar_cola() == 0


def test_recuperar_facturas_huerfanas(client, admin):
    fid = _subir(client, admin)
    with engine.begin() as c:
        c.execute(text("DELETE FROM trabajos"))
    assert worker.recuperar_huerfanas() == 1
    assert worker.recuperar_huerfanas() == 0  # ya tiene trabajo
    procesar_cola()
    assert client.get(f"/facturas/{fid}", headers=admin).json()["estado"] == "pendiente_revision"


def test_tipo_desconocido_termina_en_error():
    with SessionLocal() as db:
        t = trabajos.encolar(db, "no_existe", {}, max_intentos=1)
        db.commit()
        tid = t.id
    procesar_cola()
    with SessionLocal() as db:
        t = db.get(Trabajo, tid)
        assert t.estado == EstadoTrabajo.error and "desconocido" in t.error


def test_tareas_programadas_respetan_el_intervalo(monkeypatch):
    llamadas = []
    monkeypatch.setattr(worker, "PROGRAMADAS", [worker.Programada("prueba", timedelta(hours=1),
                                                                   lambda db: llamadas.append(1))])
    worker.correr_programadas()
    worker.correr_programadas()
    assert llamadas == [1]
    with engine.begin() as c:
        c.execute(text("UPDATE tareas_programadas SET ultima_ejecucion = now() - interval '2 hours'"))
    worker.correr_programadas()
    assert llamadas == [1, 1]


def test_tarea_programada_que_falla_no_frena_al_worker(monkeypatch):
    def falla(db):
        raise RuntimeError("BCRA caído")

    monkeypatch.setattr(worker, "PROGRAMADAS", [worker.Programada("falla", timedelta(hours=1), falla)])
    worker.correr_programadas()  # no lanza
    with SessionLocal() as db:
        assert db.get(TareaProgramada, "falla") is not None  # no se reintenta en cada vuelta


def test_salud_informa_el_worker(client):
    r = client.get("/salud").json()
    assert r["base_de_datos"] is True and r["worker"] is False
    worker.latido()
    assert client.get("/salud").json()["worker"] is True


def test_request_id_en_la_respuesta(client):
    r = client.get("/salud", headers={"X-Request-ID": "abc123"})
    assert r.headers["X-Request-ID"] == "abc123"
    assert len(client.get("/salud").headers["X-Request-ID"]) == 16


def test_formato_json_de_los_logs():
    reg = logging.LogRecord("app.pedidos", logging.INFO, "", 0, "GET /x 200", None, None)
    reg.request_id, reg.estado, reg.usuario_id = "r1", 200, 7
    datos = json.loads(FormatoJSON().format(reg))
    assert datos["msg"] == "GET /x 200" and datos["request_id"] == "r1"
    assert datos["estado"] == 200 and datos["usuario_id"] == 7


def test_factura_borrada_no_rompe_el_trabajo(client, admin):
    fid = _subir(client, admin)
    with SessionLocal() as db:
        db.delete(db.get(Factura, fid))
        db.commit()
    procesar_cola()
    assert _trabajo(fid).estado == EstadoTrabajo.hecho


def test_evaluacion_de_modelos(client, admin, monkeypatch):
    """El script de comparación de modelos mide aciertos y costo sin llamar a la API (extracción simulada)."""
    from app.extraccion import evaluar

    fid = _subir(client, admin)
    procesar_cola()
    client.post(f"/facturas/{fid}/confirmar", headers=admin)

    def falso(data, ct, modelo=None, effort=None):
        bien = modelo == "claude-opus-5-5"
        ext = ia.FacturaExtraida(cuit_emisor="30712345678", tipo_comprobante=1, punto_venta=3,
                                 numero=1542 if bien else 1, fecha_emision="2026-10-15", total=121000.50)
        return ext, ia.Uso(modelo, 3000, 500)

    monkeypatch.setattr(ia, "extraer_con_uso", falso)
    lista = evaluar.casos(5)
    assert len(lista) == 1
    opus, haiku = evaluar.evaluar("claude-opus-5-5", lista), evaluar.evaluar("claude-haiku-5-5", lista)
    assert (opus.perfectas, haiku.perfectas) == (1, 0)
    assert haiku.aciertos["numero"] == 0 and haiku.aciertos["total"] == 1
    assert opus.costo == (3000 * 4 + 500 * 20) / 1_000_000
    assert "claude-haiku-5-5" in evaluar.informe([opus, haiku])
