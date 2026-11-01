from datetime import date
from decimal import Decimal

from app.extraccion import pdf, qr_arca
from tests.helpers import pdf_con_qr, png_qr, url_qr


def test_parsear_url_qr():
    d = qr_arca.parsear_url(url_qr())
    assert d.cuit_emisor == "30712345678"
    assert (d.tipo_comprobante, d.punto_venta, d.numero) == (1, 3, 1542)
    assert d.fecha == date(2026, 10, 15)
    assert d.importe == Decimal("121000.5")
    assert d.cae == "76543210987654"


def test_url_que_no_es_de_arca():
    assert qr_arca.parsear_url("https://example.com/?p=abc") is None
    assert qr_arca.parsear_url("https://www.afip.gob.ar/fe/qr/?p=no-es-json") is None


def test_leer_qr_de_imagen():
    url = url_qr()
    assert qr_arca.leer_qrs_en_imagen(png_qr(url)) == [url]


def test_leer_qr_de_pdf_renderizado():
    contenido = pdf.leer_pdf(pdf_con_qr(url_qr()))
    encontrados = [t for png in contenido.paginas_png for t in qr_arca.leer_qrs_en_imagen(png)]
    assert qr_arca.primer_qr_valido(encontrados).numero == 1542


def test_link_en_pdf():
    contenido = pdf.leer_pdf(pdf_con_qr(url_qr(), con_link=True))
    assert qr_arca.primer_qr_valido(contenido.links).numero == 1542
