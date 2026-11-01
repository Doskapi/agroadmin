import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, descargar, qs } from "../api";
import { BarrasRanking, BarrasTiempo } from "../components/Charts";
import { Cargando, ErrorMsg, Field } from "../components/ui";
import { capitalizar, mes, pesos } from "../format";
import { useCampanias, useCampos } from "../hooks";
import type { FilaReporte } from "../types";

const AGRUPAR = { mes: "Mes", categoria: "Rubro", proveedor: "Proveedor", campo: "Campo", campania: "Campaña" } as const;
type Agrupar = keyof typeof AGRUPAR;

export default function Reportes() {
  const campanias = useCampanias();
  const campos = useCampos();
  const [f, setF] = useState({
    agrupar: "categoria" as Agrupar, desde: "", hasta: "", campania_id: "", campo_id: "", incluir_pendientes: false,
  });
  const query = qs(f);
  const datos = useQuery({ queryKey: ["reporte-gastos", f], queryFn: () => api<FilaReporte[]>(`/reportes/gastos${query}`) });
  const [descargando, setDescargando] = useState(false);

  const etiqueta = (c: string | null) =>
    f.agrupar === "mes" ? mes(c) : c ? (f.agrupar === "categoria" ? capitalizar(c) : c) : "(sin asignar)";
  const filas = datos.data ?? [];
  const total = filas.reduce((s, x) => s + Number(x.total), 0);
  const puntos = filas.map((x) => ({ etiqueta: etiqueta(x.clave), valor: Number(x.total), cantidad: x.cantidad }));
  const set = (k: string) => (e: { target: { value: string } }) => setF((p) => ({ ...p, [k]: e.target.value }));

  async function excel() {
    setDescargando(true);
    try {
      await descargar(`/reportes/gastos.xlsx${query}`, `gastos_por_${f.agrupar}.xlsx`);
    } finally {
      setDescargando(false);
    }
  }

  return (
    <div className="stack">
      <div className="page-head">
        <h1>Reportes de gastos</h1>
        <button onClick={excel} disabled={descargando || !filas.length}>
          {descargando ? "Generando…" : "⬇ Descargar Excel"}
        </button>
      </div>

      <div className="row">
        <Field label="Agrupar por">
          <select value={f.agrupar} onChange={set("agrupar")}>
            {Object.entries(AGRUPAR).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
        </Field>
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
        <label className="row" style={{ alignSelf: "end", paddingBottom: 8, fontSize: 13 }}>
          <input type="checkbox" checked={f.incluir_pendientes}
            onChange={(e) => setF((p) => ({ ...p, incluir_pendientes: e.target.checked }))} />
          Incluir facturas sin confirmar
        </label>
      </div>

      <ErrorMsg error={datos.error} />
      {datos.isPending ? <Cargando /> : (
        <>
          <div className="card">
            {f.agrupar === "mes" ? <BarrasTiempo datos={puntos} /> : <BarrasRanking datos={puntos.slice(0, 15)} />}
            {f.agrupar !== "mes" && filas.length > 15 && (
              <div className="muted" style={{ fontSize: 12 }}>El gráfico muestra los 15 mayores; la tabla tiene todos.</div>
            )}
          </div>
          <div className="card flush table-wrap">
            <table>
              <thead>
                <tr><th>{AGRUPAR[f.agrupar]}</th><th className="num">Comprobantes</th><th className="num">Total</th><th className="num">%</th></tr>
              </thead>
              <tbody>
                {filas.map((x) => (
                  <tr key={x.clave ?? "_"}>
                    <td>{etiqueta(x.clave)}</td>
                    <td className="num">{x.cantidad}</td>
                    <td className="num">{pesos(x.total)}</td>
                    <td className="num muted">{total ? ((Number(x.total) / total) * 100).toFixed(1) : 0}%</td>
                  </tr>
                ))}
                {filas.length > 0 && (
                  <tr style={{ fontWeight: 600 }}>
                    <td>Total</td>
                    <td className="num">{filas.reduce((s, x) => s + x.cantidad, 0)}</td>
                    <td className="num">{pesos(total)}</td>
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
