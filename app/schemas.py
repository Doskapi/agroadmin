"""Esquemas de entrada/salida de la API."""

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.config import password_debil
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


class LoginOut(BaseModel):
    # Solo para clientes de la API; el navegador usa la cookie de sesión.
    access_token: str | None = None
    token_type: str = "bearer"
    requiere_2fa: bool = False
    desafio: str | None = None


class Login2FA(BaseModel):
    desafio: str
    codigo: str = Field(min_length=6, max_length=10)


class CodigoIn(BaseModel):
    codigo: str = Field(min_length=6, max_length=10)


class Desactivar2FA(BaseModel):
    password: str
    codigo: str = Field(min_length=6, max_length=10)


class Inicio2FA(BaseModel):
    secreto: str
    uri: str
    qr_png: str  # base64


class SesionOut(ORM):
    id: int
    creada: datetime
    ultima_actividad: datetime
    ip: str | None
    user_agent: str | None
    actual: bool = False


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


def _password_fuerte(v: str | None) -> str | None:
    if v is not None and (motivo := password_debil(v)):
        raise ValueError(f"La contraseña {motivo}")
    return v


Password = Annotated[str, AfterValidator(_password_fuerte)]


class UsuarioIn(BaseModel):
    email: EmailStr
    nombre: str
    password: Password
    roles: list[str] = []


class CambiarPassword(BaseModel):
    actual: str
    nueva: Password


class Recuperar(BaseModel):
    email: str = Field(max_length=255)


class Restablecer(BaseModel):
    token: str
    nueva: Password


class UsuarioUpdate(BaseModel):
    nombre: str | None = None
    password: Password | None = None
    activo: bool | None = None
    roles: list[str] | None = None


class UsuarioOut(ORM):
    id: int
    email: str
    nombre: str
    activo: bool
    totp_activo: bool = False
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


class UsuarioYo(UsuarioOut):
    debe_activar_2fa: bool = False


# --- Catálogos -------------------------------------------------------------


class ProveedorIn(BaseModel):
    cuit: Cuit
    razon_social: str
    condicion_iva: str | None = None
    email: str | None = None
    telefono: str | None = None
    categoria_id: int | None = None


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
    insumo_id: int | None = None


class FacturaItemOut(ORM, FacturaItemIn):
    id: int


class ImputacionIn(BaseModel):
    campo_id: int
    lote_id: int | None = None
    porcentaje: Decimal = Field(gt=0, le=100)


class ImputacionOut(ORM, ImputacionIn):
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
    imputaciones: list[ImputacionIn] = []


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
    # Lista vacía = sin reparto (vuelve a usar campo_id/lote_id)
    imputaciones: list[ImputacionIn] | None = None


class PagoIn(BaseModel):
    fecha: date
    monto: Decimal = Field(gt=0)
    medio: Literal["transferencia", "cheque", "echeq", "efectivo", "tarjeta", "compensacion", "otro"]
    referencia: str | None = Field(default=None, max_length=128)
    observaciones: str | None = None


class PagoOut(ORM, PagoIn):
    id: int
    factura_id: int


class FacturaOut(ORM, FacturaBase):
    id: int
    estado: EstadoFactura
    pagos: list[PagoOut] = []
    pagado: Decimal = Decimal(0)
    saldo: Decimal | None = None
    arca_resultado: str | None = None
    arca_verificado: datetime | None = None
    arca_observaciones: str | None = None
    archivo_id: int | None
    datos_extraidos: dict | None
    error_extraccion: str | None
    proveedor: ProveedorOut | None
    items: list[FacturaItemOut]
    imputaciones: list[ImputacionOut] = []
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
    cotizacion: Decimal
    categoria_id: int | None = None
    campania_id: int | None = None
    campo_id: int | None = None
    lote_id: int | None = None
    repartida: bool = False
    saldo: Decimal | None = None
    fecha_vencimiento: date | None = None

    @field_validator("repartida", mode="before")
    @classmethod
    def _repartida(cls, v):
        return bool(v)


class CatalogoFacturas(BaseModel):
    items: list[FacturaResumen]
    total: int
    suma_pesos: Decimal


class AccionMasiva(BaseModel):
    ids: list[int] = Field(min_length=1, max_length=500)
    accion: Literal["imputar", "confirmar"]
    # Para "imputar": solo se cambian los campos enviados
    categoria_id: int | None = None
    campania_id: int | None = None
    campo_id: int | None = None
    lote_id: int | None = None


class ResultadoAccionMasiva(BaseModel):
    ok: list[int]
    errores: dict[int, str]


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
    # Mientras se lee el PDF, estos pueden estar vacíos
    fecha_carga: date | None
    grano: str | None
    archivo_id: int | None = None
    error_extraccion: str | None = None
    datos_extraidos: dict | None = None


# --- Reportes --------------------------------------------------------------


class FilaReporte(BaseModel):
    id: int | str | None = None  # id del rubro/proveedor/campo..., o "AAAA-MM" para meses
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


class Dimension(BaseModel):
    id: int | str | None
    clave: str | None


