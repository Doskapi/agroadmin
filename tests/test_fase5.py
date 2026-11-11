"""Fase 5: pagos, ventas y margen, conciliación y verificación con ARCA, correo entrante y cartas de porte."""

import base64
import io
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from email.message import EmailMessage

import httpx
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from defusedxml import ElementTree as ET
from openpyxl import Workbook
from sqlalchemy import select

from app import avisos, correo_entrante
from app.arca import mis_comprobantes, wscdc
from app.config import settings
from app.db import SessionLocal
from app.extraccion import carta_porte, ia
from app.models import CorreoImportado, Factura
from tests.helpers import pdf_con_qr, procesar_cola, url_qr

HOY = date.today()


def _factura(client, admin, numero, total, *, tipo=1, vto=None, confirmar=True, moneda="PES", cotizacion=1, **extra):
    prov = client.get("/proveedores", headers=admin).json()
    if not prov:
        prov = [client.post("/proveedores", headers=admin,
                            json={"cuit": "30-71234567-8", "razon_social": "Agroinsumos del Sur SA"}).json()]
    body = {"proveedor_id": prov[0]["id"], "cuit_emisor": prov[0]["cuit"], "tipo_comprobante": tipo,
            "punto_venta": 3, "numero": numero, "fecha_emision": str(HOY - timedelta(days=40)), "total": total,
            "fecha_vencimiento": str(vto) if vto else None, "moneda": moneda, "cotizacion": cotizacion,
            "cae": "76543210987654"} | extra
    f = client.post("/facturas", headers=admin, json=body).json()
    if confirmar:
        assert client.post(f"/facturas/{f['id']}/confirmar", headers=admin).status_code == 200
    return f


# --- Pagos -----------------------------------------------------------------------


def test_pagos_parciales_y_saldo(client, admin):
    f = _factura(client, admin, 1, 1000, vto=HOY + timedelta(days=3))
    pago = {"fecha": str(HOY), "monto": 400, "medio": "transferencia", "referencia": "TRF 123"}
    r = client.post(f"/facturas/{f['id']}/pagos", headers=admin, json=pago)
    assert r.status_code == 201, r.text
    assert (r.json()["pagado"], r.json()["saldo"]) == ("400.00", "600.00")
    r = client.post(f"/facturas/{f['id']}/pagos", headers=admin, json=pago | {"monto": 700})
    assert r.status_code == 422 and "supera el saldo" in r.json()["detail"]
    r = client.post(f"/facturas/{f['id']}/pagos", headers=admin, json=pago | {"monto": 600})
    assert r.json()["saldo"] == "0.00"
    # borrar un pago vuelve a dejar saldo
    pid = r.json()["pagos"][0]["id"]
    assert client.delete(f"/pagos/{pid}", headers=admin).json()["saldo"] == "400.00"
    hist = [h["accion"] for h in client.get(f"/facturas/{f['id']}/historial", headers=admin).json()]
    assert hist.count("pago_registrado") == 2 and "pago_borrado" in hist


def test_pagos_solo_de_facturas_confirmadas_y_no_nc(client, admin):
    pend = _factura(client, admin, 1, 100, confirmar=False)
    nc = _factura(client, admin, 2, 100, tipo=3)
    pago = {"fecha": str(HOY), "monto": 10, "medio": "efectivo"}
    assert client.post(f"/facturas/{pend['id']}/pagos", headers=admin, json=pago).status_code == 409
    assert client.post(f"/facturas/{nc['id']}/pagos", headers=admin, json=pago).status_code == 422


def test_cuentas_a_pagar(client, admin):
    vencida = _factura(client, admin, 1, 1000, vto=HOY - timedelta(days=5))
    _factura(client, admin, 2, 500, vto=HOY + timedelta(days=2))
    _factura(client, admin, 3, 100, moneda="DOL", cotizacion=1500, vto=HOY + timedelta(days=30))
    _factura(client, admin, 4, 50, tipo=3)  # NC: no se paga
    pagada = _factura(client, admin, 5, 80, vto=HOY - timedelta(days=1))
    client.post(f"/facturas/{pagada['id']}/pagos", headers=admin, json={"fecha": str(HOY), "monto": 80, "medio": "cheque"})

    c = client.get("/pagos/pendientes", headers=admin).json()
    assert [x["comprobante"] for x in c["facturas"]] == [
        "Factura A 00003-00000001", "Factura A 00003-00000002", "Factura A 00003-00000003"]
    assert c["facturas"][0]["dias"] == -5
    assert (c["vencido_pesos"], c["proximos_7_dias_pesos"], c["total_pesos"]) == ("1000.00", "500.00", "151500.00")
    assert len(client.get(f"/pagos/pendientes?hasta={HOY + timedelta(days=7)}", headers=admin).json()["facturas"]) == 2

    def numeros(pago):
        return {x["numero"] for x in client.get(f"/facturas/catalogo?pago={pago}", headers=admin).json()["items"]}

    assert numeros("vencida") == {1}
    assert numeros("pendiente") == {1, 2, 3}
    assert numeros("pagada") == {5}
    assert vencida["id"] in {x["id"] for x in client.get("/facturas/catalogo?pago=vencida", headers=admin).json()["items"]}


