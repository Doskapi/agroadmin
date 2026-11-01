"""Procesamiento de una factura importada: QR de ARCA -> IA -> factura en estado pendiente_revision."""

import logging
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import storage
from app.db import SessionLocal
from app.extraccion import ia, pdf, qr_arca
from app.models import Archivo, Categoria, EstadoFactura, Factura, FacturaItem, Proveedor

log = logging.getLogger(__name__)


def _dec(v) -> Decimal | None:
    return None if v is None else Decimal(str(v)).quantize(Decimal("0.01"))


def _fecha(v: str | None) -> date | None:
    try:
        return date.fromisoformat(v[:10]) if v else None
    except ValueError:
        return None


def _buscar_qr(data: bytes, content_type: str) -> qr_arca.DatosQR | None:
    if content_type == "application/pdf":
        contenido = pdf.leer_pdf(data)
        candidatos = contenido.links + qr_arca.buscar_urls_en_texto(contenido.texto)
        for png in contenido.paginas_png:
            if qr_arca.primer_qr_valido(candidatos):
                break
            candidatos += qr_arca.leer_qrs_en_imagen(png)
    else:
        candidatos = qr_arca.leer_qrs_en_imagen(data)
    return qr_arca.primer_qr_valido(candidatos)


def _aplicar_ia(db: Session, factura: Factura, ext: ia.FacturaExtraida) -> None:
    factura.cuit_emisor = ext.cuit_emisor
    factura.tipo_comprobante = ext.tipo_comprobante
    factura.punto_venta = ext.punto_venta
    factura.numero = ext.numero
    factura.fecha_emision = _fecha(ext.fecha_emision)
    factura.fecha_vencimiento = _fecha(ext.fecha_vencimiento)
    factura.moneda = ext.moneda or "PES"
    factura.cotizacion = Decimal(str(ext.cotizacion or 1))
    factura.neto_gravado = _dec(ext.neto_gravado)
    factura.no_gravado = _dec(ext.no_gravado)
    factura.iva = _dec(ext.iva)
    factura.percepciones = _dec(ext.percepciones)
    factura.total = _dec(ext.total)
    factura.cae = ext.cae
    factura.cae_vencimiento = _fecha(ext.cae_vencimiento)
    factura.items = [
        FacturaItem(
            descripcion=i.descripcion[:512],
            cantidad=None if i.cantidad is None else Decimal(str(i.cantidad)),
            unidad=i.unidad,
            precio_unitario=None if i.precio_unitario is None else Decimal(str(i.precio_unitario)),
            alicuota_iva=None if i.alicuota_iva is None else Decimal(str(i.alicuota_iva)),
            subtotal=_dec(i.subtotal),
        )
        for i in ext.items
    ]
    if ext.categoria_sugerida and not factura.categoria_id:
        cat = db.scalar(select(Categoria).where(func.lower(Categoria.nombre) == ext.categoria_sugerida.lower()))
        if cat:
            factura.categoria_id = cat.id


def _aplicar_qr(factura: Factura, qr: qr_arca.DatosQR, advertencias: list[str]) -> None:
    """El QR es la fuente oficial: pisa lo que haya leído la IA y avisa si no coincidía."""
    pares = {
        "cuit_emisor": qr.cuit_emisor,
        "tipo_comprobante": qr.tipo_comprobante,
        "punto_venta": qr.punto_venta,
        "numero": qr.numero,
        "fecha_emision": qr.fecha,
        "total": qr.importe,
        "moneda": qr.moneda,
        "cotizacion": qr.cotizacion,
        "cae": qr.cae,
    }
    for campo, valor in pares.items():
        if valor is None:
            continue
        actual = getattr(factura, campo)
        if actual is not None and str(actual) != str(valor) and campo != "cotizacion":
            advertencias.append(f"{campo}: la IA leyó {actual}, el QR dice {valor}")
        setattr(factura, campo, valor)


