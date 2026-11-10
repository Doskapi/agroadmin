import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent, type ReactNode } from "react";
import { useSearchParams } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";
import { ErrorMsg, Field, Modal, nullSiVacio } from "../components/ui";
import { capitalizar, cuit, fecha, num } from "../format";
import { porId, useCampanias, useCampos, useCategorias, useInsumos, useProveedores } from "../hooks";
import type { Campo, Cotizacion, Insumo, ItemSinInsumo, Proveedor } from "../types";

const TABS = {
  proveedores: "Proveedores", campos: "Campos y lotes", campanias: "Campañas", categorias: "Rubros",
  insumos: "Insumos", cotizaciones: "Cotización del dólar",
} as const;
type Tab = keyof typeof TABS;

export default function Catalogos() {
  const [params, setParams] = useSearchParams();
  const tab = (params.get("tab") ?? "proveedores") as Tab;
  const setTab = (t: Tab) => setParams({ tab: t }, { replace: true });
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
      {tab === "insumos" && <Insumos />}
      {tab === "cotizaciones" && <Cotizaciones />}
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
  const rubros = porId(useCategorias().data, (c) => capitalizar(c.nombre));
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
          <thead><tr><th>Razón social</th><th>CUIT</th><th>Condición IVA</th><th>Rubro por defecto</th><th>Email</th><th>Teléfono</th></tr></thead>
          <tbody>
            {filas.map((p) => (
              <tr key={p.id} className={puede("catalogos:escribir") ? "clickable" : ""}
                onClick={() => puede("catalogos:escribir") && setEditando(p)}>
                <td>{p.razon_social}</td><td>{cuit(p.cuit)}</td><td>{p.condicion_iva ?? "—"}</td>
                <td>{p.categoria_id ? rubros.get(p.categoria_id) : "—"}</td>
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
    email: p?.email ?? "", telefono: p?.telefono ?? "", categoria_id: p?.categoria_id ? String(p.categoria_id) : "",
  });
  const categorias = useCategorias();
  const g = useGuardar("proveedores", onClose);
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF((x) => ({ ...x, [k]: e.target.value }));
  const json = {
    ...f, condicion_iva: nullSiVacio(f.condicion_iva), email: nullSiVacio(f.email), telefono: nullSiVacio(f.telefono),
    categoria_id: f.categoria_id ? Number(f.categoria_id) : null,
  };

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
      <Field label="Rubro por defecto">
        <select value={f.categoria_id} onChange={set("categoria_id")}>
          <option value="">—</option>
          {categorias.data?.map((c) => <option key={c.id} value={c.id}>{capitalizar(c.nombre)}</option>)}
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

// --- Insumos -------------------------------------------------------------------

function Insumos() {
  const { puede } = useAuth();
  const escribir = puede("catalogos:escribir");
  const qc = useQueryClient();
  const insumos = useInsumos();
  const rubros = porId(useCategorias().data, (c) => capitalizar(c.nombre));
  const sinAsignar = useQuery({
    queryKey: ["insumos-sin-asignar"],
    queryFn: () => api<ItemSinInsumo[]>("/insumos/sin-asignar"),
  });
  const [editando, setEditando] = useState<Insumo | "nuevo" | null>(null);
  const asignar = useMutation({
    mutationFn: ({ item, insumo }: { item: number; insumo: number }) =>
      api(`/facturas/items/${item}/insumo`, { method: "PUT", json: { insumo_id: insumo, recordar: true } }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["insumos-sin-asignar"] }),
  });

  return (
    <div className="stack">
      <div className="grid-2" style={{ alignItems: "start" }}>
        <div className="stack">
          <div className="row" style={{ justifyContent: "space-between" }}>
            <h3 style={{ margin: 0 }}>Insumos</h3>
            {escribir && <button className="primary small" onClick={() => setEditando("nuevo")}>+ Insumo</button>}
          </div>
          <div className="card flush table-wrap">
            <table>
              <thead><tr><th>Nombre</th><th>Unidad</th><th>Rubro</th></tr></thead>
              <tbody>
                {insumos.data?.map((i) => (
                  <tr key={i.id} className={escribir ? "clickable" : ""} onClick={() => escribir && setEditando(i)}>
                    <td>{i.nombre}</td><td>{i.unidad ?? "—"}</td><td>{i.categoria_id ? rubros.get(i.categoria_id) : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {insumos.isSuccess && !insumos.data.length && (
              <div className="empty">Creá insumos (ej. "Glifosato 62%") para seguir sus precios.</div>
            )}
          </div>
        </div>

        <div className="stack">
          <h3 style={{ margin: 0 }}>Ítems de factura sin insumo</h3>
          <div className="muted" style={{ fontSize: 13 }}>
            Al asignar uno, todos los ítems con la misma descripción (y los que lleguen después) quedan asignados.
          </div>
          <ErrorMsg error={asignar.error} />
          <div className="card flush table-wrap">
            <table>
              <thead><tr><th>Descripción</th><th className="num">Ítems</th>{escribir && <th>Insumo</th>}</tr></thead>
              <tbody>
                {sinAsignar.data?.map((it) => (
                  <tr key={it.ejemplo_item_id}>
                    <td>{it.descripcion}</td>
                    <td className="num">{it.cantidad_items}</td>
                    {escribir && (
                      <td>
                        <select aria-label={`Insumo para ${it.descripcion}`} value="" disabled={asignar.isPending || !insumos.data?.length}
                          onChange={(e) => e.target.value && asignar.mutate({ item: it.ejemplo_item_id, insumo: Number(e.target.value) })}>
                          <option value="">Asignar…</option>
                          {insumos.data?.map((i) => <option key={i.id} value={i.id}>{i.nombre}</option>)}
                        </select>
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
            {sinAsignar.isSuccess && !sinAsignar.data.length && <div className="empty">Todos los ítems tienen insumo.</div>}
          </div>
        </div>
      </div>
      {editando && <FormInsumo i={editando === "nuevo" ? null : editando} onClose={() => setEditando(null)} />}
    </div>
  );
}

function FormInsumo({ i, onClose }: { i: Insumo | null; onClose: () => void }) {
  const [f, setF] = useState({ nombre: i?.nombre ?? "", unidad: i?.unidad ?? "", categoria_id: i?.categoria_id ? String(i.categoria_id) : "" });
  const categorias = useCategorias();
  const g = useGuardar("insumos", onClose);
  const json = { nombre: f.nombre, unidad: nullSiVacio(f.unidad), categoria_id: f.categoria_id ? Number(f.categoria_id) : null };
  return (
    <FormModal titulo={i ? "Editar insumo" : "Nuevo insumo"} onClose={onClose} error={g.error} pending={g.isPending}
      onSubmit={() => g.mutate({ path: i ? `/insumos/${i.id}` : "/insumos", method: i ? "PUT" : "POST", json })}>
      <Field label="Nombre" wide><input required value={f.nombre} onChange={(e) => setF({ ...f, nombre: e.target.value })} placeholder="Glifosato 62%" /></Field>
      <Field label="Unidad"><input value={f.unidad} onChange={(e) => setF({ ...f, unidad: e.target.value })} placeholder="litro, kg, bolsa…" /></Field>
      <Field label="Rubro">
        <select value={f.categoria_id} onChange={(e) => setF({ ...f, categoria_id: e.target.value })}>
          <option value="">—</option>
          {categorias.data?.map((c) => <option key={c.id} value={c.id}>{capitalizar(c.nombre)}</option>)}
        </select>
      </Field>
    </FormModal>
  );
}

// --- Cotizaciones ------------------------------------------------------------------

function Cotizaciones() {
  const { puede } = useAuth();
  const qc = useQueryClient();
  const lista = useQuery({ queryKey: ["cotizaciones"], queryFn: () => api<Cotizacion[]>("/cotizaciones?limit=60") });
  const [manual, setManual] = useState({ fecha: "", valor: "" });
  const refrescar = () => qc.invalidateQueries({ queryKey: ["cotizaciones"] });
  const actualizar = useMutation({
    mutationFn: () => api<{ guardadas: number }>("/cotizaciones/actualizar", { method: "POST" }),
    onSuccess: refrescar,
  });
  const cargar = useMutation({
    mutationFn: () => api("/cotizaciones", { method: "PUT", json: [manual] }),
    onSuccess: () => { setManual({ fecha: "", valor: "" }); refrescar(); },
  });

  return (
    <div className="stack">
      <div className="muted" style={{ fontSize: 13 }}>
        Pesos por dólar (tipo de cambio de referencia del BCRA). Se usan para ver los reportes en dólares.
      </div>
      {puede("catalogos:escribir") && (
        <div className="row">
          <button className="primary" disabled={actualizar.isPending} onClick={() => actualizar.mutate()}>
            {actualizar.isPending ? "Consultando…" : "Traer las que faltan del BCRA"}
          </button>
          {actualizar.data && <span className="muted">{actualizar.data.guardadas} cotizaciones nuevas</span>}
          <form className="row" onSubmit={(e) => { e.preventDefault(); cargar.mutate(); }}>
            <input type="date" required aria-label="Fecha" value={manual.fecha} onChange={(e) => setManual({ ...manual, fecha: e.target.value })} />
            <input type="number" step="any" min="0" required aria-label="Valor" placeholder="Pesos por dólar" style={{ width: 150 }}
              value={manual.valor} onChange={(e) => setManual({ ...manual, valor: e.target.value })} />
            <button disabled={cargar.isPending}>Cargar a mano</button>
          </form>
        </div>
      )}
      <ErrorMsg error={actualizar.error ?? cargar.error} />
      <div className="card flush table-wrap" style={{ maxWidth: 420 }}>
        <table>
          <thead><tr><th>Fecha</th><th className="num">Pesos por dólar</th></tr></thead>
          <tbody>
            {lista.data?.map((c) => <tr key={c.fecha}><td>{fecha(c.fecha)}</td><td className="num">{num(c.valor)}</td></tr>)}
          </tbody>
        </table>
        {lista.isSuccess && !lista.data.length && <div className="empty">Sin cotizaciones cargadas.</div>}
      </div>
    </div>
  );
}
