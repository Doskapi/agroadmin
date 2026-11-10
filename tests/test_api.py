from app.extraccion import ia
from tests.conftest import login
from tests.helpers import importar, pdf_con_qr, png_qr, url_qr


def _crear_usuario(client, admin, email, rol):
    r = client.post("/usuarios", headers=admin,
                    json={"email": email, "nombre": email, "password": "clave-segura-1", "roles": [rol]})
    assert r.status_code == 201, r.text
    return login(client, email, "clave-segura-1")




# --- Auth y permisos -------------------------------------------------------


def test_sin_token_401(client):
    assert client.get("/facturas").status_code == 401


def test_login_incorrecto(client):
    assert client.post("/auth/login", data={"username": "admin@test.com", "password": "mal"}).status_code == 401


def test_permisos_por_rol(client, admin):
    campo = _crear_usuario(client, admin, "peon@test.com", "campo")
    assert client.get("/facturas", headers=campo).status_code == 403
    assert client.get("/usuarios", headers=campo).status_code == 403
    r = client.post("/cartas-porte", headers=campo, json={
        "fecha_carga": "2026-04-10", "grano": "soja", "kilos_brutos": 45000, "kilos_tara": 15000,
        "transportista_cuit": "20-12345678-6",
    })
    assert r.status_code == 201, r.text
    assert r.json()["kilos_netos"] == "30000.00"
    assert r.json()["transportista_cuit"] == "20123456786"

    yo = client.get("/auth/yo", headers=campo).json()
    assert yo["roles"] == ["campo"]
    assert "facturas:leer" not in yo["permisos"]


def test_contador_confirma_pero_no_carga(client, admin):
    contador = _crear_usuario(client, admin, "conta@test.com", "contador")
    assert importar(client, contador, pdf_con_qr(url_qr())).status_code == 403
    fid = importar(client, admin, pdf_con_qr(url_qr())).json()["id"]
    r = client.post(f"/facturas/{fid}/confirmar", headers=contador)
    assert r.status_code == 200, r.text
    assert r.json()["estado"] == "confirmada"


def test_usuario_desactivado_no_entra(client, admin):
    h = _crear_usuario(client, admin, "ex@test.com", "administrativo")
    uid = client.get("/auth/yo", headers=h).json()["id"]
    client.patch(f"/usuarios/{uid}", headers=admin, json={"activo": False})
    assert client.get("/auth/yo", headers=h).status_code == 401


# --- Importación de facturas -----------------------------------------------


def test_importar_pdf_con_qr_sin_ia(client, admin):
    r = importar(client, admin, pdf_con_qr(url_qr()))
    assert r.status_code == 202
    f = client.get(f"/facturas/{r.json()['id']}", headers=admin).json()  # el background ya corrió
    assert f["estado"] == "pendiente_revision", f
    assert f["cuit_emisor"] == "30712345678"
    assert (f["tipo_comprobante"], f["punto_venta"], f["numero"]) == (1, 3, 1542)
    assert f["total"] == "121000.50"
    assert f["cae"] == "76543210987654"
    assert f["proveedor"]["cuit"] == "30712345678"
    assert f["datos_extraidos"]["fuentes"] == ["qr_arca"]


def test_importar_imagen(client, admin):
    r = importar(client, admin, png_qr(url_qr()), "foto.png", "image/png")
    f = client.get(f"/facturas/{r.json()['id']}", headers=admin).json()
    assert f["estado"] == "pendiente_revision"
    assert f["numero"] == 1542


def test_mismo_archivo_dos_veces(client, admin):
    data = pdf_con_qr(url_qr())
    assert importar(client, admin, data).status_code == 202
    assert importar(client, admin, data).status_code == 409


def test_mismo_comprobante_otro_archivo(client, admin):
    importar(client, admin, pdf_con_qr(url_qr()))
    r = importar(client, admin, png_qr(url_qr()), "foto.png", "image/png")
    f = client.get(f"/facturas/{r.json()['id']}", headers=admin).json()
    assert f["estado"] == "error"
    assert "duplicado" in f["error_extraccion"]


def test_sin_qr_ni_ia_queda_en_error(client, admin):
    r = importar(client, admin, png_qr("hola"), "x.png", "image/png")
    f = client.get(f"/facturas/{r.json()['id']}", headers=admin).json()
    assert f["estado"] == "error"


def test_formato_no_soportado(client, admin):
    assert importar(client, admin, b"hola", "a.txt", "text/plain").status_code == 415


