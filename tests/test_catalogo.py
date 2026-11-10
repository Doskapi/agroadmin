"""Fase 2: catálogo de facturas, reparto entre lotes, acciones masivas, reportes nuevos e insumos."""

import io
from datetime import date

import pytest
from openpyxl import load_workbook

from tests.conftest import login


@pytest.fixture
def datos(client, admin):
    """Dos campos con lotes, una campaña, dos proveedores y cinco facturas (una nota de crédito)."""
    cats = {c["nombre"]: c["id"] for c in client.get("/categorias", headers=admin).json()}
    camp = client.post("/campanias", headers=admin,
                       json={"nombre": "2026/27", "fecha_inicio": "2026-07-01", "fecha_fin": "2027-06-30"}).json()
    norte = client.post("/campos", headers=admin, json={"nombre": "Norte", "hectareas": 200}).json()
    sur = client.post("/campos", headers=admin, json={"nombre": "Sur", "hectareas": 100}).json()
    l1 = client.post(f"/campos/{norte['id']}/lotes", headers=admin, json={"nombre": "L1", "hectareas": 120}).json()
    l2 = client.post(f"/campos/{norte['id']}/lotes", headers=admin, json={"nombre": "L2", "hectareas": 80}).json()
    p1 = client.post("/proveedores", headers=admin, json={
        "cuit": "30-71234567-8", "razon_social": "Agroinsumos del Sur SA", "categoria_id": cats["agroquimicos"]}).json()
    p2 = client.post("/proveedores", headers=admin,
                     json={"cuit": "30-70000000-1", "razon_social": "YPF Agro"}).json()

    def factura(prov, numero, fecha, total, **extra):
        body = {"proveedor_id": prov["id"], "cuit_emisor": prov["cuit"], "tipo_comprobante": 1, "punto_venta": 1,
                "numero": numero, "fecha_emision": fecha, "total": total, "campania_id": camp["id"]} | extra
        r = client.post("/facturas", headers=admin, json=body)
        assert r.status_code == 201, r.text
        return r.json()

    f1 = factura(p1, 1, "2026-09-10", 1000, campo_id=norte["id"], lote_id=l1["id"],
                 items=[{"descripcion": "Glifosato 62%  x 20 Lts.", "cantidad": 10, "precio_unitario": 100,
                         "subtotal": 1000}])
    f2 = factura(p2, 2, "2026-10-05", 600, categoria_id=cats["combustible"], imputaciones=[
        {"campo_id": norte["id"], "lote_id": l2["id"], "porcentaje": 50},
        {"campo_id": sur["id"], "porcentaje": 50},
    ])
    f3 = factura(p1, 3, "2026-10-20", 100, moneda="DOL", cotizacion=1500, campo_id=sur["id"],
                 items=[{"descripcion": "GLIFOSATO 62% x 20 lts", "cantidad": 1, "precio_unitario": 100}])
    f4 = factura(p1, 4, "2026-10-25", 200, tipo_comprobante=3, campo_id=norte["id"], lote_id=l1["id"])
    f5 = factura(p2, 5, "2026-11-02", 50, observaciones="pendiente de imputar")
    for f in (f1, f2, f3, f4):
        assert client.post(f"/facturas/{f['id']}/confirmar", headers=admin).status_code == 200
    return {"cats": cats, "camp": camp, "norte": norte, "sur": sur, "l1": l1, "l2": l2, "p1": p1, "p2": p2,
            "f": [f1, f2, f3, f4, f5]}


# --- Catálogo -------------------------------------------------------------------


def test_rubro_por_defecto_del_proveedor(datos):
    assert datos["f"][0]["categoria_id"] == datos["cats"]["agroquimicos"]
    # si se indica un rubro, se respeta
    assert datos["f"][1]["categoria_id"] == datos["cats"]["combustible"]


