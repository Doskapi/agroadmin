import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, apiBlob } from "../api";
import { useAuth } from "../auth";
import { ACCIONES, DetalleAuditoria, fechaHora } from "../components/Auditoria";
import { PagosFactura } from "../components/Pagos";
import { BadgeFactura, Cargando, ErrorMsg, Field, Modal, nullSiVacio, numOrNull } from "../components/ui";
import { comprobante, fecha, pesos, TIPOS_COMPROBANTE } from "../format";
import { porId, useCampanias, useCampos, useCategorias, useInsumos, useProveedores } from "../hooks";
import type { EntradaAuditoria, Factura, FacturaCampos, FacturaItem, Imputacion } from "../types";

// El formulario trabaja todo como texto y convierte al guardar.
type Form = Record<keyof FacturaCampos, string>;
type ItemForm = Record<keyof Omit<FacturaItem, "id" | "insumo_id">, string> & { insumo_id?: number | null };
type RepartoForm = { campo_id: string; lote_id: string; porcentaje: string };

const CAMPOS_NUMERICOS_ENTEROS = ["proveedor_id", "tipo_comprobante", "punto_venta", "numero",
  "campania_id", "campo_id", "lote_id", "categoria_id"] as const;

function aForm(f: Factura): Form {
  const out = {} as Form;
  const keys: (keyof FacturaCampos)[] = ["proveedor_id", "cuit_emisor", "tipo_comprobante", "punto_venta", "numero",
    "fecha_emision", "fecha_vencimiento", "moneda", "cotizacion", "neto_gravado", "no_gravado", "iva",
    "percepciones", "total", "cae", "cae_vencimiento", "campania_id", "campo_id", "lote_id", "categoria_id",
    "observaciones"];
  for (const k of keys) out[k] = f[k] == null ? "" : String(f[k]);
  return out;
}

const itemAForm = (i: FacturaItem): ItemForm => ({
  descripcion: i.descripcion, cantidad: i.cantidad ?? "", unidad: i.unidad ?? "",
  precio_unitario: i.precio_unitario ?? "", alicuota_iva: i.alicuota_iva ?? "", subtotal: i.subtotal ?? "",
  insumo_id: i.insumo_id ?? null,
});

const repartoAForm = (i: Imputacion): RepartoForm => ({
  campo_id: String(i.campo_id), lote_id: i.lote_id == null ? "" : String(i.lote_id), porcentaje: String(Number(i.porcentaje)),
});

function aPayload(form: Form, items: ItemForm[], reparto: RepartoForm[]) {
  const out: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(form)) out[k] = nullSiVacio(v);
  for (const k of CAMPOS_NUMERICOS_ENTEROS) out[k] = numOrNull(form[k]);
  out.moneda = form.moneda || "PES";
  out.cotizacion = form.cotizacion || "1";
  out.items = items
    .filter((i) => i.descripcion.trim())
    .map(({ insumo_id, ...i }) => ({
      ...Object.fromEntries(Object.entries(i).map(([k, v]) => [k, nullSiVacio(v)])),
      insumo_id: insumo_id ?? null,
    }));
  out.imputaciones = reparto.map((r) => ({
    campo_id: Number(r.campo_id), lote_id: numOrNull(r.lote_id), porcentaje: r.porcentaje,
  }));
  if (reparto.length) {
    out.campo_id = null;
    out.lote_id = null;
  }
  return out;
}

