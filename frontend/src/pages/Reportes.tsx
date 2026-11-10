import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api, descargar, qs } from "../api";
import { useAuth } from "../auth";
import { BarrasRanking, BarrasTiempo, LineaPrecios } from "../components/Charts";
import { Cargando, ErrorMsg, Field } from "../components/ui";
import { capitalizar, dolaresCompacto, enMoneda, fecha, mes, num, pesos, pesosCompacto, rangoMes } from "../format";
import { useCampanias, useCampos } from "../hooks";
import type {
  Agrupar, FilaCostoHectarea, FilaIva, FilaReporte, PrecioInsumo, ReporteCruce, ResumenInsumo,
} from "../types";

const AGRUPAR: Record<Agrupar, string> = {
  mes: "Mes", categoria: "Rubro", proveedor: "Proveedor", campo: "Campo", lote: "Lote", campania: "Campaña",
};
const VISTAS = {
  gastos: "Gastos", cruce: "Cruce", hectarea: "Costo por hectárea", iva: "IVA compras", insumos: "Insumos",
} as const;
type Vista = keyof typeof VISTAS;
type Moneda = "ARS" | "USD";

// type (no interface) para que sea asignable a Record<string, ...> en qs()
type Filtros = {
  campania_id: string;
  campo_id: string;
  desde: string;
  hasta: string;
  incluir_pendientes: boolean;
  expresado_en: Moneda;
};

/** Link al catálogo de facturas con los filtros del reporte más el valor de la dimensión clickeada. */
function linkCatalogo(f: Filtros, dims: [Agrupar, number | string | null][]) {
  const p: Record<string, string> = {
    campania_id: f.campania_id, campo_id: f.campo_id, desde: f.desde, hasta: f.hasta,
    estado: f.incluir_pendientes ? "" : "confirmada",
  };
  for (const [dim, id] of dims) {
    if (id == null) continue;
    if (dim === "mes") Object.assign(p, rangoMes(String(id)));
    else if (dim === "categoria") p.categoria_id = String(id);
    else p[`${dim}_id`] = String(id);
  }
  return `/facturas${qs(p)}`;
}

const etiquetaDe = (agrupar: Agrupar) => (c: string | null) =>
  agrupar === "mes" ? mes(c) : c ? (agrupar === "categoria" ? capitalizar(c) : c) : "(sin asignar)";

export default function Reportes() {
  const [params, setParams] = useSearchParams();
  const vista = (params.get("vista") ?? "gastos") as Vista;
  const campanias = useCampanias();
  const campos = useCampos();
  const [f, setF] = useState<Filtros>({
    campania_id: "", campo_id: "", desde: "", hasta: "", incluir_pendientes: false, expresado_en: "ARS",
  });
  const set = (k: keyof Filtros) => (e: { target: { value: string } }) => setF((p) => ({ ...p, [k]: e.target.value }));
  const conMoneda = vista === "gastos" || vista === "cruce" || vista === "hectarea";

  return (
    <div className="stack">
      <div className="page-head"><h1>Reportes</h1></div>
      <div className="tabs" role="tablist" style={{ marginBottom: 0 }}>
        {Object.entries(VISTAS).map(([k, v]) => (
          <button key={k} role="tab" aria-selected={vista === k} className={vista === k ? "active" : ""}
            onClick={() => setParams({ vista: k }, { replace: true })}>
            {v}
          </button>
        ))}
      </div>

      <div className="row">
        <Field label="Campaña">
          <select value={f.campania_id} onChange={set("campania_id")}>
            <option value="">Todas</option>
            {campanias.data?.map((c) => <option key={c.id} value={c.id}>{c.nombre}</option>)}
          </select>
        </Field>
        <Field label="Campo">
          <select value={f.campo_id} onChange={set("campo_id")}>
            <option value="">Todos</option>
            {campos.data?.map((c) => <option key={c.id} value={c.id}>{c.nombre}</option>)}
          </select>
        </Field>
        <Field label="Desde"><input type="date" value={f.desde} onChange={set("desde")} /></Field>
        <Field label="Hasta"><input type="date" value={f.hasta} onChange={set("hasta")} /></Field>
        {conMoneda && (
          <Field label="Expresar en">
            <div className="segmented" role="group">
              {(["ARS", "USD"] as const).map((m) => (
                <button key={m} type="button" className={f.expresado_en === m ? "active" : ""} aria-pressed={f.expresado_en === m}
                  onClick={() => setF((p) => ({ ...p, expresado_en: m }))}>
                  {m === "ARS" ? "Pesos" : "Dólares"}
                </button>
              ))}
            </div>
          </Field>
        )}
        <label className="row" style={{ alignSelf: "end", paddingBottom: 8, fontSize: 13 }}>
          <input type="checkbox" checked={f.incluir_pendientes}
            onChange={(e) => setF((p) => ({ ...p, incluir_pendientes: e.target.checked }))} />
          Incluir facturas sin confirmar
        </label>
      </div>

      {conMoneda && f.expresado_en === "USD" && <AvisoCotizaciones f={f} />}
      {vista === "gastos" && <Gastos f={f} />}
      {vista === "cruce" && <Cruce f={f} />}
      {vista === "hectarea" && <CostoHectarea f={f} />}
      {vista === "iva" && <Iva f={f} />}
      {vista === "insumos" && <Insumos f={f} />}
    </div>
  );
}