class Celda(BaseModel):
    fila: int | str | None
    columna: int | str | None
    cantidad: int
    total: Decimal


class ReporteCruce(BaseModel):
    filas: list[Dimension]
    columnas: list[Dimension]
    celdas: list[Celda]


class FilaCostoHectarea(BaseModel):
    campo_id: int
    campo: str
    lote_id: int | None
    lote: str | None
    hectareas: Decimal | None
    total: Decimal
    por_hectarea: Decimal | None


class FilaIva(BaseModel):
    periodo: str | None
    cantidad: int
    neto_gravado: Decimal
    no_gravado: Decimal
    iva: Decimal
    percepciones: Decimal
    total: Decimal


class FaltanCotizaciones(BaseModel):
    facturas_sin_cotizacion: int
    primera_fecha_faltante: date | None


# --- Insumos y cotizaciones -------------------------------------------------


class InsumoIn(BaseModel):
    nombre: str = Field(min_length=1, max_length=255)
    unidad: str | None = None
    categoria_id: int | None = None


class InsumoOut(ORM, InsumoIn):
    id: int


class AsignarInsumo(BaseModel):
    insumo_id: int | None
    # Si es True, todos los ítems con la misma descripción (ya cargados y futuros) quedan con este insumo
    recordar: bool = True


class ItemSinInsumo(BaseModel):
    descripcion: str
    ejemplo_item_id: int
    cantidad_items: int
    unidad: str | None


class ResumenInsumo(BaseModel):
    insumo_id: int
    insumo: str
    unidad: str | None
    cantidad: Decimal | None
    total_pesos: Decimal
    precio_promedio: Decimal | None
    ultimo_precio: Decimal | None
    ultima_compra: date | None


class PrecioInsumo(BaseModel):
    factura_id: int
    fecha: date | None
    proveedor: str | None
    descripcion: str
    cantidad: Decimal | None
    unidad: str | None
    precio_unitario: Decimal | None
    moneda: str
    precio_pesos: Decimal | None


class CotizacionIn(BaseModel):
    fecha: date
    valor: Decimal = Field(gt=0)


class CotizacionOut(ORM, CotizacionIn):
    moneda: str


# --- Auditoría -----------------------------------------------------------------


class AuditoriaOut(ORM):
    id: int
    fecha: datetime
    usuario_id: int | None
    usuario: str | None = None
    accion: str
    entidad: str | None
    entidad_id: str | None
    detalle: dict | None
    ip: str | None


class PaginaAuditoria(BaseModel):
    items: list[AuditoriaOut]
    total: int


class AnularIn(BaseModel):
    motivo: str = Field(min_length=3, max_length=500)


# --- Pagos ---------------------------------------------------------------------


class FacturaAPagar(BaseModel):
    id: int
    proveedor: str | None
    comprobante: str
    fecha_emision: date | None
    vencimiento: date | None
    dias: int | None  # negativos: vencida hace N días
    moneda: str
    total: Decimal
    saldo: Decimal
    saldo_pesos: Decimal


class CuentasAPagar(BaseModel):
    facturas: list[FacturaAPagar]
    vencido_pesos: Decimal
    proximos_7_dias_pesos: Decimal
    total_pesos: Decimal


# --- Ventas de granos y margen ---------------------------------------------------


class VentaIn(BaseModel):
    fecha: date
    campania_id: int | None = None
    campo_id: int | None = None
    lote_id: int | None = None
    grano: str = Field(min_length=1, max_length=64)
    kilos: Decimal = Field(gt=0)
    precio_tonelada: Decimal | None = None
    total: Decimal = Field(gt=0)
    moneda: Literal["PES", "DOL"] = "PES"
    cotizacion: Decimal = Field(default=Decimal(1), gt=0)
    comprador: str | None = None
    comprobante: str | None = None
    observaciones: str | None = None


class VentaOut(ORM, VentaIn):
    id: int


class FilaMargen(BaseModel):
    id: int | str | None
    clave: str | None
    hectareas: Decimal | None
    kilos: Decimal
    rinde_kg_ha: Decimal | None
    ingresos: Decimal
    gastos: Decimal
    margen: Decimal
    margen_ha: Decimal | None


# --- ARCA ------------------------------------------------------------------------


class ResultadoImportacionArca(BaseModel):
    leidos: int
    nuevos: int
    desde: date | None
    hasta: date | None


class ComprobanteArcaOut(ORM):
    id: int
    fecha: date
    cuit_emisor: str
    razon_social: str | None
    tipo_comprobante: int
    punto_venta: int
    numero: int
    total: Decimal | None
    moneda: str


class Diferencia(BaseModel):
    factura_id: int
    arca: ComprobanteArcaOut
    total_cargado: Decimal | None


class Conciliacion(BaseModel):
    desde: date | None
    hasta: date | None
    coinciden: int
    faltan_cargar: list[ComprobanteArcaOut]  # en ARCA, no en el sistema
    no_estan_en_arca: list[FacturaResumen]  # cargadas y confirmadas, ARCA no las tiene
    diferencias: list[Diferencia]  # mismo comprobante, distinto total
