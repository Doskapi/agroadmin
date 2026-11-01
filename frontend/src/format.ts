const ars = new Intl.NumberFormat("es-AR", { style: "currency", currency: "ARS", maximumFractionDigits: 2 });
const arsCompacto = new Intl.NumberFormat("es-AR", { notation: "compact", maximumFractionDigits: 1 });
const numero = new Intl.NumberFormat("es-AR", { maximumFractionDigits: 2 });

export const pesos = (v: string | number | null | undefined) => (v == null || v === "" ? "—" : ars.format(Number(v)));
export const pesosCompacto = (v: number) => `$ ${arsCompacto.format(v)}`;
export const num = (v: string | number | null | undefined) => (v == null || v === "" ? "—" : numero.format(Number(v)));

export function monto(v: string | null, moneda: string) {
  if (v == null) return "—";
  if (moneda === "PES") return pesos(v);
  return `${moneda === "DOL" ? "US$" : moneda} ${numero.format(Number(v))}`;
}

export function fecha(v: string | null | undefined) {
  if (!v) return "—";
  const [a, m, d] = v.slice(0, 10).split("-");
  return `${d}/${m}/${a}`;
}

const MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"];
export function mes(clave: string | null) {
  if (!clave) return "Sin fecha";
  const [a, m] = clave.split("-");
  return `${MESES[Number(m) - 1]} ${a.slice(2)}`;
}

export const cuit = (v: string | null | undefined) =>
  v && v.length === 11 ? `${v.slice(0, 2)}-${v.slice(2, 10)}-${v.slice(10)}` : (v ?? "—");

export const TIPOS_COMPROBANTE: Record<number, string> = {
  1: "Factura A", 2: "Nota de débito A", 3: "Nota de crédito A",
  6: "Factura B", 7: "Nota de débito B", 8: "Nota de crédito B",
  11: "Factura C", 12: "Nota de débito C", 13: "Nota de crédito C",
  51: "Factura M", 53: "Nota de crédito M",
};

export function comprobante(f: { tipo_comprobante: number | null; punto_venta: number | null; numero: number | null }) {
  const tipo = f.tipo_comprobante ? (TIPOS_COMPROBANTE[f.tipo_comprobante] ?? `Tipo ${f.tipo_comprobante}`) : "Comprobante";
  if (f.punto_venta == null || f.numero == null) return tipo;
  return `${tipo} ${String(f.punto_venta).padStart(5, "0")}-${String(f.numero).padStart(8, "0")}`;
}

export const capitalizar = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);