function AvisoCotizaciones({ f }: { f: Filtros }) {
  const { puede } = useAuth();
  const qc = useQueryClient();
  const { expresado_en: _, ...resto } = f;
  const faltan = useQuery({
    queryKey: ["cotizaciones-faltantes", resto],
    queryFn: () => api<{ facturas_sin_cotizacion: number; primera_fecha_faltante: string | null }>(
      `/reportes/cotizaciones-faltantes${qs(resto)}`),
  });
  const actualizar = useMutation({
    mutationFn: () => api<{ guardadas: number }>(
      `/cotizaciones/actualizar${qs({ desde: faltan.data?.primera_fecha_faltante })}`, { method: "POST" }),
    onSuccess: () => qc.invalidateQueries(),
  });
  if (!faltan.data?.facturas_sin_cotizacion) return null;
  return (
    <div className="alert warning row" style={{ justifyContent: "space-between" }}>
      <span>
        {faltan.data.facturas_sin_cotizacion} factura(s) en pesos no tienen cotización del dólar para su fecha
        (desde {fecha(faltan.data.primera_fecha_faltante)}) y no suman en dólares.
      </span>
      {puede("catalogos:escribir") && (
        <button className="small" disabled={actualizar.isPending} onClick={() => actualizar.mutate()}>
          {actualizar.isPending ? "Consultando BCRA…" : "Traer cotizaciones del BCRA"}
        </button>
      )}
      <ErrorMsg error={actualizar.error} />
    </div>
  );
}

function BotonExcel({ path, nombre, deshabilitado }: { path: string; nombre: string; deshabilitado?: boolean }) {
  const [descargando, setDescargando] = useState(false);
  return (
    <button disabled={descargando || deshabilitado} onClick={async () => {
      setDescargando(true);
      try {
        await descargar(path, nombre);
      } finally {
        setDescargando(false);
      }
    }}>
      {descargando ? "Generando…" : "⬇ Excel"}
    </button>
  );
}

// --- Gastos por una dimensión ---------------------------------------------------

