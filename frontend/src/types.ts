// Espejo de app/schemas.py. Los montos llegan como string (Decimal) para no perder precisión.

export type Permiso =
  | "usuarios:admin"
  | "catalogos:leer"
  | "catalogos:escribir"
  | "facturas:leer"
  | "facturas:escribir"
  | "facturas:confirmar"
  | "cartas_porte:leer"
  | "cartas_porte:escribir"
  | "reportes:ver";

export interface Usuario {
  id: number;
  email: string;
  nombre: string;
  activo: boolean;
  roles: string[];
  permisos: Permiso[];
}

export interface Rol {
  id: number;
  nombre: string;
  descripcion: string | null;
  permisos: Permiso[];
}

export interface Proveedor {
  id: number;
  cuit: string;
  razon_social: string;
  condicion_iva: string | null;
  email: string | null;
  telefono: string | null;
  categoria_id: number | null;
}

export interface Lote {
  id: number;
  campo_id: number;
  nombre: string;
  hectareas: string | null;
}

export interface Campo {
  id: number;
  nombre: string;
  ubicacion: string | null;
  hectareas: string | null;
  lotes: Lote[];
}

export interface Campania {
  id: number;
  nombre: string;
  fecha_inicio: string;
  fecha_fin: string;
}

export interface Categoria {
  id: number;
  nombre: string;
}

export type EstadoFactura = "procesando" | "pendiente_revision" | "confirmada" | "error" | "anulada";

export interface FacturaItem {
  id?: number;
  descripcion: string;
  cantidad: string | null;
  unidad: string | null;
  precio_unitario: string | null;
  alicuota_iva: string | null;
  subtotal: string | null;
  insumo_id?: number | null;
}

export interface Imputacion {
  id?: number;
  campo_id: number;
  lote_id: number | null;
  porcentaje: string;
}

export interface FacturaCampos {
  proveedor_id: number | null;
  cuit_emisor: string | null;
  tipo_comprobante: number | null;
  punto_venta: number | null;
  numero: number | null;
  fecha_emision: string | null;
  fecha_vencimiento: string | null;
  moneda: string;
  cotizacion: string;
  neto_gravado: string | null;
  no_gravado: string | null;
  iva: string | null;
  percepciones: string | null;
  total: string | null;
  cae: string | null;
  cae_vencimiento: string | null;
  campania_id: number | null;
  campo_id: number | null;
  lote_id: number | null;
  categoria_id: number | null;
  observaciones: string | null;
}

export interface Factura extends FacturaCampos {
  id: number;
  estado: EstadoFactura;
  archivo_id: number | null;
  datos_extraidos: { fuentes?: string[]; advertencias?: string[] } | null;
  error_extraccion: string | null;
  proveedor: Proveedor | null;
  items: FacturaItem[];
  imputaciones: Imputacion[];
  created_at: string;
}

export interface FacturaResumen {
  id: number;
  estado: EstadoFactura;
  fecha_emision: string | null;
  cuit_emisor: string | null;
  proveedor: Proveedor | null;
  tipo_comprobante: number | null;
  punto_venta: number | null;
  numero: number | null;
  total: string | null;
  moneda: string;
  cotizacion: string;
  categoria_id: number | null;
  campania_id: number | null;
  campo_id: number | null;
  lote_id: number | null;
  repartida: boolean;
}

export interface CatalogoFacturas {
  items: FacturaResumen[];
  total: number;
  suma_pesos: string;
}

export interface ResultadoAccionMasiva {
  ok: number[];
  errores: Record<string, string>;
}

export type EstadoCartaPorte = "borrador" | "emitida" | "descargada" | "anulada";

export interface CartaPorte {
  id: number;
  estado: EstadoCartaPorte;
  numero_ctg: string | null;
  fecha_carga: string;
  campania_id: number | null;
  campo_id: number | null;
  lote_id: number | null;
  grano: string;
  kilos_brutos: string | null;
  kilos_tara: string | null;
  kilos_netos: string | null;
  kilos_descargados: string | null;
  destino: string | null;
  destinatario_cuit: string | null;
  transportista_cuit: string | null;
  chofer_cuit: string | null;
  patente_camion: string | null;
  patente_acoplado: string | null;
  km_recorrer: number | null;
  observaciones: string | null;
}

export interface FilaReporte {
  id: number | string | null;
  clave: string | null;
  cantidad: number;
  total: string;
}

export interface Resumen {
  total_gastos: string;
  cantidad_facturas: number;
  pendientes_revision: number;
  kilos_despachados: string;
  gastos_por_mes: FilaReporte[];
  gastos_por_categoria: FilaReporte[];
  top_proveedores: FilaReporte[];
}

export type Agrupar = "mes" | "categoria" | "proveedor" | "campo" | "lote" | "campania";

export interface Dimension {
  id: number | string | null;
  clave: string | null;
}

export interface ReporteCruce {
  filas: Dimension[];
  columnas: Dimension[];
  celdas: { fila: number | string | null; columna: number | string | null; cantidad: number; total: string }[];
}

export interface FilaCostoHectarea {
  campo_id: number;
  campo: string;
  lote_id: number | null;
  lote: string | null;
  hectareas: string | null;
  total: string;
  por_hectarea: string | null;
}

export interface FilaIva {
  periodo: string | null;
  cantidad: number;
  neto_gravado: string;
  no_gravado: string;
  iva: string;
  percepciones: string;
  total: string;
}

export interface Insumo {
  id: number;
  nombre: string;
  unidad: string | null;
  categoria_id: number | null;
}

export interface ItemSinInsumo {
  descripcion: string;
  ejemplo_item_id: number;
  cantidad_items: number;
  unidad: string | null;
}

export interface ResumenInsumo {
  insumo_id: number;
  insumo: string;
  unidad: string | null;
  cantidad: string | null;
  total_pesos: string;
  precio_promedio: string | null;
  ultimo_precio: string | null;
  ultima_compra: string | null;
}

export interface PrecioInsumo {
  factura_id: number;
  fecha: string | null;
  proveedor: string | null;
  descripcion: string;
  cantidad: string | null;
  unidad: string | null;
  precio_unitario: string | null;
  moneda: string;
  precio_pesos: string | null;
}

export interface Cotizacion {
  fecha: string;
  valor: string;
  moneda: string;
}
