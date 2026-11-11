"""Aviso diario por correo de facturas vencidas o que vencen en la semana."""

from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import correo
from app.models import Usuario
from app.routers.pagos import pendientes


def destinatarios(db: Session) -> list[Usuario]:
    return [u for u in db.scalars(select(Usuario).where(Usuario.activo))
            if u.permisos & {"pagos:escribir", "facturas:confirmar"}]


def armar_texto(db: Session) -> str | None:
    cuentas = pendientes(db, hasta=date.today() + timedelta(days=7))
    if not cuentas.facturas:
        return None
    lineas = ["Facturas vencidas o que vencen en los próximos 7 días:", ""]
    for f in cuentas.facturas:
        estado = f"vencida hace {-f.dias} día(s)" if f.dias is not None and f.dias < 0 else (
            "vence hoy" if f.dias == 0 else f"vence en {f.dias} día(s)")
        lineas.append(f"- {f.proveedor or 'Sin proveedor'} · {f.comprobante} · {estado} · saldo $ {f.saldo_pesos:,.2f}")
    lineas += ["", f"Vencido: $ {cuentas.vencido_pesos:,.2f}", f"Próximos 7 días: $ {cuentas.proximos_7_dias_pesos:,.2f}"]
    return "\n".join(lineas)


def enviar(db: Session) -> int:
    texto = armar_texto(db)
    if not texto:
        return 0
    return sum(correo.enviar(u.email, "Gestión Agro: facturas a pagar", texto) for u in destinatarios(db))