def test_aviso_de_vencimientos(client, admin, monkeypatch):
    _factura(client, admin, 1, 1000, vto=HOY - timedelta(days=2))
    enviados = []
    monkeypatch.setattr(avisos.correo, "enviar", lambda d, a, t: enviados.append((d, t)) or True)
    with SessionLocal() as db:
        assert avisos.enviar(db) == 1
    destino, texto = enviados[0]
    assert destino == "admin@test.com"
    assert "vencida hace 2 día(s)" in texto and "1,000.00" in texto


# --- Ventas y margen ----------------------------------------------------------------


def test_ventas_y_margen(client, admin):
    camp = client.post("/campanias", headers=admin,
                       json={"nombre": "2026/27", "fecha_inicio": "2026-07-01", "fecha_fin": "2027-06-30"}).json()
    norte = client.post("/campos", headers=admin, json={"nombre": "Norte", "hectareas": 100}).json()
    lote = client.post(f"/campos/{norte['id']}/lotes", headers=admin, json={"nombre": "L1", "hectareas": 50}).json()
    _factura(client, admin, 1, 300000, campania_id=camp["id"], campo_id=norte["id"], lote_id=lote["id"])

    v = {"fecha": str(HOY), "campania_id": camp["id"], "lote_id": lote["id"], "grano": "Soja", "kilos": 150000,
         "precio_tonelada": 300, "total": 45000, "moneda": "DOL", "cotizacion": 1000, "comprador": "Acopio SA"}
    r = client.post("/ventas", headers=admin, json=v)
    assert r.status_code == 201, r.text
    assert (r.json()["campo_id"], r.json()["grano"]) == (norte["id"], "soja")  # el lote completa el campo
    client.post("/ventas", headers=admin, json=v | {"lote_id": None, "campo_id": norte["id"], "kilos": 10000,
                                                     "total": 3000000, "moneda": "PES", "cotizacion": 1})

    por_campo = client.get("/reportes/margen?agrupar=campo", headers=admin).json()
    assert len(por_campo) == 1
    m = por_campo[0]
    # ingresos: 45000 USD x 1000 + 3.000.000 ; gastos 300.000
    assert (m["ingresos"], m["gastos"], m["margen"]) == ("48000000.00", "300000.00", "47700000.00")
    assert (m["rinde_kg_ha"], m["margen_ha"]) == ("1600.00", "477000.00")
    por_lote = {x["clave"]: x for x in client.get("/reportes/margen?agrupar=lote", headers=admin).json()}
    assert por_lote["Norte / L1"]["rinde_kg_ha"] == "3000.00"
    assert client.get("/reportes/margen?agrupar=mes", headers=admin).status_code == 422

    vid = r.json()["id"]
    assert client.put(f"/ventas/{vid}", headers=admin, json=v | {"total": 46000}).json()["total"] == "46000.00"
    assert client.delete(f"/ventas/{vid}", headers=admin).status_code == 204
    assert len(client.get("/ventas", headers=admin).json()) == 1


# --- Mis Comprobantes y conciliación ---------------------------------------------------

CSV_ARCA = (
    "Fecha;Tipo;Punto de Venta;Número Desde;Número Hasta;Cód. Autorización;Tipo Doc. Emisor;Nro. Doc. Emisor;"
    "Denominación Emisor;Tipo Cambio;Moneda;Imp. Neto Gravado;Imp. Neto No Gravado;Imp. Op. Exentas;IVA;Imp. Total\n"
    "{f};1 - Factura A;3;1;1;76543210987654;80;30712345678;AGROINSUMOS DEL SUR SA;1;$;826,45;0;0;173,55;1.000,00\n"
    "{f};1 - Factura A;3;2;2;76543210987655;80;30712345678;AGROINSUMOS DEL SUR SA;1;$;0;0;0;0;600,00\n"
    "{f};6 - Factura B;1;77;77;76543210987656;80;30700000001;YPF SA;1;$;0;0;0;0;12.345,67\n"
).format(f=(HOY - timedelta(days=40)).strftime("%d/%m/%Y"))


