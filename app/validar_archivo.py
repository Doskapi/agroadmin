"""Validación de archivos subidos: tamaño, tipo real (por contenido, no por lo que dice el navegador)
y PDFs que se puedan procesar."""

import pymupdf
from fastapi import HTTPException, UploadFile, status

from app.config import settings

_BLOQUE = 1024 * 1024


def tipo_por_contenido(data: bytes) -> str | None:
    """Tipo MIME según los primeros bytes del archivo, o None si no es uno soportado."""
    if data.startswith(b"%PDF-"):
        return "application/pdf"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


async def leer_con_limite(archivo: UploadFile) -> bytes:
    """Lee el archivo por partes y corta apenas supera el máximo, sin cargarlo entero antes."""
    maximo = settings.max_upload_mb * 1024 * 1024
    partes, total = [], 0
    while bloque := await archivo.read(_BLOQUE):
        total += len(bloque)
        if total > maximo:
            raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                                f"El archivo supera {settings.max_upload_mb} MB")
        partes.append(bloque)
    return b"".join(partes)


def validar_factura(data: bytes) -> str:
    """Devuelve el tipo MIME real del archivo o lanza 415/422 si no se puede procesar."""
    tipo = tipo_por_contenido(data)
    if tipo is None:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                            "Formato no soportado. Usar PDF, JPG, PNG o WEBP")
    if tipo == "application/pdf":
        try:
            with pymupdf.open(stream=data, filetype="pdf") as doc:
                if doc.needs_pass:
                    raise HTTPException(422, "El PDF está protegido con contraseña")
                if doc.page_count == 0:
                    raise HTTPException(422, "El PDF no tiene páginas")
                if doc.page_count > settings.max_paginas_pdf:
                    raise HTTPException(422, f"El PDF tiene {doc.page_count} páginas (máximo {settings.max_paginas_pdf})")
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(422, "El PDF está dañado o no se puede leer") from None
    return tipo