def test_catalogo_totales_y_paginado(client, admin, datos):
    r = client.get("/facturas/catalogo?limit=2&orden=total&dir=desc", headers=admin).json()
    assert r["total"] == 5
    assert len(r["items"]) == 2
    # 1000 + 600 + 100 USD x 1500 - 200 (NC) + 50
    assert r["suma_pesos"] == "151450.00"
    assert r["items"][0]["numero"] == 3  # la de dólares es la más grande en pesos


@pytest.mark.parametrize("query,numeros", [
    ("q=glifosato", {1, 3}),
    ("q=ypf", {2, 5}),
    ("q=30-70000000", {2, 5}),
    ("q=pendiente de imputar", {5}),
    ("q=0004", {4}),
    ("tipo_comprobante=3", {4}),
    ("moneda=DOL", {3}),
    ("monto_min=500&monto_max=700", {2}),
    ("estado=pendiente_revision", {5}),
    ("estado=pendiente_revision&estado=confirmada", {1, 2, 3, 4, 5}),
    ("sin_imputar=true", {5}),
    ("desde=2026-10-01&hasta=2026-10-31", {2, 3, 4}),
])
def test_catalogo_filtros(client, admin, datos, query, numeros):
    r = client.get(f"/facturas/catalogo?{query}", headers=admin).json()
    assert {f["numero"] for f in r["items"]} == numeros


def test_filtro_por_campo_y_lote_respeta_reparto(client, admin, datos):
    por_campo = client.get(f"/facturas/catalogo?campo_id={datos['sur']['id']}", headers=admin).json()
    assert {f["numero"] for f in por_campo["items"]} == {2, 3}
    por_lote = client.get(f"/facturas/catalogo?lote_id={datos['l2']['id']}", headers=admin).json()
    assert {f["numero"] for f in por_lote["items"]} == {2}
    assert [f["repartida"] for f in por_lote["items"]] == [True]


def test_excel_detalle(client, admin, datos):
    r = client.get("/facturas/catalogo.xlsx?estado=confirmada", headers=admin)
    assert r.status_code == 200
    wb = load_workbook(io.BytesIO(r.content))
    comp = list(wb["Comprobantes"].iter_rows(values_only=True))
    assert len(comp) == 5  # encabezado + 4 confirmadas
    enc = comp[0]
    nc = next(f for f in comp[1:] if f[enc.index("Número")] == 4)
    assert nc[enc.index("Total ARS")] == -200  # la nota de crédito resta
    repartida = next(f for f in comp[1:] if f[enc.index("Número")] == 2)
    assert "Norte 50%" in repartida[enc.index("Campo")]
    items = list(wb["Ítems"].iter_rows(values_only=True))
    assert len(items) == 3


# --- Reparto ---------------------------------------------------------------------


def test_reparto_debe_sumar_100(client, admin, datos):
    fid = datos["f"][4]["id"]
    r = client.patch(f"/facturas/{fid}", headers=admin, json={"imputaciones": [
        {"campo_id": datos["norte"]["id"], "porcentaje": 60}, {"campo_id": datos["sur"]["id"], "porcentaje": 30}]})
    assert r.status_code == 422
    assert "suman 90" in r.json()["detail"]


def test_reparto_lote_de_otro_campo(client, admin, datos):
    fid = datos["f"][4]["id"]
    r = client.patch(f"/facturas/{fid}", headers=admin, json={"imputaciones": [
        {"campo_id": datos["sur"]["id"], "lote_id": datos["l1"]["id"], "porcentaje": 100}]})
    assert r.status_code == 422


def test_quitar_reparto(client, admin, datos):
    fid = datos["f"][4]["id"]
    body = {"imputaciones": [{"campo_id": datos["sur"]["id"], "porcentaje": 100}]}
    assert len(client.patch(f"/facturas/{fid}", headers=admin, json=body).json()["imputaciones"]) == 1
    assert client.patch(f"/facturas/{fid}", headers=admin, json={"imputaciones": []}).json()["imputaciones"] == []


