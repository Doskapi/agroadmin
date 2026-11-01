import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent, type ReactNode } from "react";
import { api } from "../api";
import { useAuth } from "../auth";
import { ErrorMsg, Field, Modal, nullSiVacio } from "../components/ui";
import { capitalizar, cuit, fecha, num } from "../format";
import { useCampanias, useCampos, useCategorias, useProveedores } from "../hooks";
import type { Campo, Proveedor } from "../types";

const TABS = { proveedores: "Proveedores", campos: "Campos y lotes", campanias: "Campañas", categorias: "Rubros" } as const;
type Tab = keyof typeof TABS;

export default function Catalogos() {
  const [tab, setTab] = useState<Tab>("proveedores");
  return (
    <div>
      <div className="page-head"><h1>Catálogos</h1></div>
      <div className="tabs" role="tablist">
        {Object.entries(TABS).map(([k, v]) => (
          <button key={k} role="tab" aria-selected={tab === k} className={tab === k ? "active" : ""} onClick={() => setTab(k as Tab)}>
            {v}
          </button>
        ))}
      </div>
      {tab === "proveedores" && <Proveedores />}
      {tab === "campos" && <Campos />}
      {tab === "campanias" && <Campanias />}
      {tab === "categorias" && <Categorias />}
    </div>
  );
}

/** Mutación que al terminar invalida el catálogo y cierra el modal. */
function useGuardar(clave: string, onDone?: () => void) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ path, method, json }: { path: string; method: string; json: unknown }) => api(path, { method, json }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: [clave] });
      onDone?.();
    },
  });
}

function FormModal({ titulo, onClose, onSubmit, error, pending, children }: {
  titulo: string; onClose: () => void; onSubmit: () => void; error: unknown; pending: boolean; children: ReactNode;
}) {
  return (
    <Modal titulo={titulo} onClose={onClose}>
      <form onSubmit={(e: FormEvent) => { e.preventDefault(); onSubmit(); }}>
        <ErrorMsg error={error} />
        <div className="form-grid" style={{ marginTop: 8 }}>{children}</div>
        <div className="modal-actions">
          <button type="button" onClick={onClose}>Cancelar</button>
          <button className="primary" disabled={pending}>Guardar</button>
        </div>
      </form>
    </Modal>
  );
}

// --- Proveedores -------------------------------------------------------------

