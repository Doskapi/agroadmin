import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../api";
import { useAuth } from "../auth";
import { fecha, monto } from "../format";
import type { Factura, MedioPago } from "../types";
import { ErrorMsg, Field, Modal, nullSiVacio } from "./ui";

export const MEDIOS: Record<MedioPago, string> = {
  transferencia: "Transferencia", cheque: "Cheque", echeq: "E-cheq", efectivo: "Efectivo", tarjeta: "Tarjeta",
  compensacion: "Compensación", otro: "Otro",
};

export function ModalPago({ facturaId, saldo, moneda, onClose, onListo }: {
  facturaId: number; saldo: string | null; moneda: string; onClose: () => void; onListo: (f: Factura) => void;
}) {
  const qc = useQueryClient();
  const [f, setF] = useState({
    fecha: new Date().toISOString().slice(0, 10), monto: saldo ?? "", medio: "transferencia" as MedioPago,
    referencia: "", observaciones: "",
  });
  const guardar = useMutation({
    mutationFn: () => api<Factura>(`/facturas/${facturaId}/pagos`, {
      method: "POST", json: { ...f, referencia: nullSiVacio(f.referencia), observaciones: nullSiVacio(f.observaciones) },
    }),
    onSuccess: (factura) => {
      qc.setQueryData(["factura", String(facturaId)], factura);
      qc.invalidateQueries({ queryKey: ["facturas"] });
      onListo(factura);
    },
  });
  return (
    <Modal titulo="Registrar pago" onClose={onClose}>
      <form onSubmit={(e) => { e.preventDefault(); guardar.mutate(); }}>
        <ErrorMsg error={guardar.error} />
        {saldo && <div className="muted">Saldo: {monto(saldo, moneda)}</div>}
        <div className="form-grid" style={{ marginTop: 8 }}>
          <Field label="Fecha"><input type="date" required value={f.fecha} onChange={(e) => setF({ ...f, fecha: e.target.value })} /></Field>
          <Field label={`Monto (${moneda === "DOL" ? "US$" : "$"})`}>
            <input type="number" step="0.01" min="0.01" required value={f.monto} onChange={(e) => setF({ ...f, monto: e.target.value })} />
          </Field>
          <Field label="Medio">
            <select value={f.medio} onChange={(e) => setF({ ...f, medio: e.target.value as MedioPago })}>
              {Object.entries(MEDIOS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
          </Field>
          <Field label="Referencia"><input value={f.referencia} placeholder="N° de cheque / transferencia" onChange={(e) => setF({ ...f, referencia: e.target.value })} /></Field>
          <Field label="Observaciones" wide><input value={f.observaciones} onChange={(e) => setF({ ...f, observaciones: e.target.value })} /></Field>
        </div>
        <div className="modal-actions">
          <button type="button" onClick={onClose}>Cancelar</button>
          <button className="primary" disabled={guardar.isPending}>Registrar</button>
        </div>
      </form>
    </Modal>
  );
}

/** Tarjeta de pagos en el detalle de una factura confirmada. */
export function PagosFactura({ factura }: { factura: Factura }) {
  const { puede } = useAuth();
  const qc = useQueryClient();
  const [pagando, setPagando] = useState(false);
  const borrar = useMutation({
    mutationFn: (id: number) => api<Factura>(`/pagos/${id}`, { method: "DELETE" }),
    onSuccess: (f) => qc.setQueryData(["factura", String(factura.id)], f),
  });
  if (factura.estado !== "confirmada" || factura.saldo == null) return null;
  const pagada = Number(factura.saldo) <= 0.01;

  return (
    <div className="card stack" style={{ gap: 10 }}>
      <div className="row" style={{ justifyContent: "space-between" }}>
        <h3 style={{ margin: 0 }}>Pagos</h3>
        <div className="row">
          {pagada ? <span className="badge good">✓ Pagada</span>
            : <span className="badge warning">Saldo {monto(factura.saldo, factura.moneda)}</span>}
          {!pagada && puede("pagos:escribir") && <button className="small" onClick={() => setPagando(true)}>Registrar pago</button>}
        </div>
      </div>
      <ErrorMsg error={borrar.error} />
      {factura.pagos.length > 0 ? (
        <table>
          <tbody>
            {factura.pagos.map((p) => (
              <tr key={p.id}>
                <td>{fecha(p.fecha)}</td>
                <td>{MEDIOS[p.medio]}{p.referencia ? ` · ${p.referencia}` : ""}</td>
                <td className="num">{monto(p.monto, factura.moneda)}</td>
                {puede("pagos:escribir") && (
                  <td style={{ width: 40 }}>
                    <button className="small" aria-label="Borrar pago"
                      onClick={() => confirm("¿Borrar este pago?") && borrar.mutate(p.id)}>✕</button>
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      ) : <div className="muted">Sin pagos registrados.</div>}
      {pagando && <ModalPago facturaId={factura.id} saldo={factura.saldo} moneda={factura.moneda}
        onClose={() => setPagando(false)} onListo={() => setPagando(false)} />}
    </div>
  );
}
