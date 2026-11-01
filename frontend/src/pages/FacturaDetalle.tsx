import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, apiBlob } from "../api";
import { useAuth } from "../auth";
import { BadgeFactura, Cargando, ErrorMsg, Field, nullSiVacio, numOrNull } from "../components/ui";
import { comprobante, fecha, pesos, TIPOS_COMPROBANTE } from "../format";
import { useCampanias, useCampos, useCategorias, useProveedores } from "../hooks";
import type { Factura, FacturaCampos, FacturaItem } from "../types";

// El formulario trabaja todo como texto y convierte al guardar.
type Form = Record<keyof FacturaCampos, string>;
type ItemForm = Record<keyof Omit<FacturaItem, "id">, string>;

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
});

function aPayload(form: Form, items: ItemForm[]) {
  const out: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(form)) out[k] = nullSiVacio(v);
  for (const k of CAMPOS_NUMERICOS_ENTEROS) out[k] = numOrNull(form[k]);
  out.moneda = form.moneda || "PES";
  out.cotizacion = form.cotizacion || "1";
  out.items = items
    .filter((i) => i.descripcion.trim())
    .map((i) => Object.fromEntries(Object.entries(i).map(([k, v]) => [k, nullSiVacio(v)])));
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
  const [sucio, setSucio] = useState(false);

  // Cargar el formulario cuando llegan datos nuevos del servidor (salvo que haya cambios sin guardar)
  useEffect(() => {
    if (f && !sucio) {
      setForm(aForm(f));
      setItems(f.items.map(itemAForm));
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
    mutationFn: () => api<Factura>(`/facturas/${id}`, { method: "PATCH", json: aPayload(form!, items) }),
    onSuccess: refrescar,
  });
  const accion = useMutation({
    mutationFn: async (a: "confirmar" | "anular" | "reprocesar") => {
      if (a === "confirmar" && sucio) await api(`/facturas/${id}`, { method: "PATCH", json: aPayload(form!, items) });
      return api<Factura>(`/facturas/${id}/${a}`, { method: "POST" });
    },
    onSuccess: refrescar,
  });

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
            <button onClick={() => accion.mutate("reprocesar")} disabled={accion.isPending}>Volver a leer</button>
          )}
          {editable && (
            <button onClick={() => guardar.mutate()} disabled={!sucio || guardar.isPending}>
              {guardar.isPending ? "Guardando…" : "Guardar"}
            </button>
          )}
          {puede("facturas:confirmar") && f.estado === "pendiente_revision" && (
            <button className="primary" onClick={() => accion.mutate("confirmar")} disabled={accion.isPending}>
              ✓ Confirmar
            </button>
          )}
          {puede("facturas:confirmar") && f.estado !== "anulada" && f.estado !== "procesando" && (
            <button className="danger" disabled={accion.isPending}
              onClick={() => confirm("¿Anular esta factura? Deja de contar en los reportes.") && accion.mutate("anular")}>
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
      {advertencias.length > 0 && (
        <div className="alert warning">
          Revisar:
          <ul>{advertencias.map((a) => <li key={a}>{a}</li>)}</ul>
        </div>
      )}

      <div className={f.archivo_id ? "review" : ""}>
        {f.archivo_id && <VistaArchivo facturaId={f.id} />}
        {form && <FormularioFactura form={form} set={set} editable={editable} items={items}
          setItems={(v) => { setItems(v); setSucio(true); }} />}
      </div>
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

function FormularioFactura({ form, set, editable, items, setItems }: {
  form: Form;
  set: (k: keyof Form) => (e: { target: { value: string } }) => void;
  editable: boolean;
  items: ItemForm[];
  setItems: (v: ItemForm[]) => void;
}) {
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
              <tr><th>Descripción</th><th>Cant.</th><th>Unidad</th><th>P. unit.</th><th>IVA %</th><th>Subtotal</th>{editable && <th />}</tr>
            </thead>
            <tbody>
              {items.map((it, i) => (
                <tr key={i}>
                  <td style={{ minWidth: 180 }}><input value={it.descripcion} onChange={(e) => setItem(i, "descripcion", e.target.value)} /></td>
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
