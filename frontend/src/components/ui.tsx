import type { ReactNode } from "react";
import { capitalizar } from "../format";
import type { EstadoCartaPorte, EstadoFactura } from "../types";

const ESTADO_FACTURA: Record<EstadoFactura, { clase: string; icono: string; texto: string }> = {
  procesando: { clase: "info", icono: "⟳", texto: "Procesando" },
  pendiente_revision: { clase: "warning", icono: "●", texto: "A revisar" },
  confirmada: { clase: "good", icono: "✓", texto: "Confirmada" },
  error: { clase: "critical", icono: "!", texto: "Error" },
  anulada: { clase: "muted", icono: "–", texto: "Anulada" },
};

export function BadgeFactura({ estado }: { estado: EstadoFactura }) {
  const e = ESTADO_FACTURA[estado];
  return (
    <span className={`badge ${e.clase}`}>
      <span aria-hidden>{e.icono}</span>
      {e.texto}
    </span>
  );
}

const ESTADO_CP: Record<EstadoCartaPorte, string> = {
  borrador: "muted",
  emitida: "info",
  descargada: "good",
  anulada: "critical",
};

export function BadgeCartaPorte({ estado }: { estado: EstadoCartaPorte }) {
  return <span className={`badge ${ESTADO_CP[estado]}`}>{capitalizar(estado)}</span>;
}

export function Field({ label, children, wide }: { label: string; children: ReactNode; wide?: boolean }) {
  return (
    <label className={`field${wide ? " wide" : ""}`}>
      {label}
      {children}
    </label>
  );
}

export function Modal({ titulo, children, onClose }: { titulo: string; children: ReactNode; onClose: () => void }) {
  return (
    <div className="modal-bg" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal" role="dialog" aria-label={titulo}>
        <h2>{titulo}</h2>
        {children}
      </div>
    </div>
  );
}

export function ErrorMsg({ error }: { error: unknown }) {
  if (!error) return null;
  return <div className="alert critical">{error instanceof Error ? error.message : String(error)}</div>;
}

export function Cargando() {
  return (
    <div className="empty">
      <span className="spinner" /> Cargando…
    </div>
  );
}

/** Convierte "" en null para mandar a la API. */
export const nullSiVacio = (v: string) => (v.trim() === "" ? null : v.trim());
export const numOrNull = (v: string) => (v === "" ? null : Number(v));
