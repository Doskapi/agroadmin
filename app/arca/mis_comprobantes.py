"""Lectura del archivo de "Mis Comprobantes Recibidos" de ARCA (CSV o Excel).

El formato cambió con los años: se detectan las columnas por nombre (sin importar tildes ni mayúsculas),
el separador del CSV y los decimales con coma o punto.
"""

import csv
import io
import re
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from openpyxl import load_workbook


@dataclass
class FilaArca:
    fecha: date
    tipo_comprobante: int
    punto_venta: int
    numero: int
    cuit_emisor: str
    razon_social: str | None
    total: Decimal | None
    moneda: str
    cae: str | None


class ArchivoInvalido(ValueError):
    pass


def _norm(s: object) -> str:
    s = unicodedata.normalize("NFKD", str(s or ""))
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


# nombre normalizado de columna -> campo (se toma la primera que coincida con el inicio)
COLUMNAS = {
    "fecha": "fecha", "fecha de emision": "fecha",
    "tipo": "tipo", "tipo de comprobante": "tipo",
    "punto de venta": "punto_venta",
    "numero desde": "numero", "numero de comprobante": "numero", "numero": "numero",
    "nro doc emisor": "cuit", "nro doc emisor cuit": "cuit", "cuit emisor": "cuit", "nro doc vendedor": "cuit",
    "denominacion emisor": "razon_social", "denominacion vendedor": "razon_social",
    "imp total": "total", "importe total": "total", "total": "total",
    "moneda": "moneda",
    "cod autorizacion": "cae", "codigo de autorizacion": "cae",
}


def _mapear(encabezado: list) -> dict[str, int]:
    out: dict[str, int] = {}
    for i, h in enumerate(encabezado):
        n = _norm(h)
        campo = COLUMNAS.get(n)
        if campo and campo not in out:
            out[campo] = i
    faltan = {"fecha", "tipo", "punto_venta", "numero", "cuit"} - set(out)
    if faltan:
        raise ArchivoInvalido(f"No se encontraron las columnas: {', '.join(sorted(faltan))}")
    return out


def _numero(v) -> Decimal | None:
    if v is None or v == "":
        return None
    if isinstance(v, (int, float, Decimal)):
        return Decimal(str(v))
    s = str(v).strip().replace("$", "").replace(" ", "")
    if "," in s and "." in s:  # 1.234,56 o 1,234.56
        s = s.replace(".", "").replace(",", ".") if s.rfind(",") > s.rfind(".") else s.replace(",", "")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        return Decimal(s)
    except InvalidOperation:
        return None


def _fecha(v) -> date:
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    s = str(v).strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(s[:10], fmt).date()
        except ValueError:
            continue
    raise ArchivoInvalido(f"Fecha inválida: {s}")


def _entero(v) -> int:
    m = re.match(r"\s*(\d+)", str(v))  # "1 - Factura A" -> 1
    if not m:
        raise ArchivoInvalido(f"Valor numérico inválido: {v}")
    return int(m.group(1))


def _moneda(v) -> str:
    s = _norm(v)
    if not s or s in ("$", "pes", "pesos") or s.startswith("pes"):
        return "PES"
    if s.startswith("dol") or s in ("usd", "us"):
        return "DOL"
    return str(v).strip().upper()[:3]


def _filas_crudas(data: bytes, nombre: str) -> list[list]:
    if nombre.lower().endswith((".xlsx", ".xlsm")) or data[:2] == b"PK":
        ws = load_workbook(io.BytesIO(data), read_only=True, data_only=True).active
        return [list(r) for r in ws.iter_rows(values_only=True)]
    for enc in ("utf-8-sig", "latin-1"):
        try:
            texto = data.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    try:
        dialecto = csv.Sniffer().sniff(texto[:4096], delimiters=";,\t")
    except csv.Error:
        dialecto = csv.excel
    return [r for r in csv.reader(io.StringIO(texto), dialecto)]


def leer(data: bytes, nombre: str = "") -> list[FilaArca]:
    filas = _filas_crudas(data, nombre)
    # El encabezado puede no ser la primera fila (el Excel trae un título arriba)
    for i, fila in enumerate(filas[:10]):
        if any(_norm(c) in ("fecha", "fecha de emision") for c in fila):
            cols = _mapear(fila)
            datos = filas[i + 1:]
            break
    else:
        raise ArchivoInvalido("No parece un archivo de Mis Comprobantes (no hay columna Fecha)")

    out = []
    for fila in datos:
        if not fila or all(c in (None, "") for c in fila):
            continue

        def get(campo: str, fila: list = fila):
            return fila[cols[campo]] if campo in cols and cols[campo] < len(fila) else None

        cuit = "".join(c for c in str(get("cuit") or "") if c.isdigit())
        if len(cuit) != 11:
            continue  # filas de totales u otras
        out.append(FilaArca(
            fecha=_fecha(get("fecha")), tipo_comprobante=_entero(get("tipo")), punto_venta=_entero(get("punto_venta")),
            numero=_entero(get("numero")), cuit_emisor=cuit, razon_social=(str(get("razon_social") or "").strip() or None),
            total=_numero(get("total")), moneda=_moneda(get("moneda")),
            cae=("".join(c for c in str(get("cae") or "") if c.isdigit()) or None),
        ))
    return out
