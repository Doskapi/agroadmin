import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState, type DragEvent } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { api, descargar, qs } from "../api";
import { useAuth } from "../auth";
import { BadgeFactura, ErrorMsg, Field, Modal } from "../components/ui";
import { capitalizar, comprobante, cuit, fecha, monto, pesos, TIPOS_COMPROBANTE } from "../format";
import { porId, useCampanias, useCampos, useCategorias, useProveedores } from "../hooks";
import type { CatalogoFacturas, EstadoFactura, Factura, ResultadoAccionMasiva } from "../types";

const POR_PAGINA = 50;
const TABS: { valor: EstadoFactura | ""; texto: string }[] = [
  { valor: "", texto: "Todas" },
  { valor: "pendiente_revision", texto: "A revisar" },
  { valor: "confirmada", texto: "Confirmadas" },
  { valor: "error", texto: "Con error" },
  { valor: "procesando", texto: "Procesando" },
  { valor: "anulada", texto: "Anuladas" },
];
const ACEPTA = ".pdf,.jpg,.jpeg,.png,.webp";
// Filtros que viven en la URL (así un link desde un reporte abre el catálogo ya filtrado)
const FILTROS = ["q", "estado", "proveedor_id", "categoria_id", "campania_id", "campo_id", "lote_id",
  "tipo_comprobante", "moneda", "desde", "hasta", "monto_min", "monto_max", "sin_imputar", "pago"] as const;
type Orden = "fecha" | "total" | "proveedor" | "numero" | "estado";

