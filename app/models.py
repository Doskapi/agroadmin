"""Modelos de la base de datos.

Montos en Numeric(16, 2) para no perder centavos; cantidades y kilos con más decimales.
"""

import enum
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Column,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Table,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

Monto = Numeric(16, 2)
JsonDoc = JSON().with_variant(JSONB(), "postgresql")


class Base(DeclarativeBase):
    pass


class Timestamps:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


# ---------------------------------------------------------------------------
# Usuarios, roles y permisos
# ---------------------------------------------------------------------------

usuario_roles = Table(
    "usuario_roles",
    Base.metadata,
    Column("usuario_id", ForeignKey("usuarios.id", ondelete="CASCADE"), primary_key=True),
    Column("rol_id", ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
)

rol_permisos = Table(
    "rol_permisos",
    Base.metadata,
    Column("rol_id", ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
    Column("permiso_codigo", ForeignKey("permisos.codigo", ondelete="CASCADE"), primary_key=True),
)


class Permiso(Base):
    __tablename__ = "permisos"

    codigo: Mapped[str] = mapped_column(String(64), primary_key=True)
    descripcion: Mapped[str] = mapped_column(String(255))


class Rol(Base):
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(64), unique=True)
    descripcion: Mapped[str | None] = mapped_column(String(255))
    permisos: Mapped[list[Permiso]] = relationship(secondary=rol_permisos, lazy="selectin")


class Usuario(Timestamps, Base):
    __tablename__ = "usuarios"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    nombre: Mapped[str] = mapped_column(String(255))
    password_hash: Mapped[str] = mapped_column(String(255))
    activo: Mapped[bool] = mapped_column(default=True)
    # Verificación en dos pasos (TOTP). El secreto se guarda al iniciar el alta y se activa al confirmar un código.
    totp_secreto: Mapped[str | None] = mapped_column(String(64))
    totp_activo: Mapped[bool] = mapped_column(default=False, server_default="false")
    totp_ultimo_paso: Mapped[int | None] = mapped_column()  # evita reusar el mismo código
    roles: Mapped[list[Rol]] = relationship(secondary=usuario_roles, lazy="selectin")

    @property
    def permisos(self) -> set[str]:
        return {p.codigo for rol in self.roles for p in rol.permisos}


class Sesion(Base):
    """Sesión iniciada. El token solo lo tiene el navegador (cookie); acá se guarda su hash."""

    __tablename__ = "sesiones"

    id: Mapped[int] = mapped_column(primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id", ondelete="CASCADE"), index=True)
    creada: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    ultima_actividad: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expira: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revocada: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ip: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(255))


class TokenRecuperacion(Base):
    __tablename__ = "tokens_recuperacion"

    id: Mapped[int] = mapped_column(primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id", ondelete="CASCADE"))
    expira: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    usado: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Auditoria(Base):
    """Quién hizo qué y cuándo. `detalle` guarda, por ejemplo, los valores anteriores y nuevos de una edición."""

    __tablename__ = "auditoria"
    __table_args__ = (Index("ix_auditoria_entidad", "entidad", "entidad_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    fecha: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id", ondelete="SET NULL"), index=True)
    accion: Mapped[str] = mapped_column(String(64), index=True)
    entidad: Mapped[str | None] = mapped_column(String(64))
    entidad_id: Mapped[str | None] = mapped_column(String(64))
    detalle: Mapped[dict | None] = mapped_column(JsonDoc)
    ip: Mapped[str | None] = mapped_column(String(64))


# ---------------------------------------------------------------------------
# Catálogos
# ---------------------------------------------------------------------------


class Proveedor(Timestamps, Base):
    __tablename__ = "proveedores"

    id: Mapped[int] = mapped_column(primary_key=True)
    cuit: Mapped[str] = mapped_column(String(11), unique=True, index=True)
    razon_social: Mapped[str] = mapped_column(String(255))
    condicion_iva: Mapped[str | None] = mapped_column(String(64))
    email: Mapped[str | None] = mapped_column(String(255))
    telefono: Mapped[str | None] = mapped_column(String(64))
    # Rubro con el que llegan sus facturas si nadie indica otro
    categoria_id: Mapped[int | None] = mapped_column(ForeignKey("categorias.id", ondelete="SET NULL"))


class Campo(Timestamps, Base):
    __tablename__ = "campos"

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(128), unique=True)
    ubicacion: Mapped[str | None] = mapped_column(String(255))
    hectareas: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    lotes: Mapped[list["Lote"]] = relationship(back_populates="campo", cascade="all, delete-orphan")


class Lote(Timestamps, Base):
    __tablename__ = "lotes"
    __table_args__ = (UniqueConstraint("campo_id", "nombre"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    campo_id: Mapped[int] = mapped_column(ForeignKey("campos.id", ondelete="CASCADE"))
    nombre: Mapped[str] = mapped_column(String(128))
    hectareas: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    campo: Mapped[Campo] = relationship(back_populates="lotes")


class Campania(Timestamps, Base):
    __tablename__ = "campanias"

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(32), unique=True)  # ej. "2025/26"
    fecha_inicio: Mapped[date]
    fecha_fin: Mapped[date]


class Categoria(Base):
    """Rubro de gasto: semillas, agroquímicos, fertilizantes, combustible, fletes..."""

    __tablename__ = "categorias"

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(64), unique=True)


# ---------------------------------------------------------------------------
# Archivos y facturas
# ---------------------------------------------------------------------------


class Archivo(Base):
    __tablename__ = "archivos"

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre_original: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(128))
    ruta: Mapped[str] = mapped_column(String(512))
    sha256: Mapped[str] = mapped_column(String(64), unique=True)
    tamanio: Mapped[int]
    subido_por_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class EstadoFactura(str, enum.Enum):
    procesando = "procesando"
    pendiente_revision = "pendiente_revision"
    confirmada = "confirmada"
    error = "error"
    anulada = "anulada"


