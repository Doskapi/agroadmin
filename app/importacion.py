"""Alta de facturas desde un archivo (pantalla de importación o correo entrante)."""

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import storage, validar_archivo
from app.auditoria import auditar
from app.extraccion import pipeline
from app.models import Archivo, EstadoFactura, Factura


def guardar_archivo(db: Session, data: bytes, nombre: str, usuario_id: int | None,
                    validar=validar_archivo.validar_factura) -> Archivo:
    """Valida el archivo y lo guarda (o devuelve el existente si ya se subió el mismo)."""
    content_type = validar(data)  # tipo real, no el que declara el navegador o el correo
    digest = storage.sha256(data)
    existente = db.scalar(select(Archivo).where(Archivo.sha256 == digest))
    if existente:
        return existente
    archivo = Archivo(nombre_original=(nombre or "sin_nombre")[:255], content_type=content_type,
                      ruta=storage.guardar(data, content_type), sha256=digest, tamanio=len(data),
                      subido_por_id=usuario_id)
    db.add(archivo)
    db.flush()
    return archivo


def importar_factura(db: Session, data: bytes, nombre: str, usuario_id: int | None, origen: str = "importacion",
                     **detalle) -> Factura:
    """Crea la factura en estado `procesando` y encola su lectura. No hace commit.
    Lanza HTTPException (415/422/409) si el archivo no sirve o ya fue importado."""
    archivo = guardar_archivo(db, data, nombre, usuario_id)
    previa = db.scalar(select(Factura).where(Factura.archivo_id == archivo.id))
    if previa:
        raise HTTPException(409, f"Este archivo ya fue importado como factura #{previa.id}")
    factura = Factura(estado=EstadoFactura.procesando, archivo_id=archivo.id, creado_por_id=usuario_id)
    db.add(factura)
    db.flush()
    auditar(db, usuario_id, "factura_creada", "factura", factura.id, origen=origen, archivo=archivo.nombre_original,
            **detalle)
    pipeline.encolar(db, factura)
    return factura