def test_leer_mis_comprobantes_csv():
    filas = mis_comprobantes.leer(CSV_ARCA.encode("latin-1"), "comprobantes.csv")
    assert len(filas) == 3
    assert (filas[0].tipo_comprobante, filas[0].punto_venta, filas[0].numero) == (1, 3, 1)
    assert filas[0].total == Decimal("1000.00") and filas[2].total == Decimal("12345.67")
    assert filas[2].razon_social == "YPF SA" and filas[0].moneda == "PES"


def test_leer_mis_comprobantes_excel_con_titulo():
    wb = Workbook()
    ws = wb.active
    ws.append(["Mis Comprobantes Recibidos - CUIT 30711111111"])
    ws.append(["Fecha de Emisión", "Tipo de Comprobante", "Punto de Venta", "Número Desde", "Nro. Doc. Emisor",
               "Denominación Emisor", "Moneda", "Imp. Total"])
    ws.append([datetime(2026, 9, 1), "11 - Factura C", 2, 15, "20123456786", "Pérez Juan", "DOL", 1234.5])
    buf = io.BytesIO()
    wb.save(buf)
    (fila,) = mis_comprobantes.leer(buf.getvalue(), "mc.xlsx")
    assert (fila.fecha, fila.tipo_comprobante, fila.numero, fila.moneda, fila.total) == (
        date(2026, 9, 1), 11, 15, "DOL", Decimal("1234.5"))


def test_archivo_que_no_es_de_arca():
    with pytest.raises(mis_comprobantes.ArchivoInvalido):
        mis_comprobantes.leer(b"a,b,c\n1,2,3\n", "x.csv")


def test_conciliacion(client, admin):
    _factura(client, admin, 1, 1000)  # coincide
    _factura(client, admin, 2, 650)  # total distinto (ARCA dice 600)
    _factura(client, admin, 9, 50)  # cargada pero ARCA no la tiene
    r = client.post("/arca/comprobantes-recibidos", headers=admin,
                    files={"archivo": ("mc.csv", CSV_ARCA.encode("utf-8"), "text/csv")})
    assert r.status_code == 200, r.text
    assert (r.json()["leidos"], r.json()["nuevos"]) == (3, 3)
    # volver a subir el mismo archivo no duplica
    again = client.post("/arca/comprobantes-recibidos", headers=admin,
                        files={"archivo": ("mc.csv", CSV_ARCA.encode("utf-8"), "text/csv")})
    assert again.json()["nuevos"] == 0

    c = client.get("/arca/conciliacion", headers=admin).json()
    assert c["coinciden"] == 1
    assert [x["numero"] for x in c["faltan_cargar"]] == [77]
    assert [x["numero"] for x in c["no_estan_en_arca"]] == [9]
    assert [(d["arca"]["numero"], d["total_cargado"]) for d in c["diferencias"]] == [(2, "650.00")]


def test_importar_archivo_invalido_a_arca(client, admin):
    r = client.post("/arca/comprobantes-recibidos", headers=admin, files={"archivo": ("x.csv", b"hola", "text/csv")})
    assert r.status_code == 422


# --- WSCDC (ARCA) -------------------------------------------------------------------------


@pytest.fixture
def certificado(tmp_path, monkeypatch):
    clave = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    nombre = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "agroadmin-test")])
    cert = (x509.CertificateBuilder().subject_name(nombre).issuer_name(nombre).public_key(clave.public_key())
            .serial_number(1).not_valid_before(datetime.now(UTC)).not_valid_after(datetime.now(UTC) + timedelta(days=1))
            .sign(clave, hashes.SHA256()))
    (tmp_path / "c.crt").write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    (tmp_path / "c.key").write_bytes(clave.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                                         serialization.NoEncryption()))
    monkeypatch.setattr(settings, "arca_cuit", "30711111111")
    monkeypatch.setattr(settings, "arca_certificado", tmp_path / "c.crt")
    monkeypatch.setattr(settings, "arca_clave_privada", tmp_path / "c.key")
    monkeypatch.setattr(settings, "storage_dir", tmp_path)
    return cert