function Proveedores() {
  const { puede } = useAuth();
  const lista = useProveedores();
  const [buscar, setBuscar] = useState("");
  const [editando, setEditando] = useState<Proveedor | "nuevo" | null>(null);
  const q = buscar.toLowerCase();
  const filas = lista.data?.filter((p) => !q || p.razon_social.toLowerCase().includes(q) || p.cuit.includes(q)) ?? [];

  return (
    <div className="stack">
      <div className="row" style={{ justifyContent: "space-between" }}>
        <input placeholder="Buscar por nombre o CUIT" value={buscar} onChange={(e) => setBuscar(e.target.value)} style={{ width: 280 }} />
        {puede("catalogos:escribir") && <button className="primary" onClick={() => setEditando("nuevo")}>+ Proveedor</button>}
      </div>
      <div className="card flush table-wrap">
        <table>
          <thead><tr><th>Razón social</th><th>CUIT</th><th>Condición IVA</th><th>Email</th><th>Teléfono</th></tr></thead>
          <tbody>
            {filas.map((p) => (
              <tr key={p.id} className={puede("catalogos:escribir") ? "clickable" : ""}
                onClick={() => puede("catalogos:escribir") && setEditando(p)}>
                <td>{p.razon_social}</td><td>{cuit(p.cuit)}</td><td>{p.condicion_iva ?? "—"}</td>
                <td>{p.email ?? "—"}</td><td>{p.telefono ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {lista.isSuccess && !filas.length && (
          <div className="empty">Sin proveedores. Se crean solos al importar facturas, o podés cargarlos acá.</div>
        )}
      </div>
      {editando && <FormProveedor p={editando === "nuevo" ? null : editando} onClose={() => setEditando(null)} />}
    </div>
  );
}

function FormProveedor({ p, onClose }: { p: Proveedor | null; onClose: () => void }) {
  const [f, setF] = useState({
    cuit: p?.cuit ?? "", razon_social: p?.razon_social ?? "", condicion_iva: p?.condicion_iva ?? "",
    email: p?.email ?? "", telefono: p?.telefono ?? "",
  });
  const g = useGuardar("proveedores", onClose);
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF((x) => ({ ...x, [k]: e.target.value }));
  const json = { ...f, condicion_iva: nullSiVacio(f.condicion_iva), email: nullSiVacio(f.email), telefono: nullSiVacio(f.telefono) };

  return (
    <FormModal titulo={p ? "Editar proveedor" : "Nuevo proveedor"} onClose={onClose} error={g.error} pending={g.isPending}
      onSubmit={() => g.mutate({ path: p ? `/proveedores/${p.id}` : "/proveedores", method: p ? "PUT" : "POST", json })}>
      <Field label="Razón social" wide><input required value={f.razon_social} onChange={set("razon_social")} /></Field>
      <Field label="CUIT"><input required value={f.cuit} onChange={set("cuit")} placeholder="30-12345678-9" /></Field>
      <Field label="Condición IVA">
        <select value={f.condicion_iva} onChange={set("condicion_iva")}>
          <option value="">—</option>
          <option>Responsable Inscripto</option><option>Monotributo</option><option>Exento</option>
        </select>
      </Field>
      <Field label="Email"><input type="email" value={f.email} onChange={set("email")} /></Field>
      <Field label="Teléfono"><input value={f.telefono} onChange={set("telefono")} /></Field>
    </FormModal>
  );
}

// --- Campos y lotes ----------------------------------------------------------

function Campos() {
  const { puede } = useAuth();
  const lista = useCampos();
  const [editando, setEditando] = useState<Campo | "nuevo" | null>(null);
  const [loteDe, setLoteDe] = useState<Campo | null>(null);
  const escribir = puede("catalogos:escribir");

  return (
    <div className="stack">
      {escribir && <div><button className="primary" onClick={() => setEditando("nuevo")}>+ Campo</button></div>}
      {lista.data?.map((c) => (
        <div key={c.id} className="card">
          <div className="row" style={{ justifyContent: "space-between" }}>
            <div>
              <h3 style={{ margin: 0 }}>{c.nombre}</h3>
              <div className="muted">{[c.ubicacion, c.hectareas && `${num(c.hectareas)} ha`].filter(Boolean).join(" · ") || "—"}</div>
            </div>
            {escribir && (
              <div className="row">
                <button className="small" onClick={() => setEditando(c)}>Editar</button>
                <button className="small" onClick={() => setLoteDe(c)}>+ Lote</button>
              </div>
            )}
          </div>
          {c.lotes.length > 0 && (
            <div className="row" style={{ marginTop: 10 }}>
              {c.lotes.map((l) => (
                <span key={l.id} className="badge muted">{l.nombre}{l.hectareas ? ` · ${num(l.hectareas)} ha` : ""}</span>
              ))}
            </div>
          )}
        </div>
      ))}
      {lista.isSuccess && !lista.data.length && <div className="card empty">Todavía no hay campos cargados.</div>}
      {editando && <FormCampo c={editando === "nuevo" ? null : editando} onClose={() => setEditando(null)} />}
      {loteDe && <FormLote campo={loteDe} onClose={() => setLoteDe(null)} />}
    </div>
  );
}

function FormCampo({ c, onClose }: { c: Campo | null; onClose: () => void }) {
  const [f, setF] = useState({ nombre: c?.nombre ?? "", ubicacion: c?.ubicacion ?? "", hectareas: c?.hectareas ?? "" });
  const g = useGuardar("campos", onClose);
  const json = { nombre: f.nombre, ubicacion: nullSiVacio(f.ubicacion), hectareas: nullSiVacio(f.hectareas) };
  return (
    <FormModal titulo={c ? "Editar campo" : "Nuevo campo"} onClose={onClose} error={g.error} pending={g.isPending}
      onSubmit={() => g.mutate({ path: c ? `/campos/${c.id}` : "/campos", method: c ? "PUT" : "POST", json })}>
      <Field label="Nombre"><input required value={f.nombre} onChange={(e) => setF({ ...f, nombre: e.target.value })} /></Field>
      <Field label="Ubicación"><input value={f.ubicacion} onChange={(e) => setF({ ...f, ubicacion: e.target.value })} /></Field>
      <Field label="Hectáreas"><input type="number" step="0.01" value={f.hectareas} onChange={(e) => setF({ ...f, hectareas: e.target.value })} /></Field>
    </FormModal>
  );
}

function FormLote({ campo, onClose }: { campo: Campo; onClose: () => void }) {
  const [f, setF] = useState({ nombre: "", hectareas: "" });
  const g = useGuardar("campos", onClose);
  return (
    <FormModal titulo={`Nuevo lote en ${campo.nombre}`} onClose={onClose} error={g.error} pending={g.isPending}
      onSubmit={() => g.mutate({ path: `/campos/${campo.id}/lotes`, method: "POST",
        json: { nombre: f.nombre, hectareas: nullSiVacio(f.hectareas) } })}>
      <Field label="Nombre"><input required value={f.nombre} onChange={(e) => setF({ ...f, nombre: e.target.value })} /></Field>
      <Field label="Hectáreas"><input type="number" step="0.01" value={f.hectareas} onChange={(e) => setF({ ...f, hectareas: e.target.value })} /></Field>
    </FormModal>
  );
}

// --- Campañas y rubros -------------------------------------------------------

function Campanias() {
  const { puede } = useAuth();
  const lista = useCampanias();
  const [nueva, setNueva] = useState(false);
  const [f, setF] = useState({ nombre: "", fecha_inicio: "", fecha_fin: "" });
  const g = useGuardar("campanias", () => setNueva(false));

  return (
    <div className="stack">
      {puede("catalogos:escribir") && <div><button className="primary" onClick={() => setNueva(true)}>+ Campaña</button></div>}
      <div className="card flush table-wrap">
        <table>
          <thead><tr><th>Campaña</th><th>Inicio</th><th>Fin</th></tr></thead>
          <tbody>
            {lista.data?.map((c) => <tr key={c.id}><td>{c.nombre}</td><td>{fecha(c.fecha_inicio)}</td><td>{fecha(c.fecha_fin)}</td></tr>)}
          </tbody>
        </table>
        {lista.isSuccess && !lista.data.length && <div className="empty">Sin campañas.</div>}
      </div>
      {nueva && (
        <FormModal titulo="Nueva campaña" onClose={() => setNueva(false)} error={g.error} pending={g.isPending}
          onSubmit={() => g.mutate({ path: "/campanias", method: "POST", json: f })}>
          <Field label="Nombre"><input required placeholder="2026/27" value={f.nombre} onChange={(e) => setF({ ...f, nombre: e.target.value })} /></Field>
          <Field label="Inicio"><input type="date" required value={f.fecha_inicio} onChange={(e) => setF({ ...f, fecha_inicio: e.target.value })} /></Field>
          <Field label="Fin"><input type="date" required value={f.fecha_fin} onChange={(e) => setF({ ...f, fecha_fin: e.target.value })} /></Field>
        </FormModal>
      )}
    </div>
  );
}

function Categorias() {
  const { puede } = useAuth();
  const lista = useCategorias();
  const [nombre, setNombre] = useState("");
  const g = useGuardar("categorias", () => setNombre(""));

  return (
    <div className="stack">
      {puede("catalogos:escribir") && (
        <form className="row" onSubmit={(e) => { e.preventDefault(); g.mutate({ path: "/categorias", method: "POST", json: { nombre } }); }}>
          <input placeholder="Nuevo rubro" required value={nombre} onChange={(e) => setNombre(e.target.value)} />
          <button disabled={g.isPending}>Agregar</button>
        </form>
      )}
      <ErrorMsg error={g.error} />
      <div className="card">
        <div className="row">
          {lista.data?.map((c) => <span key={c.id} className="badge muted">{capitalizar(c.nombre)}</span>)}
        </div>
      </div>
    </div>
  );
}