class Factura(Timestamps, Base):
    __tablename__ = "facturas"
    __table_args__ = (
        UniqueConstraint("cuit_emisor", "tipo_comprobante", "punto_venta", "numero", name="uq_factura_comprobante"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    estado: Mapped[EstadoFactura] = mapped_column(
        Enum(EstadoFactura, name="estado_factura"), default=EstadoFactura.pendiente_revision, index=True
    )

    proveedor_id: Mapped[int | None] = mapped_column(ForeignKey("proveedores.id"), index=True)
    cuit_emisor: Mapped[str | None] = mapped_column(String(11))
    # Código ARCA: 1=A, 6=B, 11=C, 3=NC A, etc.
    tipo_comprobante: Mapped[int | None]
    punto_venta: Mapped[int | None]
    numero: Mapped[int | None]
    fecha_emision: Mapped[date | None] = mapped_column(Date, index=True)
    fecha_vencimiento: Mapped[date | None] = mapped_column(Date)

    moneda: Mapped[str] = mapped_column(String(3), default="PES")
    cotizacion: Mapped[Decimal] = mapped_column(Numeric(14, 6), default=1)
    neto_gravado: Mapped[Decimal | None] = mapped_column(Monto)
    no_gravado: Mapped[Decimal | None] = mapped_column(Monto)
    iva: Mapped[Decimal | None] = mapped_column(Monto)
    percepciones: Mapped[Decimal | None] = mapped_column(Monto)
    total: Mapped[Decimal | None] = mapped_column(Monto)

    cae: Mapped[str | None] = mapped_column(String(14))
    cae_vencimiento: Mapped[date | None] = mapped_column(Date)

    campania_id: Mapped[int | None] = mapped_column(ForeignKey("campanias.id"), index=True)
    campo_id: Mapped[int | None] = mapped_column(ForeignKey("campos.id"), index=True)
    lote_id: Mapped[int | None] = mapped_column(ForeignKey("lotes.id"))
    categoria_id: Mapped[int | None] = mapped_column(ForeignKey("categorias.id"), index=True)

    archivo_id: Mapped[int | None] = mapped_column(ForeignKey("archivos.id"))
    datos_extraidos: Mapped[dict | None] = mapped_column(JsonDoc)  # lo que devolvió la extracción, para auditar
    error_extraccion: Mapped[str | None] = mapped_column(Text)
    observaciones: Mapped[str | None] = mapped_column(Text)
    creado_por_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))

    proveedor: Mapped[Proveedor | None] = relationship(lazy="joined")
    items: Mapped[list["FacturaItem"]] = relationship(
        back_populates="factura", cascade="all, delete-orphan", order_by="FacturaItem.id", lazy="selectin"
    )
    # Si tiene imputaciones, el gasto se reparte entre esos campos/lotes y se ignoran campo_id/lote_id.
    imputaciones: Mapped[list["FacturaImputacion"]] = relationship(
        cascade="all, delete-orphan", order_by="FacturaImputacion.id", lazy="selectin"
    )

    @property
    def repartida(self) -> bool:
        return bool(self.imputaciones)


class FacturaItem(Base):
    __tablename__ = "factura_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    factura_id: Mapped[int] = mapped_column(ForeignKey("facturas.id", ondelete="CASCADE"), index=True)
    descripcion: Mapped[str] = mapped_column(String(512))
    cantidad: Mapped[Decimal | None] = mapped_column(Numeric(16, 4))
    unidad: Mapped[str | None] = mapped_column(String(32))
    precio_unitario: Mapped[Decimal | None] = mapped_column(Numeric(16, 4))
    alicuota_iva: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    subtotal: Mapped[Decimal | None] = mapped_column(Monto)
    insumo_id: Mapped[int | None] = mapped_column(ForeignKey("insumos.id", ondelete="SET NULL"), index=True)
    factura: Mapped[Factura] = relationship(back_populates="items")