# --- Acciones masivas -------------------------------------------------------------


def test_imputar_en_lote(client, admin, datos):
    f5 = datos["f"][4]
    confirmada = datos["f"][0]
    r = client.post("/facturas/acciones", headers=admin, json={
        "ids": [f5["id"], confirmada["id"], 9999], "accion": "imputar",
        "lote_id": datos["l2"]["id"], "categoria_id": datos["cats"]["fletes"]})
    assert r.status_code == 200, r.text
    res = r.json()
    assert res["ok"] == [f5["id"]]
    assert set(res["errores"]) == {str(confirmada["id"]), "9999"}
    f = client.get(f"/facturas/{f5['id']}", headers=admin).json()
    # el lote completa el campo
    assert (f["campo_id"], f["lote_id"], f["categoria_id"]) == (datos["norte"]["id"], datos["l2"]["id"],
                                                                  datos["cats"]["fletes"])


def test_confirmar_en_lote_y_permisos(client, admin, datos):
    client.post("/usuarios", headers=admin, json={"email": "carga@test.com", "nombre": "c",
                                                   "password": "clave-segura-1", "roles": ["administrativo"]})
    carga = login(client, "carga@test.com", "clave-segura-1")
    body = {"ids": [datos["f"][4]["id"]], "accion": "confirmar"}
    assert client.post("/facturas/acciones", headers=carga, json=body).status_code == 403
    r = client.post("/facturas/acciones", headers=admin, json=body).json()
    assert r["ok"] == [datos["f"][4]["id"]]


# --- Reportes ---------------------------------------------------------------------


def _por(client, admin, agrupar, extra=""):
    filas = client.get(f"/reportes/gastos?agrupar={agrupar}{extra}", headers=admin).json()
    return {f["clave"]: f["total"] for f in filas}


def test_reportes_por_campo_y_lote_con_reparto(client, admin, datos):
    # Norte: 1000 (L1) + 300 (mitad de f2 en L2) - 200 (NC L1) ; Sur: 300 + 150000
    assert _por(client, admin, "campo") == {"Norte": "1100.00", "Sur": "150300.00"}
    assert _por(client, admin, "lote") == {"Norte / L1": "800.00", "Norte / L2": "300.00", None: "150300.00"}
    # filtrar por campo toma solo la parte de ese campo
    assert _por(client, admin, "categoria", f"&campo_id={datos['sur']['id']}") == {
        "agroquimicos": "150000.00", "combustible": "300.00"}


def test_reporte_devuelve_ids(client, admin, datos):
    filas = client.get("/reportes/gastos?agrupar=proveedor", headers=admin).json()
    assert {f["id"] for f in filas} == {datos["p1"]["id"], datos["p2"]["id"]}


def test_cruce(client, admin, datos):
    r = client.get("/reportes/cruce?filas=categoria&columnas=mes", headers=admin).json()
    assert [c["clave"] for c in r["columnas"]] == ["2026-09", "2026-10"]
    assert r["filas"][0]["clave"] == "agroquimicos"  # el de mayor gasto primero
    celdas = {(c["fila"], c["columna"]): c["total"] for c in r["celdas"]}
    assert celdas[(datos["cats"]["agroquimicos"], "2026-10")] == "149800.00"
    assert client.get("/reportes/cruce?filas=mes&columnas=mes", headers=admin).status_code == 422
    xlsx = client.get("/reportes/cruce.xlsx?filas=categoria&columnas=campania", headers=admin)
    assert xlsx.content[:2] == b"PK"


def test_costo_por_hectarea(client, admin, datos):
    filas = client.get("/reportes/costo-hectarea", headers=admin).json()
    norte = next(f for f in filas if f["campo"] == "Norte" and f["lote"] is None)
    assert (norte["total"], norte["por_hectarea"]) == ("1100.00", "5.50")  # 1100 / 200 ha
    l1 = next(f for f in filas if f["lote"] == "L1")
    assert l1["por_hectarea"] == "6.67"  # 800 / 120 ha


