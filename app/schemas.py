"""Esquemas de entrada/salida de la API."""

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models import EstadoCartaPorte, EstadoFactura


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


def _solo_digitos(v: str) -> str:
    limpio = "".join(c for c in v if c.isdigit())
    if len(limpio) != 11:
        raise ValueError("El CUIT debe tener 11 dígitos")
    return limpio


# Acepta "20-12345678-9" o "20123456789" y lo guarda sin guiones
Cuit = Annotated[str, AfterValidator(_solo_digitos)]


# --- Auth / usuarios -------------------------------------------------------


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class RolOut(ORM):
    id: int
    nombre: str
    descripcion: str | None
    permisos: list[str]

    @field_validator("permisos", mode="before")
    @classmethod
    def _codigos(cls, v):
        return [p.codigo if hasattr(p, "codigo") else p for p in v]


class RolIn(BaseModel):
    nombre: str
    descripcion: str | None = None
    permisos: list[str] = []


class UsuarioIn(BaseModel):
    email: EmailStr
    nombre: str
    password: str = Field(min_length=8)
    roles: list[str] = []


class UsuarioUpdate(BaseModel):
    nombre: str | None = None
    password: str | None = Field(default=None, min_length=8)
    activo: bool | None = None
    roles: list[str] | None = None


class UsuarioOut(ORM):
    id: int
    email: str
    nombre: str
    activo: bool
    roles: list[str]
    permisos: list[str]

    @field_validator("roles", mode="before")
    @classmethod
    def _nombres(cls, v):
        return [r.nombre if hasattr(r, "nombre") else r for r in v]

    @field_validator("permisos", mode="before")
    @classmethod
    def _ordenar(cls, v):
        return sorted(v)


# --- Catálogos -------------------------------------------------------------


class ProveedorIn(BaseModel):
    cuit: Cuit
    razon_social: str
    condicion_iva: str | None = None
    email: str | None = None
    telefono: str | None = None


class ProveedorOut(ORM, ProveedorIn):
    id: int


class LoteIn(BaseModel):
    nombre: str
    hectareas: Decimal | None = None


class LoteOut(ORM, LoteIn):
    id: int
    campo_id: int


class CampoIn(BaseModel):
    nombre: str
    ubicacion: str | None = None
    hectareas: Decimal | None = None


class CampoOut(ORM, CampoIn):
    id: int
    lotes: list[LoteOut] = []


class CampaniaIn(BaseModel):
    nombre: str
    fecha_inicio: date
    fecha_fin: date


class CampaniaOut(ORM, CampaniaIn):
    id: int


class CategoriaIn(BaseModel):
    nombre: str


class CategoriaOut(ORM, CategoriaIn):
    id: int


# --- Facturas --------------------------------------------------------------


class FacturaItemIn(BaseModel):
    descripcion: str
    cantidad: Decimal | None = None
    unidad: str | None = None
    precio_unitario: Decimal | None = None
    alicuota_iva: Decimal | None = None
    subtotal: Decimal | None = None


class FacturaItemOut(ORM, FacturaItemIn):
    id: int


class FacturaBase(BaseModel):
    proveedor_id: int | None = None
    cuit_emisor: Cuit | None = None
    tipo_comprobante: int | None = None
    punto_venta: int | None = None
    numero: int | None = None
    fecha_emision: date | None = None
    fecha_vencimiento: date | None = None
    moneda: str = "PES"
    cotizacion: Decimal = Decimal(1)
    neto_gravado: Decimal | None = None
    no_gravado: Decimal | None = None
    iva: Decimal | None = None
    percepciones: Decimal | None = None
    total: Decimal | None = None
    cae: str | None = None
    cae_vencimiento: date | None = None
    campania_id: int | None = None
    campo_id: int | None = None
    lote_id: int | None = None
    categoria_id: int | None = None
    observaciones: str | None = None


class FacturaIn(FacturaBase):
    items: list[FacturaItemIn] = []


class FacturaUpdate(BaseModel):
    """Todos los campos opcionales: solo se actualiza lo que se envía."""

    proveedor_id: int | None = None
    cuit_emisor: Cuit | None = None
    tipo_comprobante: int | None = None
    punto_venta: int | None = None
    numero: int | None = None
    fecha_emision: date | None = None
    fecha_vencimiento: date | None = None
    moneda: str | None = None
    cotizacion: Decimal | None = None
    neto_gravado: Decimal | None = None
    no_gravado: Decimal | None = None
    iva: Decimal | None = None
    percepciones: Decimal | None = None
    total: Decimal | None = None
    cae: str | None = None
    cae_vencimiento: date | None = None
    campania_id: int | None = None
    campo_id: int | None = None
    lote_id: int | None = None
    categoria_id: int | None = None
    observaciones: str | None = None
    items: list[FacturaItemIn] | None = None


class FacturaOut(ORM, FacturaBase):
    id: int
    estado: EstadoFactura
    archivo_id: int | None
    datos_extraidos: dict | None
    error_extraccion: str | None
    proveedor: ProveedorOut | None
    items: list[FacturaItemOut]
    created_at: datetime


class FacturaResumen(ORM):
    id: int
    estado: EstadoFactura
    fecha_emision: date | None
    cuit_emisor: str | None
    proveedor: ProveedorOut | None
    tipo_comprobante: int | None
    punto_venta: int | None
    numero: int | None
    total: Decimal | None
    moneda: str


# --- Cartas de porte -------------------------------------------------------


class CartaPorteIn(BaseModel):
    numero_ctg: str | None = None
    fecha_carga: date
    campania_id: int | None = None
    campo_id: int | None = None
    lote_id: int | None = None
    grano: str
    kilos_brutos: Decimal | None = None
    kilos_tara: Decimal | None = None
    kilos_netos: Decimal | None = None
    kilos_descargados: Decimal | None = None
    destino: str | None = None
    destinatario_cuit: Cuit | None = None
    transportista_cuit: Cuit | None = None
    chofer_cuit: Cuit | None = None
    patente_camion: str | None = None
    patente_acoplado: str | None = None
    km_recorrer: int | None = None
    observaciones: str | None = None
    estado: EstadoCartaPorte = EstadoCartaPorte.borrador


class CartaPorteOut(ORM, CartaPorteIn):
    id: int
    created_at: datetime


# --- Reportes --------------------------------------------------------------


class FilaReporte(BaseModel):
    clave: str | None
    cantidad: int
    total: Decimal


class ResumenDashboard(BaseModel):
    total_gastos: Decimal
    cantidad_facturas: int
    pendientes_revision: int
    kilos_despachados: Decimal
    gastos_por_mes: list[FilaReporte]
    gastos_por_categoria: list[FilaReporte]
    top_proveedores: list[FilaReporte]
