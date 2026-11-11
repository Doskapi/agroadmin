"""Pagos de facturas y cuentas a pagar."""

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app.auditoria import auditar
from app.deps import DB, requiere
from app.filtros import NOTAS_CREDITO, a_pagar, saldo, vencimiento
from app.models import EstadoFactura, Factura, Pago, Usuario
from app.schemas import CuentasAPagar, FacturaAPagar, FacturaOut, PagoIn

router = APIRouter(tags=["pagos"])
CENTAVO = Decimal("0.01")


TIPOS = {1: "Factura A", 2: "Nota de débito A", 6: "Factura B", 7: "Nota de débito B", 11: "Factura C",
         12: "Nota de débito C", 51: "Factura M"}


def _comprobante(f: Factura) -> str:
    tipo = TIPOS.get(f.tipo_comprobante, f"Tipo {f.tipo_comprobante}" if f.tipo_comprobante else "Factura")
    if f.punto_venta is None or f.numero is None:
        return f"{tipo} #{f.id}"
    return f"{tipo} {f.punto_venta:05d}-{f.numero:08d}"


@router.get("/pagos/pendientes", response_model=CuentasAPagar, dependencies=[requiere("facturas:leer")])
def pendientes(db: DB, proveedor_id: int | None = None, hasta: date | None = None):
    """Facturas confirmadas con saldo, de la que vence primero a la última. `hasta` limita por vencimiento."""
    stmt = select(Factura, saldo(), vencimiento()).where(a_pagar(), saldo() > CENTAVO)
    if proveedor_id:
        stmt = stmt.where(Factura.proveedor_id == proveedor_id)
    if hasta:
        stmt = stmt.where(vencimiento() <= hasta)
    hoy = date.today()
    filas, vencido, proximos, total = [], Decimal(0), Decimal(0), Decimal(0)
    for f, s, vto in db.execute(stmt.order_by(vencimiento().asc().nulls_last(), Factura.id)):
        en_pesos = (s * f.cotizacion).quantize(CENTAVO)
        dias = (vto - hoy).days if vto else None
        filas.append(FacturaAPagar(
            id=f.id, proveedor=f.proveedor.razon_social if f.proveedor else None, comprobante=_comprobante(f),
            fecha_emision=f.fecha_emision, vencimiento=vto, dias=dias, moneda=f.moneda, total=f.total,
            saldo=s.quantize(CENTAVO), saldo_pesos=en_pesos,
        ))
        total += en_pesos
        if dias is not None and dias < 0:
            vencido += en_pesos
        elif dias is not None and dias <= 7:
            proximos += en_pesos
    return CuentasAPagar(facturas=filas, vencido_pesos=vencido, proximos_7_dias_pesos=proximos, total_pesos=total)


@router.post("/facturas/{factura_id}/pagos", response_model=FacturaOut, status_code=201)
def registrar(db: DB, factura_id: int, data: PagoIn, usuario: Usuario = requiere("pagos:escribir")):
    factura = db.get(Factura, factura_id)
    if not factura:
        raise HTTPException(404, "Factura no encontrada")
    if factura.estado != EstadoFactura.confirmada:
        raise HTTPException(409, "Solo se registran pagos de facturas confirmadas")
    if factura.tipo_comprobante in NOTAS_CREDITO:
        raise HTTPException(422, "Las notas de crédito no se pagan")
    if factura.saldo is not None and data.monto > factura.saldo + CENTAVO:
        raise HTTPException(422, f"El pago ({data.monto}) supera el saldo de la factura ({factura.saldo})")
    pago = Pago(factura_id=factura.id, creado_por_id=usuario.id, **data.model_dump())
    pago.monto = data.monto.quantize(CENTAVO)
    db.add(pago)
    db.flush()
    auditar(db, usuario.id, "pago_registrado", "factura", factura.id, monto=data.monto, medio=data.medio,
            fecha=data.fecha, pago=pago.id)
    db.commit()
    db.refresh(factura)
    return factura


@router.delete("/pagos/{pago_id}", response_model=FacturaOut)
def borrar(db: DB, pago_id: int, usuario: Usuario = requiere("pagos:escribir")):
    pago = db.get(Pago, pago_id)
    if not pago:
        raise HTTPException(404, "Pago no encontrado")
    factura = db.get(Factura, pago.factura_id)
    auditar(db, usuario.id, "pago_borrado", "factura", factura.id, monto=pago.monto, fecha=pago.fecha)
    factura.pagos.remove(pago)
    db.commit()
    db.refresh(factura)
    return factura