def _respuestas_arca(resultado="A", obs=""):
    pedidos = []

    def responder(request: httpx.Request):
        pedidos.append(request)
        if "LoginCms" in str(request.url):
            ta = ("<loginTicketResponse><credentials><token>TOK</token><sign>SIG</sign></credentials>"
                  f"<header><expirationTime>{(datetime.now(UTC) + timedelta(hours=12)).isoformat()}</expirationTime>"
                  "</header></loginTicketResponse>")
            cuerpo = ('<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"><soapenv:Body>'
                      f'<loginCmsResponse><loginCmsReturn>{ta.replace("<", "&lt;").replace(">", "&gt;")}'
                      "</loginCmsReturn></loginCmsResponse></soapenv:Body></soapenv:Envelope>")
        else:
            cuerpo = ('<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"><soap:Body>'
                      '<ComprobanteConstatarResponse xmlns="http://servicios1.afip.gob.ar/wscdc/">'
                      f"<ComprobanteConstatarResult><Resultado>{resultado}</Resultado>{obs}"
                      "</ComprobanteConstatarResult></ComprobanteConstatarResponse></soap:Body></soap:Envelope>")
        return httpx.Response(200, content=cuerpo.encode())

    return pedidos, httpx.Client(transport=httpx.MockTransport(responder))


def test_firma_del_pedido_de_acceso(certificado, tmp_path):
    from cryptography.hazmat.primitives.serialization import pkcs7

    cms = base64.b64decode(wscdc.firmar_tra((tmp_path / "c.crt").read_bytes(), (tmp_path / "c.key").read_bytes()))
    assert pkcs7.load_der_pkcs7_certificates(cms)[0] == certificado  # el certificado viaja en el CMS
    assert b"<service>wscdc</service>" in cms  # el contenido va adjunto


def test_constatar_aprobado_y_ticket_reutilizado(certificado):
    pedidos, client = _respuestas_arca()
    r = wscdc.constatar("30712345678", 1, 3, 1542, date(2026, 10, 15), Decimal("121000.50"), "76543210987654",
                        client=client)
    assert r.resultado == "A" and r.observaciones == []
    pedido = ET.fromstring(pedidos[1].content)
    campos = {e.tag.split("}")[1]: e.text for e in pedido.iter() if e.text and "}" in e.tag}
    assert campos["CbteFch"] == "20261015" and campos["ImpTotal"] == "121000.50"
    assert campos["DocNroReceptor"] == "30711111111" and campos["Token"] == "TOK"
    # el segundo pedido usa el ticket guardado: no vuelve a llamar al WSAA
    wscdc.constatar("30712345678", 1, 3, 1542, date(2026, 10, 15), Decimal("1"), "1", client=client)
    assert sum("LoginCms" in str(p.url) for p in pedidos) == 1


def test_constatar_rechazado_con_observaciones(certificado):
    obs = "<Observaciones><Obs><Code>21</Code><Msg>El CAE no corresponde</Msg></Obs></Observaciones>"
    _, client = _respuestas_arca("R", obs)
    r = wscdc.constatar("30712345678", 1, 3, 1, date(2026, 10, 15), Decimal("1"), "1", client=client)
    assert r.resultado == "R" and r.observaciones == ["21: El CAE no corresponde"]


def test_confirmar_encola_la_verificacion(client, admin, certificado, monkeypatch):
    monkeypatch.setattr(wscdc, "constatar", lambda *a, **k: wscdc.Resultado("R", ["21: El CAE no corresponde"]))
    f = _factura(client, admin, 1, 1000)
    procesar_cola()
    f = client.get(f"/facturas/{f['id']}", headers=admin).json()
    assert f["arca_resultado"] == "R" and "CAE" in f["arca_observaciones"]
    # sin configuración no se puede pedir a mano
    monkeypatch.setattr(settings, "arca_cuit", "")
    assert client.post(f"/facturas/{f['id']}/verificar-arca", headers=admin).status_code == 422


# --- Correo entrante -------------------------------------------------------------------------


def _correo(message_id="<a1@proveedor.com>", remitente="facturas@proveedor.com", adjunto=None):
    m = EmailMessage()
    m["From"], m["Subject"], m["Message-ID"] = remitente, "Factura octubre", message_id
    m.set_content("Adjuntamos la factura")
    if adjunto is not False:
        m.add_attachment(adjunto or pdf_con_qr(url_qr()), maintype="application", subtype="pdf", filename="fc.pdf")
    return m.as_bytes()