def test_iva(client, admin, datos):
    client.patch(f"/facturas/{datos['f'][4]['id']}", headers=admin,
                 json={"neto_gravado": 41.32, "iva": 8.68})
    client.post(f"/facturas/{datos['f'][4]['id']}/confirmar", headers=admin)
    filas = {f["periodo"]: f for f in client.get("/reportes/iva", headers=admin).json()}
    assert filas["2026-11"]["iva"] == "8.68"
    assert filas["2026-10"]["total"] == "150400.00"  # 600 + 150000 - 200


def test_reporte_en_dolares(client, admin, datos):
    faltan = client.get("/reportes/cotizaciones-faltantes", headers=admin).json()
    assert faltan["facturas_sin_cotizacion"] == 3
    assert faltan["primera_fecha_faltante"] == "2026-09-10"
    r = client.put("/cotizaciones", headers=admin, json=[
        {"fecha": "2026-09-01", "valor": 1000}, {"fecha": "2026-10-01", "valor": 1200}])
    assert r.json() == {"guardadas": 2}
    # 1000 / 1000 + (600 / 1200) + 100 (ya en USD) - 200 / 1200
    total = sum(float(v) for v in _por(client, admin, "mes", "&expresado_en=USD").values())
    assert total == pytest.approx(1 + 0.5 + 100 - 0.17, abs=0.02)
    assert client.get("/reportes/cotizaciones-faltantes", headers=admin).json()["facturas_sin_cotizacion"] == 0


def test_actualizar_cotizaciones_bcra(client, admin, monkeypatch):
    from decimal import Decimal

    from app.routers import cotizaciones

    pedidos = []

    def falso(desde, hasta):
        pedidos.append((desde, hasta))
        return {date(2026, 10, 1): Decimal("1524.5")}

    monkeypatch.setattr(cotizaciones, "traer_del_bcra", falso)
    r = client.post("/cotizaciones/actualizar?hasta=2026-10-05", headers=admin)
    assert r.json() == {"guardadas": 1}
    client.post("/cotizaciones/actualizar?hasta=2026-10-05", headers=admin)
    assert pedidos[-1][0] == date(2026, 10, 2)  # sigue desde la última guardada


# --- Insumos ---------------------------------------------------------------------


def test_insumos_alias_y_reporte(client, admin, datos):
    sin = client.get("/insumos/sin-asignar", headers=admin).json()
    glifo = next(s for s in sin if s["descripcion"].startswith("Glifosato"))
    insumo = client.post("/insumos", headers=admin, json={"nombre": "Glifosato 62%", "unidad": "bidón 20 L"}).json()
    r = client.put(f"/facturas/items/{glifo['ejemplo_item_id']}/insumo", headers=admin,
                   json={"insumo_id": insumo["id"], "recordar": True})
    assert r.status_code == 200
    # el ítem de la otra factura (mayúsculas y puntuación distintas) también quedó asignado
    assert client.get("/insumos/sin-asignar", headers=admin).json() == []

    # y los ítems nuevos con esa descripción se asignan solos
    nueva = client.post("/facturas", headers=admin, json={"items": [{"descripcion": "glifosato 62% x 20 LTS"}]}).json()
    assert nueva["items"][0]["insumo_id"] == insumo["id"]

    res = client.get("/reportes/insumos", headers=admin).json()
    assert res[0]["insumo"] == "Glifosato 62%"
    assert res[0]["cantidad"] == "11.0000"
    assert res[0]["total_pesos"] == "151000.00"  # 1000 + 100 USD x 1500 (sin subtotal: cantidad x precio)
    assert res[0]["ultimo_precio"] == "150000.00"
    precios = client.get(f"/reportes/insumos/{insumo['id']}/precios", headers=admin).json()
    assert [p["precio_pesos"] for p in precios] == ["100.00", "150000.00", None]  # la última no tiene precio
