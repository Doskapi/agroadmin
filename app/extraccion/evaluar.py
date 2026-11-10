"""Compara modelos de Claude leyendo facturas ya confirmadas, contra los datos oficiales del QR de ARCA.

Sirve para decidir si un modelo más barato alcanza. Cada corrida LLAMA A LA API Y CUESTA PLATA:
empezá con pocas facturas.

    python -m app.extraccion.evaluar --modelos claude-opus-5-5 claude-sonnet-5-5 claude-haiku-5-5 --limite 20

Se mide, por modelo: aciertos por campo (CUIT, tipo, punto de venta, número, fecha, total), cuántas facturas
salieron perfectas, tokens y costo estimado por factura.
"""

import argparse
from dataclasses import dataclass, field
from decimal import Decimal

from sqlalchemy import select

from app import storage
from app.db import SessionLocal
from app.extraccion import ia
from app.models import Archivo, EstadoFactura, Factura

# Precio en US$ por millón de tokens (entrada, salida). Revisar en https://platform.claude.com/pricing
PRECIOS = {
    "claude-opus-5-5": (4.00, 20.00),
    "claude-sonnet-5-5": (2.00, 10.00),
    "claude-haiku-5-5": (0.10, 0.50),
}
CAMPOS = ("cuit_emisor", "tipo_comprobante", "punto_venta", "numero", "fecha_emision", "total")


@dataclass
class Resultado:
    modelo: str
    facturas: int = 0
    perfectas: int = 0
    errores: int = 0
    aciertos: dict[str, int] = field(default_factory=lambda: dict.fromkeys(CAMPOS, 0))
    tokens_entrada: int = 0
    tokens_salida: int = 0

    @property
    def costo(self) -> float | None:
        if self.modelo not in PRECIOS:
            return None
        pe, ps = PRECIOS[self.modelo]
        return (self.tokens_entrada * pe + self.tokens_salida * ps) / 1_000_000


def _igual(campo: str, extraido, esperado) -> bool:
    if extraido is None or esperado is None:
        return extraido == esperado
    if campo == "total":
        return abs(Decimal(str(extraido)) - Decimal(str(esperado))) <= Decimal("0.01")
    return str(extraido)[:10] == str(esperado)[:10]


def casos(limite: int) -> list[tuple[bytes, str, dict]]:
    """Facturas confirmadas que tienen archivo y QR: el QR da la respuesta correcta."""
    with SessionLocal() as db:
        facturas = db.scalars(
            select(Factura).where(Factura.estado == EstadoFactura.confirmada, Factura.archivo_id.is_not(None))
            .order_by(Factura.id.desc())
        ).all()
        out = []
        for f in facturas:
            qr = (f.datos_extraidos or {}).get("qr")
            if not qr:
                continue
            archivo = db.get(Archivo, f.archivo_id)
            esperado = {c: getattr(f, c) for c in CAMPOS}  # lo confirmado por una persona
            out.append((storage.leer(archivo.ruta), archivo.content_type, esperado))
            if len(out) >= limite:
                break
        return out


def evaluar(modelo: str, lista: list[tuple[bytes, str, dict]], effort: str | None = None) -> Resultado:
    r = Resultado(modelo)
    for data, tipo, esperado in lista:
        r.facturas += 1
        try:
            ext, uso = ia.extraer_con_uso(data, tipo, modelo=modelo, effort=effort)
        except ia.ErrorExtraccionIA as e:
            print(f"  {modelo}: error ({e})")
            r.errores += 1
            continue
        r.tokens_entrada += uso.tokens_entrada
        r.tokens_salida += uso.tokens_salida
        ok = {c: _igual(c, getattr(ext, c), esperado[c]) for c in CAMPOS}
        for c, bien in ok.items():
            r.aciertos[c] += bien
        r.perfectas += all(ok.values())
    return r


def informe(resultados: list[Resultado]) -> str:
    lineas = [f"{'Modelo':<20} {'Perfectas':>10} {'Errores':>8} "
              + " ".join(f"{c[:8]:>8}" for c in CAMPOS) + f" {'US$/fact.':>10}"]
    for r in resultados:
        n = max(r.facturas, 1)
        costo = f"{r.costo / n:.4f}" if r.costo is not None else "?"
        lineas.append(f"{r.modelo:<20} {r.perfectas / n:>9.0%} {r.errores:>8} "
                      + " ".join(f"{r.aciertos[c] / n:>8.0%}" for c in CAMPOS) + f" {costo:>10}")
    return "\n".join(lineas)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--modelos", nargs="+", default=list(PRECIOS))
    p.add_argument("--limite", type=int, default=10, help="cuántas facturas (cada una cuesta una llamada por modelo)")
    p.add_argument("--effort", choices=["low", "medium", "high"], default=None)
    args = p.parse_args()
    if not ia.disponible():
        raise SystemExit("Falta ANTHROPIC_API_KEY")
    lista = casos(args.limite)
    if not lista:
        raise SystemExit("No hay facturas confirmadas con QR de ARCA para comparar")
    print(f"Comparando {len(args.modelos)} modelo(s) sobre {len(lista)} factura(s)…")
    print(informe([evaluar(m, lista, args.effort) for m in args.modelos]))


if __name__ == "__main__":
    main()