def _vincular_proveedor(db: Session, factura: Factura, ext: ia.FacturaExtraida | None) -> None:
    if not factura.cuit_emisor:
        return
    proveedor = db.scalar(select(Proveedor).where(Proveedor.cuit == factura.cuit_emisor))
    if not proveedor:
        proveedor = Proveedor(
            cuit=factura.cuit_emisor,
            razon_social=(ext.razon_social_emisor if ext and ext.razon_social_emisor else f"CUIT {factura.cuit_emisor}"),
            condicion_iva=ext.condicion_iva_emisor if ext else None,
        )
        db.add(proveedor)
        db.flush()
    factura.proveedor_id = proveedor.id


def _es_duplicada(db: Session, factura: Factura) -> Factura | None:
    if not all([factura.cuit_emisor, factura.tipo_comprobante, factura.punto_venta, factura.numero]):
        return None
    return db.scalar(
        select(Factura).where(
            Factura.id != factura.id,
            Factura.cuit_emisor == factura.cuit_emisor,
            Factura.tipo_comprobante == factura.tipo_comprobante,
            Factura.punto_venta == factura.punto_venta,
            Factura.numero == factura.numero,
        )
    )


def procesar(db: Session, factura: Factura) -> None:
    archivo = db.get(Archivo, factura.archivo_id)
    data = storage.leer(archivo.ruta)
    advertencias: list[str] = []
    extraido: dict = {"fuentes": []}

    ext: ia.FacturaExtraida | None = None
    if ia.disponible():
        try:
            ext = ia.extraer(data, archivo.content_type)
            _aplicar_ia(db, factura, ext)
            extraido["fuentes"].append("ia")
            extraido["ia"] = ext.model_dump()
        except ia.ErrorExtraccionIA as e:
            advertencias.append(str(e))

    try:
        qr = _buscar_qr(data, archivo.content_type)
    except Exception:  # un PDF roto no debe impedir guardar lo que dio la IA
        log.exception("Error buscando QR en archivo %s", archivo.id)
        qr = None
    if qr:
        _aplicar_qr(factura, qr, advertencias)
        extraido["fuentes"].append("qr_arca")
        extraido["qr"] = qr.to_json()

    if factura.total is not None and factura.neto_gravado is not None:
        suma = sum((v or 0) for v in (factura.neto_gravado, factura.no_gravado, factura.iva, factura.percepciones))
        if abs(Decimal(suma) - factura.total) > Decimal("1.00"):
            advertencias.append(f"Neto + IVA + otros ({suma}) no coincide con el total ({factura.total})")

    extraido["advertencias"] = advertencias
    factura.datos_extraidos = extraido

    if not extraido["fuentes"]:
        factura.estado = EstadoFactura.error
        factura.error_extraccion = (
            "; ".join(advertencias) or "No se encontró QR de ARCA y la extracción con IA no está configurada"
        )
        return

    _vincular_proveedor(db, factura, ext)
    if dup := _es_duplicada(db, factura):
        factura.estado = EstadoFactura.error
        factura.error_extraccion = f"Comprobante duplicado: ya está cargado como factura #{dup.id}"
        # Liberamos la clave única para que esta fila quede como registro del intento.
        factura.numero = None
        return

    factura.estado = EstadoFactura.pendiente_revision
    factura.error_extraccion = None


def procesar_en_segundo_plano(factura_id: int) -> None:
    """Punto de entrada para BackgroundTasks (abre su propia sesión)."""
    with SessionLocal() as db:
        factura = db.get(Factura, factura_id)
        if not factura:
            return
        try:
            procesar(db, factura)
            db.commit()
        except Exception as e:
            log.exception("Fallo procesando factura %s", factura_id)
            db.rollback()
            factura = db.get(Factura, factura_id)
            factura.estado = EstadoFactura.error
            factura.error_extraccion = f"Error interno: {e}"
            db.commit()