export default function FacturaDetalle() {
  const { id } = useParams();
  const { puede } = useAuth();
  const qc = useQueryClient();

  const factura = useQuery({
    queryKey: ["factura", id],
    queryFn: () => api<Factura>(`/facturas/${id}`),
    refetchInterval: (q) => (q.state.data?.estado === "procesando" ? 2000 : false),
  });
  const f = factura.data;

  const [form, setForm] = useState<Form | null>(null);
  const [items, setItems] = useState<ItemForm[]>([]);
  const [reparto, setReparto] = useState<RepartoForm[]>([]);
  const [sucio, setSucio] = useState(false);

  // Cargar el formulario cuando llegan datos nuevos del servidor (salvo que haya cambios sin guardar)
  useEffect(() => {
    if (f && !sucio) {
      setForm(aForm(f));
      setItems(f.items.map(itemAForm));
      setReparto(f.imputaciones.map(repartoAForm));
    }
  }, [f, sucio]);

  const refrescar = (data: Factura) => {
    qc.setQueryData(["factura", id], data);
    qc.invalidateQueries({ queryKey: ["facturas"] });
    qc.invalidateQueries({ queryKey: ["resumen"] });
    qc.invalidateQueries({ queryKey: ["proveedores"] });
    setSucio(false);
  };

  const guardar = useMutation({
    mutationFn: () => api<Factura>(`/facturas/${id}`, { method: "PATCH", json: aPayload(form!, items, reparto) }),
    onSuccess: refrescar,
  });
  const accion = useMutation({
    mutationFn: async ({ a, motivo }: { a: "confirmar" | "anular" | "reprocesar"; motivo?: string }) => {
      if (a === "confirmar" && sucio) await api(`/facturas/${id}`, { method: "PATCH", json: aPayload(form!, items, reparto) });
      return api<Factura>(`/facturas/${id}/${a}`, { method: "POST", ...(a === "anular" ? { json: { motivo } } : {}) });
    },
    onSuccess: (data) => {
      refrescar(data);
      setAnulando(false);
      qc.invalidateQueries({ queryKey: ["historial", id] });
    },
  });
  const [anulando, setAnulando] = useState(false);

  if (factura.isPending) return <Cargando />;
  if (factura.error || !f) return <ErrorMsg error={factura.error} />;

  const editable = puede("facturas:escribir") && !["confirmada", "anulada", "procesando"].includes(f.estado);
  const set = (k: keyof Form) => (e: { target: { value: string } }) => {
    setForm((prev) => ({ ...prev!, [k]: e.target.value, ...(k === "campo_id" ? { lote_id: "" } : {}) }));
    setSucio(true);
  };
  const advertencias = f.datos_extraidos?.advertencias ?? [];
  const fuentes = f.datos_extraidos?.fuentes ?? [];

  return (
    <div className="stack">
      <div className="page-head">
        <div>
          <div className="muted" style={{ marginBottom: 4 }}><Link to="/facturas">← Facturas</Link></div>
          <div className="row">
            <h1>{f.proveedor?.razon_social ?? `Factura #${f.id}`}</h1>
            <BadgeFactura estado={f.estado} />
          </div>
          <div className="muted">
            {comprobante(f)} · {fecha(f.fecha_emision)}
            {fuentes.length > 0 && ` · datos leídos de: ${fuentes.map((x) => (x === "qr_arca" ? "QR de ARCA" : "IA")).join(" + ")}`}
          </div>
        </div>
        <div className="row">
          {f.archivo_id && puede("facturas:escribir") && f.estado !== "confirmada" && f.estado !== "procesando" && (
            <button onClick={() => accion.mutate({ a: "reprocesar" })} disabled={accion.isPending}>Volver a leer</button>
          )}
          {editable && (
            <button onClick={() => guardar.mutate()} disabled={!sucio || guardar.isPending}>
              {guardar.isPending ? "Guardando…" : "Guardar"}
            </button>
          )}
          {puede("facturas:confirmar") && f.estado === "pendiente_revision" && (
            <button className="primary" onClick={() => accion.mutate({ a: "confirmar" })} disabled={accion.isPending}>
              ✓ Confirmar
            </button>
          )}
          {puede("facturas:confirmar") && f.estado !== "anulada" && f.estado !== "procesando" && (
            <button className="danger" disabled={accion.isPending} onClick={() => setAnulando(true)}>
              Anular
            </button>
          )}
        </div>
      </div>

      <ErrorMsg error={guardar.error ?? accion.error} />
      {f.estado === "procesando" && (
        <div className="alert warning"><span className="spinner" /> Leyendo el comprobante… se actualiza solo.</div>
      )}
      {f.error_extraccion && <div className="alert critical">{f.error_extraccion}</div>}
      <EstadoArca f={f} onPedido={refrescar} />
      {advertencias.length > 0 && (
        <div className="alert warning">
          Revisar:
          <ul>{advertencias.map((a) => <li key={a}>{a}</li>)}</ul>
        </div>
      )}

      {anulando && <ModalAnular pending={accion.isPending} error={accion.error} onClose={() => setAnulando(false)}
        onAnular={(motivo) => accion.mutate({ a: "anular", motivo })} />}

      <div className={f.archivo_id ? "review" : ""}>
        {f.archivo_id && <VistaArchivo facturaId={f.id} />}
        {form && <FormularioFactura form={form} set={set} editable={editable} items={items}
          setItems={(v) => { setItems(v); setSucio(true); }}
          reparto={reparto} setReparto={(v) => { setReparto(v); setSucio(true); }} />}
      </div>
      <PagosFactura factura={f} />
      <Historial facturaId={f.id} />
    </div>
  );
}