export default function Facturas() {
  const { puede } = useAuth();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [params, setParams] = useSearchParams();
  const get = (k: string) => params.get(k) ?? "";
  const filtros = Object.fromEntries(FILTROS.map((k) => [k, get(k)])) as Record<(typeof FILTROS)[number], string>;
  const orden = (get("orden") || "fecha") as Orden;
  const dir = get("dir") || "desc";
  const pagina = Number(get("pagina") || 1);

  const setParam = (cambios: Record<string, string>, resetPagina = true) => {
    const p = new URLSearchParams(params);
    for (const [k, v] of Object.entries(cambios)) {
      if (v) p.set(k, v);
      else p.delete(k);
    }
    if (resetPagina) p.delete("pagina");
    setParams(p, { replace: true });
  };
  const setFiltro = (k: string, v: string) => setParam({ [k]: v, ...(k === "campo_id" ? { lote_id: "" } : {}) });

  const [seleccion, setSeleccion] = useState<Set<number>>(new Set());
  const [resultado, setResultado] = useState<ResultadoAccionMasiva | null>(null);
  useEffect(() => setSeleccion(new Set()), [params]);

  const query = qs({ ...filtros, orden, dir, limit: POR_PAGINA, offset: (pagina - 1) * POR_PAGINA });
  const lista = useQuery({
    queryKey: ["facturas", query],
    queryFn: () => api<CatalogoFacturas>(`/facturas/catalogo${query}`),
    placeholderData: (prev) => prev,
    // mientras haya facturas procesándose, refrescamos solo
    refetchInterval: (q) => (q.state.data?.items.some((f) => f.estado === "procesando") ? 2500 : false),
  });
  const filas = lista.data?.items ?? [];
  const paginas = Math.max(1, Math.ceil((lista.data?.total ?? 0) / POR_PAGINA));

  const crearManual = useMutation({
    mutationFn: () => api<Factura>("/facturas", { method: "POST", json: {} }),
    onSuccess: (f) => navigate(`/facturas/${f.id}`),
  });
  const [exportando, setExportando] = useState(false);
  async function excel() {
    setExportando(true);
    try {
      await descargar(`/facturas/catalogo.xlsx${qs({ ...filtros, orden, dir: "asc" })}`, "facturas.xlsx");
    } finally {
      setExportando(false);
    }
  }

  const ordenarPor = (o: Orden) =>
    setParam({ orden: o, dir: orden === o && dir === "desc" ? "asc" : "desc" }, false);
  const Th = ({ o, children, className }: { o: Orden; children: string; className?: string }) => (
    <th className={`sortable ${className ?? ""}`} aria-sort={orden === o ? (dir === "asc" ? "ascending" : "descending") : "none"}>
      <button type="button" onClick={() => ordenarPor(o)}>
        {children} {orden === o ? (dir === "asc" ? "▲" : "▼") : ""}
      </button>
    </th>
  );

  const seleccionable = puede("facturas:escribir") || puede("facturas:confirmar");
  const todasSeleccionadas = filas.length > 0 && filas.every((f) => seleccion.has(f.id));
  const alternar = (id: number) =>
    setSeleccion((s) => {
      const n = new Set(s);
      if (n.has(id)) n.delete(id);
      else n.add(id);
      return n;
    });

  const categorias = porId(useCategorias().data, (c) => capitalizar(c.nombre));
  const campanias = porId(useCampanias().data, (c) => c.nombre);
  const camposData = useCampos().data;
  const campos = porId(camposData, (c) => c.nombre);
  const lotes = new Map((camposData ?? []).flatMap((c) => c.lotes.map((l) => [l.id, l.nombre] as const)));

  return (
    <div className="stack">
      <div className="page-head">
        <h1>Facturas</h1>
        <div className="row">
          <button onClick={excel} disabled={exportando || !lista.data?.total}>
            {exportando ? "Generando…" : "⬇ Excel"}
          </button>
          {puede("facturas:escribir") && (
            <button onClick={() => crearManual.mutate()} disabled={crearManual.isPending}>+ Carga manual</button>
          )}
        </div>
      </div>

      {puede("facturas:escribir") && (
        <Importador onImportado={() => qc.invalidateQueries({ queryKey: ["facturas"] })} />
      )}

      <div>
        <div className="tabs" role="tablist">
          {TABS.map((t) => (
            <button key={t.valor} role="tab" aria-selected={filtros.estado === t.valor}
              className={filtros.estado === t.valor ? "active" : ""} onClick={() => setFiltro("estado", t.valor)}>
              {t.texto}
            </button>
          ))}
        </div>
        <PanelFiltros filtros={filtros} setFiltro={setFiltro} limpiar={() => setParams(new URLSearchParams(), { replace: true })} />

        {resultado && <ResultadoAccion r={resultado} onCerrar={() => setResultado(null)} />}
        {seleccion.size > 0 && (
          <AccionesMasivas ids={[...seleccion]} onListo={(r) => {
            setResultado(r);
            setSeleccion(new Set());
            qc.invalidateQueries({ queryKey: ["facturas"] });
            qc.invalidateQueries({ queryKey: ["resumen"] });
          }} />
        )}

        <ErrorMsg error={lista.error} />
        <div className="card flush table-wrap">
          <table>
            <thead>
              <tr>
                {seleccionable && (
                  <th style={{ width: 32 }}>
                    <input type="checkbox" aria-label="Seleccionar todas las de esta página" checked={todasSeleccionadas}
                      onChange={() => setSeleccion(todasSeleccionadas ? new Set() : new Set(filas.map((f) => f.id)))} />
                  </th>
                )}
                <Th o="fecha">Fecha</Th>
                <Th o="proveedor">Proveedor</Th>
                <Th o="numero">Comprobante</Th>
                <th>Imputación</th>
                <Th o="total" className="num">Total</Th>
                <Th o="estado">Estado</Th>
              </tr>
            </thead>
            <tbody>
              {filas.map((f) => (
                <tr key={f.id} className="clickable" onClick={() => navigate(`/facturas/${f.id}`)}>
                  {seleccionable && (
                    <td onClick={(e) => e.stopPropagation()}>
                      <input type="checkbox" aria-label={`Seleccionar factura ${f.id}`} checked={seleccion.has(f.id)}
                        onChange={() => alternar(f.id)} />
                    </td>
                  )}
                  <td>{fecha(f.fecha_emision)}</td>
                  <td>
                    {f.proveedor?.razon_social ?? <span className="muted">{f.cuit_emisor ? cuit(f.cuit_emisor) : "—"}</span>}
                  </td>
                  <td>{comprobante(f)}</td>
                  <td className="imputacion">
                    {[
                      f.categoria_id && categorias.get(f.categoria_id),
                      f.campania_id && campanias.get(f.campania_id),
                      f.repartida ? "Repartida" : [f.campo_id && campos.get(f.campo_id), f.lote_id && lotes.get(f.lote_id)].filter(Boolean).join(" / "),
                    ].filter(Boolean).join(" · ") || <span className="muted">Sin imputar</span>}
                  </td>
                  <td className="num">
                    {monto(f.total, f.moneda)}
                    {f.estado === "confirmada" && f.saldo != null && Number(f.saldo) > 0.01 && (
                      <div className="muted" style={{ fontSize: 11 }}>
                        {Number(f.saldo) < Number(f.total) ? `saldo ${monto(f.saldo, f.moneda)}` : "impaga"}
                      </div>
                    )}
                  </td>
                  <td><BadgeFactura estado={f.estado} /></td>
                </tr>
              ))}
            </tbody>
          </table>
          {lista.isPending && <div className="empty"><span className="spinner" /></div>}
          {lista.isSuccess && filas.length === 0 && <div className="empty">No hay facturas con estos filtros.</div>}
        </div>
        {lista.data && lista.data.total > 0 && (
          <div className="row pie-tabla">
            <span className="muted">
              {lista.data.total} factura{lista.data.total === 1 ? "" : "s"} · suma {pesos(lista.data.suma_pesos)}
              <span title="En pesos, con la cotización de cada comprobante; las notas de crédito restan"> ⓘ</span>
            </span>
            {paginas > 1 && (
              <div className="row">
                <button className="small" disabled={pagina <= 1} onClick={() => setParam({ pagina: String(pagina - 1) }, false)}>
                  ← Anterior
                </button>
                <span className="muted">Página {pagina} de {paginas}</span>
                <button className="small" disabled={pagina >= paginas} onClick={() => setParam({ pagina: String(pagina + 1) }, false)}>
                  Siguiente →
                </button>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function PanelFiltros({ filtros, setFiltro, limpiar }: {
  filtros: Record<string, string>;
  setFiltro: (k: string, v: string) => void;
  limpiar: () => void;
}) {
  const proveedores = useProveedores();
  const categorias = useCategorias();
  const campanias = useCampanias();
  const campos = useCampos();
  const lotes = campos.data?.find((c) => String(c.id) === filtros.campo_id)?.lotes ?? [];
  const avanzados = ["categoria_id", "campania_id", "campo_id", "lote_id", "tipo_comprobante", "moneda",
    "monto_min", "monto_max", "sin_imputar", "pago"];
  const [abierto, setAbierto] = useState(() => avanzados.some((k) => filtros[k]));

  // La búsqueda se aplica cuando se deja de tipear
  const [q, setQ] = useState(filtros.q);
  useEffect(() => setQ(filtros.q), [filtros.q]);
  useEffect(() => {
    if (q === filtros.q) return;
    const t = setTimeout(() => setFiltro("q", q), 350);
    return () => clearTimeout(t);
  }, [q]); // eslint-disable-line react-hooks/exhaustive-deps

  const sel = (k: string) => ({ value: filtros[k], onChange: (e: { target: { value: string } }) => setFiltro(k, e.target.value) });
  const hayFiltros = Object.entries(filtros).some(([k, v]) => v && k !== "estado");

  return (
    <div className="stack" style={{ gap: 12, marginBottom: 12 }}>
      <div className="row">
        <input type="search" className="buscador" placeholder="Buscar por proveedor, CUIT, número, ítem u observación"
          value={q} onChange={(e) => setQ(e.target.value)} aria-label="Buscar facturas" />
        <Field label="Proveedor">
          <select {...sel("proveedor_id")}>
            <option value="">Todos</option>
            {proveedores.data?.map((p) => <option key={p.id} value={p.id}>{p.razon_social}</option>)}
          </select>
        </Field>
        <Field label="Desde"><input type="date" {...sel("desde")} /></Field>
        <Field label="Hasta"><input type="date" {...sel("hasta")} /></Field>
        <button type="button" className="small" style={{ alignSelf: "end", marginBottom: 4 }} onClick={() => setAbierto((a) => !a)}
          aria-expanded={abierto}>
          {abierto ? "Menos filtros" : "Más filtros"}
        </button>
        {hayFiltros && (
          <button type="button" className="small" style={{ alignSelf: "end", marginBottom: 4 }} onClick={limpiar}>
            Limpiar filtros
          </button>
        )}
      </div>
      {abierto && (
        <div className="row">
          <Field label="Rubro">
            <select {...sel("categoria_id")}>
              <option value="">Todos</option>
              {categorias.data?.map((c) => <option key={c.id} value={c.id}>{capitalizar(c.nombre)}</option>)}
            </select>
          </Field>
          <Field label="Campaña">
            <select {...sel("campania_id")}>
              <option value="">Todas</option>
              {campanias.data?.map((c) => <option key={c.id} value={c.id}>{c.nombre}</option>)}
            </select>
          </Field>
          <Field label="Campo">
            <select {...sel("campo_id")}>
              <option value="">Todos</option>
              {campos.data?.map((c) => <option key={c.id} value={c.id}>{c.nombre}</option>)}
            </select>
          </Field>
          <Field label="Lote">
            <select {...sel("lote_id")} disabled={!lotes.length}>
              <option value="">Todos</option>
              {lotes.map((l) => <option key={l.id} value={l.id}>{l.nombre}</option>)}
            </select>
          </Field>
          <Field label="Tipo">
            <select {...sel("tipo_comprobante")}>
              <option value="">Todos</option>
              {Object.entries(TIPOS_COMPROBANTE).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
          </Field>
          <Field label="Moneda">
            <select {...sel("moneda")}>
              <option value="">Todas</option>
              <option value="PES">Pesos</option>
              <option value="DOL">Dólares</option>
            </select>
          </Field>
          <Field label="Pago">
            <select {...sel("pago")}>
              <option value="">Todas</option>
              <option value="pendiente">Con saldo</option>
              <option value="vencida">Vencidas impagas</option>
              <option value="pagada">Pagadas</option>
            </select>
          </Field>
          <Field label="Total desde"><input type="number" step="0.01" style={{ width: 120 }} {...sel("monto_min")} /></Field>
          <Field label="Total hasta"><input type="number" step="0.01" style={{ width: 120 }} {...sel("monto_max")} /></Field>
          <label className="row" style={{ alignSelf: "end", paddingBottom: 8, fontSize: 13 }}>
            <input type="checkbox" checked={filtros.sin_imputar === "true"}
              onChange={(e) => setFiltro("sin_imputar", e.target.checked ? "true" : "")} />
            Sin rubro, campaña o campo
          </label>
        </div>
      )}
    </div>
  );
}

function AccionesMasivas({ ids, onListo }: { ids: number[]; onListo: (r: ResultadoAccionMasiva) => void }) {
  const { puede } = useAuth();
  const [imputando, setImputando] = useState(false);
  const accion = useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      api<ResultadoAccionMasiva>("/facturas/acciones", { method: "POST", json: { ids, ...body } }),
    onSuccess: (r) => {
      setImputando(false);
      onListo(r);
    },
  });

  return (
    <div className="stack" style={{ gap: 8, marginBottom: 12 }}>
      <div className="barra-seleccion row">
        <strong>{ids.length} seleccionada{ids.length === 1 ? "" : "s"}</strong>
        {puede("facturas:escribir") && <button className="small" onClick={() => setImputando(true)}>Imputar…</button>}
        {puede("facturas:confirmar") && (
          <button className="small primary" disabled={accion.isPending}
            onClick={() => confirm(`¿Confirmar ${ids.length} factura(s)?`) && accion.mutate({ accion: "confirmar" })}>
            ✓ Confirmar
          </button>
        )}
      </div>
      <ErrorMsg error={accion.error} />
      {imputando && <ModalImputar onClose={() => setImputando(false)} pending={accion.isPending}
        onAplicar={(cambios) => accion.mutate({ accion: "imputar", ...cambios })} />}
    </div>
  );
}

function ResultadoAccion({ r, onCerrar }: { r: ResultadoAccionMasiva; onCerrar: () => void }) {
  const errores = Object.entries(r.errores);
  return (
    <div className={`alert ${errores.length ? "warning" : "good"}`} role="status" style={{ marginBottom: 12 }}>
      {r.ok.length} factura{r.ok.length === 1 ? "" : "s"} actualizada{r.ok.length === 1 ? "" : "s"}.
      {errores.length > 0 && (
        <>
          {" "}No se pudieron actualizar {errores.length}:
          <ul>{errores.map(([id, m]) => <li key={id}>#{id}: {m}</li>)}</ul>
        </>
      )}
      <button className="small" style={{ marginLeft: 8 }} onClick={onCerrar}>Cerrar</button>
    </div>
  );
}

function ModalImputar({ onClose, onAplicar, pending }: {
  onClose: () => void; onAplicar: (c: Record<string, number>) => void; pending: boolean;
}) {
  const categorias = useCategorias();
  const campanias = useCampanias();
  const campos = useCampos();
  const [f, setF] = useState({ categoria_id: "", campania_id: "", campo_id: "", lote_id: "" });
  const lotes = campos.data?.find((c) => String(c.id) === f.campo_id)?.lotes ?? [];
  const cambios = Object.fromEntries(Object.entries(f).filter(([, v]) => v).map(([k, v]) => [k, Number(v)]));
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) =>
    setF((x) => ({ ...x, [k]: e.target.value, ...(k === "campo_id" ? { lote_id: "" } : {}) }));

  return (
    <Modal titulo="Imputar facturas seleccionadas" onClose={onClose}>
      <p className="muted" style={{ marginTop: 0 }}>Solo se cambia lo que elijas; lo demás queda como está.
        Las facturas confirmadas o anuladas no se modifican.</p>
      <div className="form-grid">
        <Field label="Rubro">
          <select value={f.categoria_id} onChange={set("categoria_id")}>
            <option value="">(no cambiar)</option>
            {categorias.data?.map((c) => <option key={c.id} value={c.id}>{capitalizar(c.nombre)}</option>)}
          </select>
        </Field>
        <Field label="Campaña">
          <select value={f.campania_id} onChange={set("campania_id")}>
            <option value="">(no cambiar)</option>
            {campanias.data?.map((c) => <option key={c.id} value={c.id}>{c.nombre}</option>)}
          </select>
        </Field>
        <Field label="Campo">
          <select value={f.campo_id} onChange={set("campo_id")}>
            <option value="">(no cambiar)</option>
            {campos.data?.map((c) => <option key={c.id} value={c.id}>{c.nombre}</option>)}
          </select>
        </Field>
        <Field label="Lote">
          <select value={f.lote_id} onChange={set("lote_id")} disabled={!lotes.length}>
            <option value="">(todo el campo)</option>
            {lotes.map((l) => <option key={l.id} value={l.id}>{l.nombre}</option>)}
          </select>
        </Field>
      </div>
      <div className="modal-actions">
        <button type="button" onClick={onClose}>Cancelar</button>
        <button className="primary" disabled={pending || !Object.keys(cambios).length} onClick={() => onAplicar(cambios)}>
          Aplicar
        </button>
      </div>
    </Modal>
  );
}

function Importador({ onImportado }: { onImportado: () => void }) {
  const input = useRef<HTMLInputElement>(null);
  const camara = useRef<HTMLInputElement>(null);
  // En el celular, botón para sacar la foto directamente con la cámara
  const tactil = typeof matchMedia === "function" && matchMedia("(pointer: coarse)").matches;
  const [over, setOver] = useState(false);
  const [subiendo, setSubiendo] = useState(0);
  const [errores, setErrores] = useState<string[]>([]);

  async function subir(archivos: FileList | File[]) {
    const lista = Array.from(archivos);
    if (!lista.length) return;
    setErrores([]);
    setSubiendo(lista.length);
    const errs: string[] = [];
    // de a uno para no saturar la API; cada uno se procesa en segundo plano en el servidor
    for (const archivo of lista) {
      const fd = new FormData();
      fd.append("archivo", archivo);
      try {
        await api("/facturas/importar", { method: "POST", body: fd });
      } catch (e) {
        errs.push(`${archivo.name}: ${e instanceof Error ? e.message : e}`);
      }
      setSubiendo((n) => n - 1);
      onImportado();
    }
    setErrores(errs);
  }

  const onDrop = (e: DragEvent) => {
    e.preventDefault();
    setOver(false);
    subir(e.dataTransfer.files);
  };

  return (
    <div className="stack" style={{ gap: 8 }}>
      <div
        className={`dropzone${over ? " over" : ""}`}
        onClick={() => input.current?.click()}
        onDragOver={(e) => { e.preventDefault(); setOver(true); }}
        onDragLeave={() => setOver(false)}
        onDrop={onDrop}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => e.key === "Enter" && input.current?.click()}
      >
        {subiendo > 0 ? (
          <span><span className="spinner" /> Subiendo {subiendo} archivo{subiendo > 1 ? "s" : ""}…</span>
        ) : (
          <>
            <strong>Arrastrá facturas acá</strong> o hacé clic para elegirlas
            <div className="muted" style={{ fontSize: 12, marginTop: 4 }}>
              PDF o foto (JPG, PNG, WEBP). Se leen el QR de ARCA y el detalle automáticamente.
            </div>
          </>
        )}
        <input ref={input} type="file" accept={ACEPTA} multiple hidden
          onChange={(e) => { if (e.target.files) subir(e.target.files); e.target.value = ""; }} />
      </div>
      {tactil && (
        <>
          <button type="button" className="primary" onClick={() => camara.current?.click()} disabled={subiendo > 0}>
            📷 Sacar foto de una factura
          </button>
          <input ref={camara} type="file" accept="image/*" capture="environment" hidden
            onChange={(e) => { if (e.target.files) subir(e.target.files); e.target.value = ""; }} />
        </>
      )}
      {errores.length > 0 && (
        <div className="alert critical">
          No se pudieron importar:
          <ul>{errores.map((e) => <li key={e}>{e}</li>)}</ul>
        </div>
      )}
    </div>
  );
}