def test_ia_mas_qr(client, admin, monkeypatch):
    """La IA aporta ítems y razón social; el QR corrige el total y se deja una advertencia."""
    monkeypatch.setattr(ia, "disponible", lambda: True)
    monkeypatch.setattr(ia, "extraer", lambda data, ct: ia.FacturaExtraida(
        cuit_emisor="30712345678", razon_social_emisor="Agroinsumos del Sur SA", tipo_comprobante=1,
        punto_venta=3, numero=1542, fecha_emision="2026-10-15", neto_gravado=100000.0, iva=21000.0,
        total=121000.0, categoria_sugerida="agroquimicos",
        items=[ia.ItemExtraido(descripcion="Glifosato 66%", cantidad=200, unidad="lt", precio_unitario=500,
                               alicuota_iva=21, subtotal=100000)],
    ))
    r = importar(client, admin, pdf_con_qr(url_qr()))
    f = client.get(f"/facturas/{r.json()['id']}", headers=admin).json()
    assert f["estado"] == "pendiente_revision"
    assert f["datos_extraidos"]["fuentes"] == ["ia", "qr_arca"]
    assert f["total"] == "121000.50"
    assert any("total" in a for a in f["datos_extraidos"]["advertencias"])
    assert f["proveedor"]["razon_social"] == "Agroinsumos del Sur SA"
    assert f["items"][0]["descripcion"] == "Glifosato 66%"
    cats = {c["id"]: c["nombre"] for c in client.get("/categorias", headers=admin).json()}
    assert cats[f["categoria_id"]] == "agroquimicos"


# --- Revisión, confirmación y reportes -------------------------------------


def test_confirmar_exige_datos(client, admin):
    r = client.post("/facturas", headers=admin, json={"total": 1000})
    assert r.status_code == 201
    r = client.post(f"/facturas/{r.json()['id']}/confirmar", headers=admin)
    assert r.status_code == 422
    assert "proveedor_id" in r.json()["detail"]


def test_confirmada_no_se_edita(client, admin):
    fid = importar(client, admin, pdf_con_qr(url_qr())).json()["id"]
    client.post(f"/facturas/{fid}/confirmar", headers=admin)
    assert client.patch(f"/facturas/{fid}", headers=admin, json={"total": 1}).status_code == 409


def test_reportes(client, admin):
    prov = client.post("/proveedores", headers=admin,
                       json={"cuit": "30-71234567-8", "razon_social": "Agroinsumos del Sur SA"}).json()
    cats = {c["nombre"]: c["id"] for c in client.get("/categorias", headers=admin).json()}
    camp = client.post("/campanias", headers=admin,
                       json={"nombre": "2026/27", "fecha_inicio": "2026-07-01", "fecha_fin": "2027-06-30"}).json()
    base = {"proveedor_id": prov["id"], "cuit_emisor": prov["cuit"], "campania_id": camp["id"], "punto_venta": 1}
    facturas = [
        {"tipo_comprobante": 1, "numero": 1, "fecha_emision": "2026-09-10", "total": 1000, "categoria_id": cats["semillas"]},
        {"tipo_comprobante": 1, "numero": 2, "fecha_emision": "2026-10-05", "total": 500, "categoria_id": cats["combustible"]},
        {"tipo_comprobante": 1, "numero": 3, "fecha_emision": "2026-10-20", "total": 100, "moneda": "DOL",
         "cotizacion": 1200, "categoria_id": cats["semillas"]},
        {"tipo_comprobante": 3, "numero": 4, "fecha_emision": "2026-10-25", "total": 200, "categoria_id": cats["semillas"]},
    ]
    for f in facturas:
        fid = client.post("/facturas", headers=admin, json=base | f).json()["id"]
        assert client.post(f"/facturas/{fid}/confirmar", headers=admin).status_code == 200
    # una pendiente que no debe contar
    client.post("/facturas", headers=admin, json=base | {"tipo_comprobante": 1, "numero": 9, "total": 99999})

    por_cat = {f["clave"]: f["total"] for f in client.get("/reportes/gastos?agrupar=categoria", headers=admin).json()}
    # semillas: 1000 + 100 USD * 1200 - NC 200
    assert por_cat == {"semillas": "120800.00", "combustible": "500.00"}

    por_mes = client.get("/reportes/gastos?agrupar=mes", headers=admin).json()
    assert [f["clave"] for f in por_mes] == ["2026-09", "2026-10"]

    resumen = client.get("/reportes/resumen", headers=admin).json()
    assert resumen["total_gastos"] == "121300.00"
    assert resumen["pendientes_revision"] == 1
    assert resumen["top_proveedores"][0]["clave"] == "Agroinsumos del Sur SA"

    r = client.get("/reportes/gastos.xlsx?agrupar=proveedor", headers=admin)
    assert r.status_code == 200
    assert r.content[:2] == b"PK"  # xlsx es un zip