def test_correo_importa_adjuntos(client, admin):
    with SessionLocal() as db:
        reg = correo_entrante.procesar_mensaje(db, _correo())
        assert len(reg.facturas) == 1
        assert correo_entrante.procesar_mensaje(db, _correo()) is None  # mismo Message-ID: se ignora
        sin = correo_entrante.procesar_mensaje(db, _correo("<a2@x>", adjunto=False))
        assert sin.facturas == [] and "Sin adjuntos" in sin.detalle
    procesar_cola()
    f = client.get(f"/facturas/{reg.facturas[0]}", headers=admin).json()
    assert f["estado"] == "pendiente_revision" and f["numero"] == 1542
    hist = client.get(f"/facturas/{f['id']}/historial", headers=admin).json()
    assert hist[0]["detalle"]["origen"] == "correo"


def test_correo_de_remitente_no_autorizado(monkeypatch):
    monkeypatch.setattr(settings, "imap_remitentes", "proveedor.com, otro@gmail.com")
    assert correo_entrante.remitente_permitido("Juan <juan@proveedor.com>")
    assert correo_entrante.remitente_permitido("otro@gmail.com")
    assert not correo_entrante.remitente_permitido("x@gmail.com")
    with SessionLocal() as db:
        reg = correo_entrante.procesar_mensaje(db, _correo(remitente="spam@malo.com"))
        assert reg.facturas == [] and "no autorizado" in reg.detalle


def test_correo_con_archivo_repetido_no_rompe(client, admin):
    pdf = pdf_con_qr(url_qr())
    with SessionLocal() as db:
        correo_entrante.procesar_mensaje(db, _correo("<b1@x>", adjunto=pdf))
        reg = correo_entrante.procesar_mensaje(db, _correo("<b2@x>", adjunto=pdf))
        assert reg.facturas == [] and "ya fue importado" in reg.detalle
        assert db.scalar(select(CorreoImportado).where(CorreoImportado.message_id == "<b2@x>")) is not None


def test_revisar_casilla_imap(monkeypatch):
    marcados = []

    class ImapFalso:
        def __init__(self, host, puerto):
            assert (host, puerto) == ("imap.test", 993)

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def login(self, u, p):
            assert u == "facturas@empresa.com"

        def select(self, carpeta):
            return "OK", [b"1"]

        def search(self, charset, criterio):
            assert criterio == "UNSEEN"
            return "OK", [b"7"]

        def fetch(self, num, partes):
            return "OK", [(b"7 (RFC822)", _correo("<c1@x>")), b")"]

        def store(self, num, accion, flag):
            marcados.append((num, flag))

    monkeypatch.setattr(settings, "imap_host", "imap.test")
    monkeypatch.setattr(settings, "imap_usuario", "facturas@empresa.com")
    with SessionLocal() as db:
        assert correo_entrante.revisar_casilla(db, ImapFalso) == 1
        assert db.scalar(select(Factura).where(Factura.creado_por_id.is_(None))) is not None
    assert marcados == [(b"7", "\\Seen")]


# --- Cartas de porte desde PDF ------------------------------------------------------------------


def test_importar_carta_de_porte(client, admin, monkeypatch):
    archivo = {"archivo": ("cpe.pdf", pdf_con_qr("CPE 10100012345678"), "application/pdf")}
    assert client.post("/cartas-porte/importar", headers=admin, files=archivo).status_code == 422  # sin IA

    monkeypatch.setattr(ia, "disponible", lambda: True)
    ext = carta_porte.CartaPorteExtraida(
        numero_ctg="10100-012345678", fecha_carga="2026-04-10", grano="Soja", kilos_brutos=45000, kilos_tara=15000,
        destino="Puerto Timbúes", transportista_cuit="20-12345678-6", patente_camion="ab 123 cd")
    monkeypatch.setattr(ia, "llamar", lambda *a, **k: (ext, None))
    r = client.post("/cartas-porte/importar", headers=admin, files=archivo)
    assert r.status_code == 202, r.text
    assert r.json()["estado"] == "procesando"
    cid = r.json()["id"]
    procesar_cola()
    cp = client.get(f"/cartas-porte/{cid}", headers=admin).json()
    assert cp["estado"] == "borrador"
    assert (cp["numero_ctg"], cp["grano"], cp["kilos_netos"]) == ("10100012345678", "soja", "30000.00")
    assert (cp["transportista_cuit"], cp["patente_camion"]) == ("20123456786", "AB123CD")
    assert client.get(f"/cartas-porte/{cid}/archivo", headers=admin).status_code == 200
    assert client.post("/cartas-porte/importar", headers=admin, files=archivo).status_code == 409
