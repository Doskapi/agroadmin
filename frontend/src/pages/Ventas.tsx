import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, qs } from "../api";
import { useAuth } from "../auth";
import { ErrorMsg, Field, Modal, nullSiVacio, numOrNull } from "../components/ui";
import { capitalizar, fecha, monto, num } from "../format";
import { porId, useCampanias, useCampos } from "../hooks";
import type { Venta } from "../types";

const GRANOS = ["soja", "maíz", "trigo", "girasol", "sorgo", "cebada"];

export default function Ventas() {
  const { puede } = useAuth();
  const campanias = useCampanias();
  const [campania, setCampania] = useState("");
  const [editando, setEditando] = useState<Venta | "nueva" | null>(null);
  const lista = useQuery({
    queryKey: ["ventas", campania],
    queryFn: () => api<Venta[]>(`/ventas${qs({ campania_id: campania })}`),
  });
  const nombresCampania = porId(campanias.data, (c) => c.nombre);
  const camposData = useCampos().data;
  const nombresCampo = porId(camposData, (c) => c.nombre);
  const toneladas = (lista.data ?? []).reduce((s, v) => s + Number(v.kilos), 0) / 1000;

  return (
    <div className="stack">
      <div className="page-head">
        <h1>Ventas de granos</h1>
        {puede("ventas:escribir") && <button className="primary" onClick={() => setEditando("nueva")}>+ Venta</button>}
      </div>
      <div className="row">
        <Field label="Campaña">
          <select value={campania} onChange={(e) => setCampania(e.target.value)}>
            <option value="">Todas</option>
            {campanias.data?.map((c) => <option key={c.id} value={c.id}>{c.nombre}</option>)}
          </select>
        </Field>
      </div>
      <ErrorMsg error={lista.error} />
      <div className="card flush table-wrap">
        <table>
          <thead>
            <tr><th>Fecha</th><th>Grano</th><th>Campaña</th><th>Campo</th><th>Comprador</th><th>Liquidación</th>
              <th className="num">Kilos</th><th className="num">Total</th></tr>
          </thead>
          <tbody>
            {lista.data?.map((v) => (
              <tr key={v.id} className={puede("ventas:escribir") ? "clickable" : ""} onClick={() => puede("ventas:escribir") && setEditando(v)}>
                <td>{fecha(v.fecha)}</td>
                <td>{capitalizar(v.grano)}</td>
                <td>{v.campania_id ? nombresCampania.get(v.campania_id) : "—"}</td>
                <td>{v.campo_id ? nombresCampo.get(v.campo_id) : "—"}</td>
                <td>{v.comprador ?? "—"}</td>
                <td>{v.comprobante ?? "—"}</td>
                <td className="num">{num(v.kilos)}</td>
                <td className="num">{monto(v.total, v.moneda)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {lista.isSuccess && !lista.data.length && <div className="empty">Sin ventas cargadas.</div>}
      </div>
      {!!lista.data?.length && <div className="muted">{lista.data.length} ventas · {num(toneladas)} toneladas</div>}
      <div className="muted" style={{ fontSize: 12 }}>El margen (ventas menos gastos) está en Reportes → Margen.</div>
      {editando && <FormVenta v={editando === "nueva" ? null : editando} onClose={() => setEditando(null)} />}
    </div>
  );
}

function FormVenta({ v, onClose }: { v: Venta | null; onClose: () => void }) {
  const qc = useQueryClient();
  const campanias = useCampanias();
  const campos = useCampos();
  const [f, setF] = useState({
    fecha: v?.fecha ?? new Date().toISOString().slice(0, 10), campania_id: String(v?.campania_id ?? ""),
    campo_id: String(v?.campo_id ?? ""), lote_id: String(v?.lote_id ?? ""), grano: v?.grano ?? "soja",
    kilos: v?.kilos ?? "", precio_tonelada: v?.precio_tonelada ?? "", total: v?.total ?? "", moneda: v?.moneda ?? "PES",
    cotizacion: v?.cotizacion ?? "1", comprador: v?.comprador ?? "", comprobante: v?.comprobante ?? "",
    observaciones: v?.observaciones ?? "",
  });
  const lotes = campos.data?.find((c) => String(c.id) === f.campo_id)?.lotes ?? [];
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) =>
    setF((p) => ({ ...p, [k]: e.target.value, ...(k === "campo_id" ? { lote_id: "" } : {}) }));
  const sugerido = f.kilos && f.precio_tonelada ? (Number(f.kilos) / 1000) * Number(f.precio_tonelada) : null;
  const refrescar = () => { qc.invalidateQueries({ queryKey: ["ventas"] }); onClose(); };

  const guardar = useMutation({
    mutationFn: () => api(v ? `/ventas/${v.id}` : "/ventas", {
      method: v ? "PUT" : "POST",
      json: {
        ...f, campania_id: numOrNull(f.campania_id), campo_id: numOrNull(f.campo_id), lote_id: numOrNull(f.lote_id),
        precio_tonelada: nullSiVacio(f.precio_tonelada), comprador: nullSiVacio(f.comprador),
        comprobante: nullSiVacio(f.comprobante), observaciones: nullSiVacio(f.observaciones),
        cotizacion: f.moneda === "PES" ? "1" : f.cotizacion,
      },
    }),
    onSuccess: refrescar,
  });
  const borrar = useMutation({ mutationFn: () => api(`/ventas/${v!.id}`, { method: "DELETE" }), onSuccess: refrescar });

  return (
    <Modal titulo={v ? "Editar venta" : "Nueva venta de granos"} onClose={onClose}>
      <form onSubmit={(e) => { e.preventDefault(); guardar.mutate(); }}>
        <ErrorMsg error={guardar.error ?? borrar.error} />
        <div className="form-grid" style={{ marginTop: 8 }}>
          <Field label="Fecha"><input type="date" required value={f.fecha} onChange={set("fecha")} /></Field>
          <Field label="Grano">
            <select value={f.grano} onChange={set("grano")}>
              {[...new Set([...GRANOS, f.grano])].map((g) => <option key={g} value={g}>{capitalizar(g)}</option>)}
            </select>
          </Field>
          <Field label="Campaña">
            <select value={f.campania_id} onChange={set("campania_id")}>
              <option value="">—</option>
              {campanias.data?.map((c) => <option key={c.id} value={c.id}>{c.nombre}</option>)}
            </select>
          </Field>
          <Field label="Campo">
            <select value={f.campo_id} onChange={set("campo_id")}>
              <option value="">—</option>
              {campos.data?.map((c) => <option key={c.id} value={c.id}>{c.nombre}</option>)}
            </select>
          </Field>
          <Field label="Lote">
            <select value={f.lote_id} onChange={set("lote_id")} disabled={!lotes.length}>
              <option value="">—</option>
              {lotes.map((l) => <option key={l.id} value={l.id}>{l.nombre}</option>)}
            </select>
          </Field>
          <Field label="Kilos"><input type="number" step="0.01" min="0" required value={f.kilos} onChange={set("kilos")} /></Field>
          <Field label="Precio por tonelada"><input type="number" step="any" value={f.precio_tonelada} onChange={set("precio_tonelada")} /></Field>
          <Field label="Moneda">
            <select value={f.moneda} onChange={set("moneda")}>
              <option value="PES">Pesos</option>
              <option value="DOL">Dólares</option>
            </select>
          </Field>
          {f.moneda === "DOL" && <Field label="Cotización"><input type="number" step="any" required value={f.cotizacion} onChange={set("cotizacion")} /></Field>}
          <Field label="Total neto cobrado">
            <input type="number" step="0.01" min="0" required value={f.total} onChange={set("total")}
              placeholder={sugerido ? `${sugerido.toFixed(2)} (kilos × precio)` : ""} />
          </Field>
          <Field label="Comprador"><input value={f.comprador} onChange={set("comprador")} /></Field>
          <Field label="N° de liquidación"><input value={f.comprobante} onChange={set("comprobante")} /></Field>
          <Field label="Observaciones" wide><textarea rows={2} value={f.observaciones} onChange={set("observaciones")} /></Field>
        </div>
        <div className="modal-actions">
          {v && <button type="button" className="danger" onClick={() => confirm("¿Borrar esta venta?") && borrar.mutate()}>Borrar</button>}
          <button type="button" onClick={onClose}>Cancelar</button>
          <button className="primary" disabled={guardar.isPending}>Guardar</button>
        </div>
      </form>
    </Modal>
  );
}