class FacturaImputacion(Base):
    """Parte de una factura asignada a un campo (y opcionalmente a un lote)."""

    __tablename__ = "factura_imputaciones"

    id: Mapped[int] = mapped_column(primary_key=True)
    factura_id: Mapped[int] = mapped_column(ForeignKey("facturas.id", ondelete="CASCADE"), index=True)
    campo_id: Mapped[int] = mapped_column(ForeignKey("campos.id"))
    lote_id: Mapped[int | None] = mapped_column(ForeignKey("lotes.id"))
    porcentaje: Mapped[Decimal] = mapped_column(Numeric(7, 4))


# ---------------------------------------------------------------------------
# Insumos y cotizaciones
# ---------------------------------------------------------------------------


class Insumo(Timestamps, Base):
    """Producto normalizado (ej. "Glifosato 62%") para seguir precios y volúmenes comprados."""

    __tablename__ = "insumos"

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(255), unique=True)
    unidad: Mapped[str | None] = mapped_column(String(32))
    categoria_id: Mapped[int | None] = mapped_column(ForeignKey("categorias.id", ondelete="SET NULL"))


class InsumoAlias(Base):
    """Descripción de ítem (normalizada) que corresponde a un insumo: se aplica sola a los ítems nuevos."""

    __tablename__ = "insumo_alias"

    descripcion: Mapped[str] = mapped_column(String(512), primary_key=True)
    insumo_id: Mapped[int] = mapped_column(ForeignKey("insumos.id", ondelete="CASCADE"), index=True)


class Cotizacion(Base):
    """Cotización del dólar (pesos por unidad) por día, para expresar reportes en moneda dura."""

    __tablename__ = "cotizaciones"

    moneda: Mapped[str] = mapped_column(String(3), primary_key=True, default="DOL")
    fecha: Mapped[date] = mapped_column(Date, primary_key=True)
    valor: Mapped[Decimal] = mapped_column(Numeric(14, 6))


# ---------------------------------------------------------------------------
# Cartas de porte
# ---------------------------------------------------------------------------


class EstadoCartaPorte(str, enum.Enum):
    borrador = "borrador"
    emitida = "emitida"
    descargada = "descargada"
    anulada = "anulada"


class CartaPorte(Timestamps, Base):
    __tablename__ = "cartas_porte"

    id: Mapped[int] = mapped_column(primary_key=True)
    estado: Mapped[EstadoCartaPorte] = mapped_column(
        Enum(EstadoCartaPorte, name="estado_carta_porte"), default=EstadoCartaPorte.borrador, index=True
    )
    numero_ctg: Mapped[str | None] = mapped_column(String(20), unique=True)
    fecha_carga: Mapped[date] = mapped_column(Date, index=True)

    campania_id: Mapped[int | None] = mapped_column(ForeignKey("campanias.id"), index=True)
    campo_id: Mapped[int | None] = mapped_column(ForeignKey("campos.id"), index=True)
    lote_id: Mapped[int | None] = mapped_column(ForeignKey("lotes.id"))
    grano: Mapped[str] = mapped_column(String(64))  # soja, maíz, trigo...

    kilos_brutos: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    kilos_tara: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    kilos_netos: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    kilos_descargados: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))

    destino: Mapped[str | None] = mapped_column(String(255))
    destinatario_cuit: Mapped[str | None] = mapped_column(String(11))
    transportista_cuit: Mapped[str | None] = mapped_column(String(11))
    chofer_cuit: Mapped[str | None] = mapped_column(String(11))
    patente_camion: Mapped[str | None] = mapped_column(String(10))
    patente_acoplado: Mapped[str | None] = mapped_column(String(10))
    km_recorrer: Mapped[int | None] = mapped_column(Integer)
    observaciones: Mapped[str | None] = mapped_column(Text)
    creado_por_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))


# ---------------------------------------------------------------------------
# Cola de trabajos en segundo plano
# ---------------------------------------------------------------------------


class EstadoTrabajo(str, enum.Enum):
    pendiente = "pendiente"
    en_curso = "en_curso"
    hecho = "hecho"
    error = "error"


class Trabajo(Base):
    """Tarea para el worker (ej. leer una factura importada). Sobrevive a reinicios de la API."""

    __tablename__ = "trabajos"
    # El worker busca los pendientes por fecha
    __table_args__ = (Index("ix_trabajos_pendientes", "ejecutar_desde",
                            postgresql_where=text("estado IN ('pendiente', 'en_curso')")),)

    id: Mapped[int] = mapped_column(primary_key=True)
    tipo: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict] = mapped_column(JsonDoc, default=dict)
    estado: Mapped[EstadoTrabajo] = mapped_column(
        Enum(EstadoTrabajo, name="estado_trabajo"), default=EstadoTrabajo.pendiente, index=True)
    intentos: Mapped[int] = mapped_column(default=0)
    max_intentos: Mapped[int] = mapped_column(default=5)
    ejecutar_desde: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    bloqueado_hasta: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(Text)
    creado: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    terminado: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class TareaProgramada(Base):
    """Última ejecución de cada tarea periódica del worker (y su latido, en la fila `_latido`)."""

    __tablename__ = "tareas_programadas"

    nombre: Mapped[str] = mapped_column(String(64), primary_key=True)
    ultima_ejecucion: Mapped[datetime] = mapped_column(DateTime(timezone=True))