function VistaArchivo({ facturaId }: { facturaId: number }) {
  const archivo = useQuery({
    queryKey: ["factura-archivo", facturaId],
    queryFn: async () => {
      const blob = await apiBlob(`/facturas/${facturaId}/archivo`);
      return { url: URL.createObjectURL(blob), tipo: blob.type };
    },
    staleTime: Infinity,
  });
  useEffect(() => () => { if (archivo.data) URL.revokeObjectURL(archivo.data.url); }, [archivo.data]);

  return (
    <div className="card preview" style={{ padding: 8 }}>
      {archivo.data ? (
        archivo.data.tipo === "application/pdf"
          ? <iframe src={archivo.data.url} title="Comprobante" />
          : <img src={archivo.data.url} alt="Comprobante" />
      ) : archivo.error ? <ErrorMsg error={archivo.error} /> : <Cargando />}
    </div>
  );
}

function FormularioFactura({ form, set, editable, items, setItems, reparto, setReparto }: {
  form: Form;
  set: (k: keyof Form) => (e: { target: { value: string } }) => void;
  editable: boolean;
  items: ItemForm[];
  setItems: (v: ItemForm[]) => void;
  reparto: RepartoForm[];
  setReparto: (v: RepartoForm[]) => void;
}) {
  const insumos = porId(useInsumos().data, (i) => i.nombre);
  const proveedores = useProveedores();
  const campos = useCampos();
  const campanias = useCampanias();
  const categorias = useCategorias();
  const lotes = campos.data?.find((c) => String(c.id) === form.campo_id)?.lotes ?? [];
  const dis = !editable;

  const setItem = (i: number, k: keyof ItemForm, v: string) =>
    setItems(items.map((it, j) => (j === i ? { ...it, [k]: v } : it)));
  const vacio: ItemForm = { descripcion: "", cantidad: "", unidad: "", precio_unitario: "", alicuota_iva: "", subtotal: "" };

  return (
    <fieldset disabled={dis} style={{ border: "none", padding: 0, margin: 0, minWidth: 0 }} className="stack">
      <div className="card">
        <h3>Comprobante</h3>
        <div className="form-grid">
          <Field label="Proveedor" wide>
            <select value={form.proveedor_id} onChange={set("proveedor_id")}>
              <option value="">— sin asignar —</option>
              {proveedores.data?.map((p) => <option key={p.id} value={p.id}>{p.razon_social} ({p.cuit})</option>)}
            </select>
          </Field>
          <Field label="CUIT emisor"><input value={form.cuit_emisor} onChange={set("cuit_emisor")} placeholder="30-12345678-9" /></Field>
          <Field label="Tipo">
            <select value={form.tipo_comprobante} onChange={set("tipo_comprobante")}>
              <option value="">—</option>
              {Object.entries(TIPOS_COMPROBANTE).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
          </Field>
          <Field label="Punto de venta"><input type="number" value={form.punto_venta} onChange={set("punto_venta")} /></Field>
          <Field label="Número"><input type="number" value={form.numero} onChange={set("numero")} /></Field>
          <Field label="Fecha de emisión"><input type="date" value={form.fecha_emision} onChange={set("fecha_emision")} /></Field>
          <Field label="Vencimiento"><input type="date" value={form.fecha_vencimiento} onChange={set("fecha_vencimiento")} /></Field>
          <Field label="CAE"><input value={form.cae} onChange={set("cae")} /></Field>
          <Field label="Vto. CAE"><input type="date" value={form.cae_vencimiento} onChange={set("cae_vencimiento")} /></Field>
        </div>
      </div>

      <div className="card">
        <h3>Importes</h3>
        <div className="form-grid">
          <Field label="Moneda">
            <select value={form.moneda} onChange={set("moneda")}>
              <option value="PES">Pesos</option>
              <option value="DOL">Dólares</option>
            </select>
          </Field>
          <Field label="Cotización"><input type="number" step="any" value={form.cotizacion} onChange={set("cotizacion")} /></Field>
          <Field label="Neto gravado"><input type="number" step="0.01" value={form.neto_gravado} onChange={set("neto_gravado")} /></Field>
          <Field label="No gravado"><input type="number" step="0.01" value={form.no_gravado} onChange={set("no_gravado")} /></Field>
          <Field label="IVA"><input type="number" step="0.01" value={form.iva} onChange={set("iva")} /></Field>
          <Field label="Percepciones / otros"><input type="number" step="0.01" value={form.percepciones} onChange={set("percepciones")} /></Field>
          <Field label="Total"><input type="number" step="0.01" value={form.total} onChange={set("total")} style={{ fontWeight: 600 }} /></Field>
        </div>
        {form.moneda !== "PES" && form.total && (
          <div className="muted" style={{ marginTop: 8 }}>
            Equivale a {pesos(Number(form.total) * Number(form.cotizacion || 1))}
          </div>
        )}
      </div>

      <div className="card">
        <h3>Imputación</h3>
        <div className="form-grid">
          <Field label="Categoría">
            <select value={form.categoria_id} onChange={set("categoria_id")}>
              <option value="">—</option>
              {categorias.data?.map((c) => <option key={c.id} value={c.id}>{c.nombre}</option>)}
            </select>
          </Field>
          <Field label="Campaña">
            <select value={form.campania_id} onChange={set("campania_id")}>
              <option value="">—</option>
              {campanias.data?.map((c) => <option key={c.id} value={c.id}>{c.nombre}</option>)}
            </select>
          </Field>
          {reparto.length === 0 && (
            <>
              <Field label="Campo">
                <select value={form.campo_id} onChange={set("campo_id")}>
                  <option value="">—</option>
                  {campos.data?.map((c) => <option key={c.id} value={c.id}>{c.nombre}</option>)}
                </select>
              </Field>
              <Field label="Lote">
                <select value={form.lote_id} onChange={set("lote_id")} disabled={dis || !lotes.length}>
                  <option value="">—</option>
                  {lotes.map((l) => <option key={l.id} value={l.id}>{l.nombre}</option>)}
                </select>
              </Field>
            </>
          )}
          <div className="wide">
            <EditorReparto reparto={reparto} setReparto={setReparto} editable={editable}
              campoInicial={form.campo_id} loteInicial={form.lote_id} />
          </div>
          <Field label="Observaciones" wide>
            <textarea rows={2} value={form.observaciones} onChange={set("observaciones")} />
          </Field>
        </div>
      </div>

      <div className="card flush">
        <div style={{ padding: "16px 16px 4px" }}><h3>Detalle</h3></div>
        <div className="table-wrap">
          <table className="items-table">
            <thead>
              <tr><th>Descripción</th><th>Insumo</th><th>Cant.</th><th>Unidad</th><th>P. unit.</th><th>IVA %</th><th>Subtotal</th>{editable && <th />}</tr>
            </thead>
            <tbody>
              {items.map((it, i) => (
                <tr key={i}>
                  <td style={{ minWidth: 180 }}><input value={it.descripcion} onChange={(e) => setItem(i, "descripcion", e.target.value)} /></td>
                  <td className="muted" style={{ fontSize: 12, whiteSpace: "nowrap" }}>
                    {it.insumo_id ? insumos.get(it.insumo_id) : "—"}
                  </td>
                  <td><input type="number" step="any" value={it.cantidad} onChange={(e) => setItem(i, "cantidad", e.target.value)} /></td>
                  <td><input value={it.unidad} onChange={(e) => setItem(i, "unidad", e.target.value)} style={{ width: 60 }} /></td>
                  <td><input type="number" step="any" value={it.precio_unitario} onChange={(e) => setItem(i, "precio_unitario", e.target.value)} /></td>
                  <td><input type="number" step="any" value={it.alicuota_iva} onChange={(e) => setItem(i, "alicuota_iva", e.target.value)} style={{ width: 60 }} /></td>
                  <td><input type="number" step="0.01" value={it.subtotal} onChange={(e) => setItem(i, "subtotal", e.target.value)} /></td>
                  {editable && (
                    <td><button type="button" className="small" aria-label="Quitar ítem"
                      onClick={() => setItems(items.filter((_, j) => j !== i))}>✕</button></td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
          {items.length === 0 && <div className="empty" style={{ padding: 16 }}>Sin ítems</div>}
        </div>
        {editable && (
          <div style={{ padding: 12 }}>
            <button type="button" className="small" onClick={() => setItems([...items, vacio])}>+ Agregar ítem</button>
          </div>
        )}
      </div>
    </fieldset>
  );
}

function EditorReparto({ reparto, setReparto, editable, campoInicial, loteInicial }: {
  reparto: RepartoForm[];
  setReparto: (v: RepartoForm[]) => void;
  editable: boolean;
  campoInicial: string;
  loteInicial: string;
}) {
  const campos = useCampos();
  const suma = reparto.reduce((s, r) => s + (Number(r.porcentaje) || 0), 0);
  const set = (i: number, k: keyof RepartoForm, v: string) =>
    setReparto(reparto.map((r, j) => (j === i ? { ...r, [k]: v, ...(k === "campo_id" ? { lote_id: "" } : {}) } : r)));

  if (!reparto.length) {
    return editable ? (
      <button type="button" className="small" onClick={() => setReparto([
        { campo_id: campoInicial, lote_id: loteInicial, porcentaje: "50" },
        { campo_id: "", lote_id: "", porcentaje: "50" },
      ])}>
        Repartir entre varios campos o lotes
      </button>
    ) : null;
  }

  return (
    <div className="stack" style={{ gap: 8 }}>
      <div className="row" style={{ justifyContent: "space-between" }}>
        <strong style={{ fontSize: 13 }}>Reparto del gasto</strong>
        <span className={Math.abs(suma - 100) < 0.01 ? "badge good" : "badge critical"}>Suma {suma}%</span>
      </div>
      {reparto.map((r, i) => {
        const lotes = campos.data?.find((c) => String(c.id) === r.campo_id)?.lotes ?? [];
        return (
          <div key={i} className="row">
            <select aria-label="Campo" value={r.campo_id} onChange={(e) => set(i, "campo_id", e.target.value)} required>
              <option value="">Campo…</option>
              {campos.data?.map((c) => <option key={c.id} value={c.id}>{c.nombre}</option>)}
            </select>
            <select aria-label="Lote" value={r.lote_id} onChange={(e) => set(i, "lote_id", e.target.value)} disabled={!lotes.length}>
              <option value="">Todo el campo</option>
              {lotes.map((l) => <option key={l.id} value={l.id}>{l.nombre}</option>)}
            </select>
            <input aria-label="Porcentaje" type="number" min="0" max="100" step="any" style={{ width: 80 }}
              value={r.porcentaje} onChange={(e) => set(i, "porcentaje", e.target.value)} /> %
            {editable && (
              <button type="button" className="small" aria-label="Quitar"
                onClick={() => setReparto(reparto.filter((_, j) => j !== i))}>✕</button>
            )}
          </div>
        );
      })}
      {editable && (
        <div className="row">
          <button type="button" className="small"
            onClick={() => setReparto([...reparto, { campo_id: "", lote_id: "", porcentaje: String(Math.max(0, 100 - suma)) }])}>
            + Agregar
          </button>
          <button type="button" className="small" onClick={() => setReparto([])}>Quitar reparto</button>
        </div>
      )}
    </div>
  );
}

function ModalAnular({ onClose, onAnular, pending, error }: {
  onClose: () => void; onAnular: (motivo: string) => void; pending: boolean; error: unknown;
}) {
  const [motivo, setMotivo] = useState("");
  return (
    <Modal titulo="Anular factura" onClose={onClose}>
      <form onSubmit={(e) => { e.preventDefault(); onAnular(motivo); }} className="stack">
        <div className="muted">Deja de contar en los reportes. El motivo queda registrado en el historial.</div>
        <ErrorMsg error={error} />
        <Field label="Motivo">
          <textarea rows={2} required minLength={3} value={motivo} onChange={(e) => setMotivo(e.target.value)} autoFocus
            placeholder="Ej.: duplicada, cargada por error, el proveedor la anuló" />
        </Field>
        <div className="modal-actions">
          <button type="button" onClick={onClose}>Cancelar</button>
          <button className="danger" disabled={pending}>Anular</button>
        </div>
      </form>
    </Modal>
  );
}

function Historial({ facturaId }: { facturaId: number }) {
  const [abierto, setAbierto] = useState(false);
  const hist = useQuery({
    queryKey: ["historial", String(facturaId)],
    queryFn: () => api<EntradaAuditoria[]>(`/facturas/${facturaId}/historial`),
    enabled: abierto,
  });
  return (
    <div className="card">
      <button type="button" className="link" style={{ fontWeight: 600 }} onClick={() => setAbierto(!abierto)} aria-expanded={abierto}>
        {abierto ? "▾" : "▸"} Historial de cambios
      </button>
      {abierto && (hist.isPending ? <Cargando /> : (
        <ul className="historial">
          {hist.data?.map((e) => (
            <li key={e.id}>
              <span className="muted">{fechaHora(e.fecha)}</span> · <strong>{e.usuario ?? "Sistema"}</strong>{" "}
              {(ACCIONES[e.accion] ?? e.accion).toLowerCase()}
              <div><DetalleAuditoria e={e} /></div>
            </li>
          ))}
          {!hist.data?.length && <li className="muted">Sin registros (la factura es anterior a la auditoría).</li>}
        </ul>
      ))}
    </div>
  );
}

/** Resultado de la constatación del comprobante en ARCA (y botón para pedirla). */
function EstadoArca({ f, onPedido }: { f: Factura; onPedido: (f: Factura) => void }) {
  const { puede } = useAuth();
  const estado = useQuery({
    queryKey: ["arca-estado"],
    queryFn: () => api<{ verificacion_configurada: boolean }>("/arca/estado"),
    staleTime: Infinity,
  });
  const pedir = useMutation({
    mutationFn: () => api<Factura>(`/facturas/${f.id}/verificar-arca`, { method: "POST" }),
    onSuccess: onPedido,
  });
  if (!estado.data?.verificacion_configurada || !f.cae) return null;
  const boton = puede("facturas:escribir") && (
    <button className="small" disabled={pedir.isPending || pedir.isSuccess} onClick={() => pedir.mutate()}>
      {pedir.isSuccess ? "Pedido enviado" : f.arca_verificado ? "Volver a verificar" : "Verificar en ARCA"}
    </button>
  );
  if (f.arca_resultado === "A") {
    return <div className="alert good row" style={{ justifyContent: "space-between" }}>
      <span>✓ Comprobante válido según ARCA ({fechaHora(f.arca_verificado!)})</span>{boton}</div>;
  }
  if (f.arca_resultado === "R") {
    return <div className="alert critical row" style={{ justifyContent: "space-between" }}>
      <span>✗ ARCA rechazó el comprobante: {f.arca_observaciones}</span>{boton}</div>;
  }
  return <div className="alert info row" style={{ justifyContent: "space-between" }}>
    <span>{f.arca_observaciones ? `No se pudo verificar en ARCA: ${f.arca_observaciones}` : "Sin verificar en ARCA."}</span>
    {boton}<ErrorMsg error={pedir.error} /></div>;
}
