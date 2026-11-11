import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { api, qs } from "../api";
import { BarrasRanking, BarrasTiempo } from "../components/Charts";
import { Cargando, ErrorMsg, Field } from "../components/ui";
import { capitalizar, mes, num, pesos } from "../format";
import { useCampanias } from "../hooks";
import { useAuth } from "../auth";
import type { CuentasAPagar, FilaReporte, Resumen } from "../types";

const aPuntos = (filas: FilaReporte[], etiqueta: (c: string | null) => string) =>
  filas.map((f) => ({ etiqueta: etiqueta(f.clave), valor: Number(f.total), cantidad: f.cantidad }));

export default function Dashboard() {
  const campanias = useCampanias();
  const [filtros, setFiltros] = useState({ campania_id: "", desde: "", hasta: "" });
  const resumen = useQuery({
    queryKey: ["resumen", filtros],
    queryFn: () => api<Resumen>(`/reportes/resumen${qs(filtros)}`),
  });
  const r = resumen.data;
  const { puede } = useAuth();
  const aPagar = useQuery({
    queryKey: ["pagos-pendientes", {}],
    queryFn: () => api<CuentasAPagar>("/pagos/pendientes"),
    enabled: puede("facturas:leer"),
  });
  const set = (k: keyof typeof filtros) => (e: { target: { value: string } }) =>
    setFiltros((f) => ({ ...f, [k]: e.target.value }));

  return (
    <div className="stack">
      <div className="page-head">
        <h1>Dashboard</h1>
        <div className="row">
          <Field label="Campaña">
            <select value={filtros.campania_id} onChange={set("campania_id")}>
              <option value="">Todas</option>
              {campanias.data?.map((c) => <option key={c.id} value={c.id}>{c.nombre}</option>)}
            </select>
          </Field>
          <Field label="Desde"><input type="date" value={filtros.desde} onChange={set("desde")} /></Field>
          <Field label="Hasta"><input type="date" value={filtros.hasta} onChange={set("hasta")} /></Field>
        </div>
      </div>

      <ErrorMsg error={resumen.error} />
      {!r ? <Cargando /> : (
        <>
          <div className="kpis">
            <div className="card">
              <div className="kpi-label">Gastos confirmados</div>
              <div className="kpi-value">{pesos(r.total_gastos)}</div>
              <div className="kpi-sub">{r.cantidad_facturas} comprobantes</div>
            </div>
            <div className="card">
              <div className="kpi-label">Facturas a revisar</div>
              <div className="kpi-value">{r.pendientes_revision}</div>
              <div className="kpi-sub">
                {r.pendientes_revision > 0
                  ? <Link to="/facturas?estado=pendiente_revision">Revisar ahora →</Link>
                  : "Todo al día"}
              </div>
            </div>
            {aPagar.data && (
              <div className="card">
                <div className="kpi-label">A pagar</div>
                <div className="kpi-value" style={{ color: Number(aPagar.data.vencido_pesos) ? "var(--critical-text)" : undefined }}>
                  {pesos(aPagar.data.total_pesos)}
                </div>
                <div className="kpi-sub">
                  {Number(aPagar.data.vencido_pesos) > 0 ? `${pesos(aPagar.data.vencido_pesos)} vencido · ` : ""}
                  {pesos(aPagar.data.proximos_7_dias_pesos)} en 7 días · <Link to="/pagos">Ver →</Link>
                </div>
              </div>
            )}
            <div className="card">
              <div className="kpi-label">Kilos despachados</div>
              <div className="kpi-value">{num(r.kilos_despachados)}</div>
              <div className="kpi-sub">{num(Number(r.kilos_despachados) / 1000)} toneladas</div>
            </div>
          </div>

          <div className="card">
            <h2>Gastos por mes</h2>
            <BarrasTiempo datos={aPuntos(r.gastos_por_mes, mes)} />
          </div>

          <div className="grid-2">
            <div className="card">
              <h2>Por rubro</h2>
              <BarrasRanking datos={aPuntos(r.gastos_por_categoria, (c) => (c ? capitalizar(c) : "Sin categoría"))} />
            </div>
            <div className="card">
              <h2>Principales proveedores</h2>
              <BarrasRanking datos={aPuntos(r.top_proveedores, (c) => c ?? "Sin proveedor")} />
            </div>
          </div>
          <div className="muted" style={{ fontSize: 12 }}>
            Solo facturas confirmadas, en pesos (las de dólares se convierten con su cotización; las notas de crédito restan).
            El detalle en tabla y la exportación a Excel están en <Link to="/reportes">Reportes</Link>.
          </div>
        </>
      )}
    </div>
  );
}