function Gastos({ f }: { f: Filtros }) {
  const [agrupar, setAgrupar] = useState<Agrupar>("categoria");
  const query = qs({ ...f, agrupar });
  const datos = useQuery({ queryKey: ["reporte-gastos", query], queryFn: () => api<FilaReporte[]>(`/reportes/gastos${query}`) });
  const fmt = enMoneda(f.expresado_en);
  const compacto = f.expresado_en === "USD" ? dolaresCompacto : pesosCompacto;
  const etiqueta = etiquetaDe(agrupar);
  const filas = datos.data ?? [];
  const total = filas.reduce((s, x) => s + Number(x.total), 0);
  const puntos = filas.map((x) => ({ etiqueta: etiqueta(x.clave), valor: Number(x.total), cantidad: x.cantidad }));

  return (
    <div className="stack">
      <div className="row" style={{ justifyContent: "space-between" }}>
        <Field label="Agrupar por">
          <select value={agrupar} onChange={(e) => setAgrupar(e.target.value as Agrupar)}>
            {Object.entries(AGRUPAR).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
        </Field>
        <BotonExcel path={`/reportes/gastos.xlsx${query}`} nombre={`gastos_por_${agrupar}.xlsx`} deshabilitado={!filas.length} />
      </div>
      <ErrorMsg error={datos.error} />
      {datos.isPending ? <Cargando /> : (
        <>
          <div className="card">
            {agrupar === "mes"
              ? <BarrasTiempo datos={puntos} formato={fmt} compacto={compacto} />
              : <BarrasRanking datos={puntos.slice(0, 15)} formato={fmt} compacto={compacto} />}
            {agrupar !== "mes" && filas.length > 15 && (
              <div className="muted" style={{ fontSize: 12 }}>El gráfico muestra los 15 mayores; la tabla tiene todos.</div>
            )}
          </div>
          <div className="card flush table-wrap">
            <table>
              <thead>
                <tr><th>{AGRUPAR[agrupar]}</th><th className="num">Comprobantes</th><th className="num">Total</th><th className="num">%</th></tr>
              </thead>
              <tbody>
                {filas.map((x) => (
                  <tr key={String(x.id ?? "_")}>
                    <td>
                      {x.id != null
                        ? <Link to={linkCatalogo(f, [[agrupar, x.id]])} title="Ver las facturas">{etiqueta(x.clave)}</Link>
                        : etiqueta(x.clave)}
                    </td>
                    <td className="num">{x.cantidad}</td>
                    <td className="num">{fmt(x.total)}</td>
                    <td className="num muted">{total ? ((Number(x.total) / total) * 100).toFixed(1) : 0}%</td>
                  </tr>
                ))}
                {filas.length > 0 && (
                  <tr style={{ fontWeight: 600 }}>
                    <td>Total</td>
                    <td className="num">{filas.reduce((s, x) => s + x.cantidad, 0)}</td>
                    <td className="num">{fmt(total)}</td>
                    <td />
                  </tr>
                )}
              </tbody>
            </table>
            {!filas.length && <div className="empty">No hay gastos con estos filtros.</div>}
          </div>
        </>
      )}
    </div>
  );
}

// --- Tabla de doble entrada --------------------------------------------------------

const PRESETS: { texto: string; filas: Agrupar; columnas: Agrupar }[] = [
  { texto: "Rubro × mes", filas: "categoria", columnas: "mes" },
  { texto: "Comparar campañas", filas: "categoria", columnas: "campania" },
  { texto: "Rubro × campo", filas: "categoria", columnas: "campo" },
  { texto: "Proveedor × mes", filas: "proveedor", columnas: "mes" },
];

function Cruce({ f }: { f: Filtros }) {
  const [ejes, setEjes] = useState<{ filas: Agrupar; columnas: Agrupar }>({ filas: "categoria", columnas: "mes" });
  const query = qs({ ...f, ...ejes });
  const datos = useQuery({ queryKey: ["reporte-cruce", query], queryFn: () => api<ReporteCruce>(`/reportes/cruce${query}`) });
  const fmt = enMoneda(f.expresado_en);
  const c = datos.data;
  const celda = new Map(c?.celdas.map((x) => [`${x.fila}|${x.columna}`, Number(x.total)]) ?? []);
  const totalFila = (id: unknown) => c?.columnas.reduce((s, co) => s + (celda.get(`${id}|${co.id}`) ?? 0), 0) ?? 0;
  const totalCol = (id: unknown) => c?.filas.reduce((s, fi) => s + (celda.get(`${fi.id}|${id}`) ?? 0), 0) ?? 0;
  const etF = etiquetaDe(ejes.filas);
  const etC = etiquetaDe(ejes.columnas);

  return (
    <div className="stack">
      <div className="row" style={{ justifyContent: "space-between" }}>
        <div className="row">
          <Field label="Filas">
            <select value={ejes.filas} onChange={(e) => setEjes((x) => ({ ...x, filas: e.target.value as Agrupar }))}>
              {Object.entries(AGRUPAR).map(([k, v]) => <option key={k} value={k} disabled={k === ejes.columnas}>{v}</option>)}
            </select>
          </Field>
          <Field label="Columnas">
            <select value={ejes.columnas} onChange={(e) => setEjes((x) => ({ ...x, columnas: e.target.value as Agrupar }))}>
              {Object.entries(AGRUPAR).map(([k, v]) => <option key={k} value={k} disabled={k === ejes.filas}>{v}</option>)}
            </select>
          </Field>
          {PRESETS.map((p) => (
            <button key={p.texto} className="small" style={{ alignSelf: "end", marginBottom: 4 }}
              onClick={() => setEjes({ filas: p.filas, columnas: p.columnas })}>
              {p.texto}
            </button>
          ))}
        </div>
        <BotonExcel path={`/reportes/cruce.xlsx${query}`} nombre={`${ejes.filas}_por_${ejes.columnas}.xlsx`}
          deshabilitado={!c?.celdas.length} />
      </div>
      <ErrorMsg error={datos.error} />
      {datos.isPending ? <Cargando /> : c && (
        <div className="card flush table-wrap">
          <table className="pivot">
            <thead>
              <tr>
                <th>{AGRUPAR[ejes.filas]} \ {AGRUPAR[ejes.columnas]}</th>
                {c.columnas.map((co) => <th key={String(co.id)} className="num">{etC(co.clave)}</th>)}
                <th className="num">Total</th>
              </tr>
            </thead>
            <tbody>
              {c.filas.map((fi) => (
                <tr key={String(fi.id)}>
                  <td>{etF(fi.clave)}</td>
                  {c.columnas.map((co) => {
                    const v = celda.get(`${fi.id}|${co.id}`);
                    const clickeable = v != null && fi.id != null && co.id != null;
                    return (
                      <td key={String(co.id)} className={`num${clickeable ? " clickable-cell" : ""}`}>
                        {clickeable
                          ? <Link to={linkCatalogo(f, [[ejes.filas, fi.id], [ejes.columnas, co.id]])}>{fmt(v)}</Link>
                          : v != null ? fmt(v) : <span className="muted">—</span>}
                      </td>
                    );
                  })}
                  <td className="num" style={{ fontWeight: 600 }}>{fmt(totalFila(fi.id))}</td>
                </tr>
              ))}
              {c.filas.length > 0 && (
                <tr style={{ fontWeight: 600 }}>
                  <td>Total</td>
                  {c.columnas.map((co) => <td key={String(co.id)} className="num">{fmt(totalCol(co.id))}</td>)}
                  <td className="num">{fmt(c.celdas.reduce((s, x) => s + Number(x.total), 0))}</td>
                </tr>
              )}
            </tbody>
          </table>
          {!c.filas.length && <div className="empty">No hay gastos con estos filtros.</div>}
        </div>
      )}
    </div>
  );
}

// --- Costo por hectárea -----------------------------------------------------------

function CostoHectarea({ f }: { f: Filtros }) {
  const query = qs(f);
  const datos = useQuery({
    queryKey: ["reporte-hectarea", query],
    queryFn: () => api<FilaCostoHectarea[]>(`/reportes/costo-hectarea${query}`),
  });
  const fmt = enMoneda(f.expresado_en);
  const filas = datos.data ?? [];
  const puntos = filas.filter((x) => x.lote_id == null && x.por_hectarea != null)
    .map((x) => ({ etiqueta: x.campo, valor: Number(x.por_hectarea) }));

  return (
    <div className="stack">
      <ErrorMsg error={datos.error} />
      {datos.isPending ? <Cargando /> : (
        <>
          {puntos.length > 0 && (
            <div className="card">
              <h3>Costo por hectárea por campo</h3>
              <BarrasRanking datos={puntos} formato={fmt} compacto={f.expresado_en === "USD" ? dolaresCompacto : pesosCompacto} />
            </div>
          )}
          <div className="card flush table-wrap">
            <table>
              <thead>
                <tr><th>Campo / lote</th><th className="num">Hectáreas</th><th className="num">Gasto</th><th className="num">Por hectárea</th></tr>
              </thead>
              <tbody>
                {filas.map((x) => (
                  <tr key={`${x.campo_id}-${x.lote_id ?? ""}`} className={x.lote_id ? "subfila" : ""}
                    style={x.lote_id ? undefined : { fontWeight: 600 }}>
                    <td>
                      <Link to={linkCatalogo(f, x.lote_id ? [["lote", x.lote_id]] : [["campo", x.campo_id]])}>
                        {x.lote ?? x.campo}
                      </Link>
                    </td>
                    <td className="num">{x.hectareas ? num(x.hectareas) : <span className="muted" title="Cargá las hectáreas en Catálogos">—</span>}</td>
                    <td className="num">{fmt(x.total)}</td>
                    <td className="num">{x.por_hectarea ? fmt(x.por_hectarea) : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {!filas.length && <div className="empty">No hay gastos imputados a campos con estos filtros.</div>}
          </div>
          <div className="muted" style={{ fontSize: 12 }}>
            La fila del campo incluye todo lo imputado al campo (tenga o no lote). Las facturas repartidas cuentan según su porcentaje.
          </div>
        </>
      )}
    </div>
  );
}

// --- IVA compras ---------------------------------------------------------------------

function Iva({ f }: { f: Filtros }) {
  const { expresado_en: _, ...resto } = f;
  const query = qs(resto);
  const datos = useQuery({ queryKey: ["reporte-iva", query], queryFn: () => api<FilaIva[]>(`/reportes/iva${query}`) });
  const filas = datos.data ?? [];
  const suma = (k: keyof FilaIva) => filas.reduce((s, x) => s + Number(x[k]), 0);
  const cols: [keyof FilaIva, string][] = [
    ["neto_gravado", "Neto gravado"], ["no_gravado", "No gravado"], ["iva", "IVA"], ["percepciones", "Percepciones"], ["total", "Total"],
  ];
  const detalle = qs({ ...resto, incluir_pendientes: undefined, estado: f.incluir_pendientes ? "" : "confirmada" });

  return (
    <div className="stack">
      <div className="row" style={{ justifyContent: "space-between" }}>
        <span className="muted">En pesos. Las notas de crédito restan. El Excel tiene el detalle comprobante por comprobante.</span>
        <BotonExcel path={`/facturas/catalogo.xlsx${detalle}`} nombre="libro_iva_compras.xlsx" deshabilitado={!filas.length} />
      </div>
      <ErrorMsg error={datos.error} />
      {datos.isPending ? <Cargando /> : (
        <div className="card flush table-wrap">
          <table>
            <thead>
              <tr><th>Período</th><th className="num">Comprobantes</th>{cols.map(([, t]) => <th key={t} className="num">{t}</th>)}</tr>
            </thead>
            <tbody>
              {filas.map((x) => (
                <tr key={x.periodo ?? "_"}>
                  <td>{x.periodo ? <Link to={linkCatalogo(f, [["mes", x.periodo]])}>{mes(x.periodo)}</Link> : "Sin fecha"}</td>
                  <td className="num">{x.cantidad}</td>
                  {cols.map(([k]) => <td key={k} className="num">{pesos(x[k] as string)}</td>)}
                </tr>
              ))}
              {filas.length > 0 && (
                <tr style={{ fontWeight: 600 }}>
                  <td>Total</td>
                  <td className="num">{filas.reduce((s, x) => s + x.cantidad, 0)}</td>
                  {cols.map(([k]) => <td key={k} className="num">{pesos(suma(k))}</td>)}
                </tr>
              )}
            </tbody>
          </table>
          {!filas.length && <div className="empty">No hay comprobantes con estos filtros.</div>}
        </div>
      )}
    </div>
  );
}

// --- Insumos -----------------------------------------------------------------------------

function Insumos({ f }: { f: Filtros }) {
  const { expresado_en: _, ...resto } = f;
  const query = qs(resto);
  const datos = useQuery({ queryKey: ["reporte-insumos", query], queryFn: () => api<ResumenInsumo[]>(`/reportes/insumos${query}`) });
  const [elegido, setElegido] = useState<ResumenInsumo | null>(null);
  const filas = datos.data ?? [];

  return (
    <div className="stack">
      <ErrorMsg error={datos.error} />
      {datos.isPending ? <Cargando /> : (
        <div className="card flush table-wrap">
          <table>
            <thead>
              <tr>
                <th>Insumo</th><th className="num">Cantidad</th><th className="num">Gasto</th>
                <th className="num">Precio promedio</th><th className="num">Último precio</th><th>Última compra</th>
              </tr>
            </thead>
            <tbody>
              {filas.map((x) => (
                <tr key={x.insumo_id} className="clickable" onClick={() => setElegido(x)}
                  aria-selected={elegido?.insumo_id === x.insumo_id}>
                  <td>{x.insumo}</td>
                  <td className="num">{x.cantidad ? `${num(x.cantidad)} ${x.unidad ?? ""}` : "—"}</td>
                  <td className="num">{pesos(x.total_pesos)}</td>
                  <td className="num">{pesos(x.precio_promedio)}</td>
                  <td className="num">{pesos(x.ultimo_precio)}</td>
                  <td>{fecha(x.ultima_compra)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {!filas.length && (
            <div className="empty">
              No hay ítems asignados a insumos. Asignalos en <Link to="/catalogos?tab=insumos">Catálogos → Insumos</Link>.
            </div>
          )}
        </div>
      )}
      {elegido && <HistorialPrecios insumo={elegido} query={query} />}
    </div>
  );
}

function HistorialPrecios({ insumo, query }: { insumo: ResumenInsumo; query: string }) {
  const datos = useQuery({
    queryKey: ["precios-insumo", insumo.insumo_id, query],
    queryFn: () => api<PrecioInsumo[]>(`/reportes/insumos/${insumo.insumo_id}/precios${query}`),
  });
  const conPrecio = (datos.data ?? []).filter((p) => p.precio_pesos != null && p.fecha);
  return (
    <div className="card stack">
      <h3 style={{ margin: 0 }}>Precio de {insumo.insumo} (en pesos, por unidad)</h3>
      {datos.isPending ? <Cargando /> : (
        <>
          <LineaPrecios datos={conPrecio.map((p) => ({ etiqueta: fecha(p.fecha), valor: Number(p.precio_pesos) }))} />
          <div className="table-wrap">
            <table>
              <thead><tr><th>Fecha</th><th>Proveedor</th><th>Descripción</th><th className="num">Cantidad</th><th className="num">Precio</th></tr></thead>
              <tbody>
                {datos.data?.map((p, i) => (
                  <tr key={i}>
                    <td><Link to={`/facturas/${p.factura_id}`}>{fecha(p.fecha)}</Link></td>
                    <td>{p.proveedor ?? "—"}</td>
                    <td>{p.descripcion}</td>
                    <td className="num">{p.cantidad ? `${num(p.cantidad)} ${p.unidad ?? ""}` : "—"}</td>
                    <td className="num">{pesos(p.precio_pesos)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}
