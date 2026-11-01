"""Guardado de archivos en disco, deduplicados por hash."""

import hashlib
import mimetypes
from pathlib import Path

from app.config import settings


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def guardar(data: bytes, content_type: str) -> str:
    digest = sha256(data)
    ext = mimetypes.guess_extension(content_type) or ""
    ruta = Path(settings.storage_dir) / digest[:2] / f"{digest}{ext}"
    ruta.parent.mkdir(parents=True, exist_ok=True)
    if not ruta.exists():
        ruta.write_bytes(data)
    return str(ruta)


def leer(ruta: str) -> bytes:
    return Path(ruta).read_bytes()
