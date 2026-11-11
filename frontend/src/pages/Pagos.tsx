import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { api, qs } from "../api";
import { useAuth } from "../auth";
import { ModalPago } from "../components/Pagos";
import { Cargando, ErrorMsg, Field } from "../components/ui";
import { fecha, monto, pesos } from "../format";
import { useProveedores } from "../hooks";
import type { CuentasAPagar, FacturaAPagar } from "../types";

function Vence({ dias }: { dias: number | null }) {
  if (dias == null) return <span className="muted">—</span>;
  if (dias < 0) return <span className="badge critical">Vencida hace {-dias} d</span>;
  if (dias === 0) return <span className="badge warning">Vence hoy</span>;
  if (dias <= 7) return <span className="badge warning">En {dias} d</span>;
  return <span className="muted">En {dias} d</span>;
}

export default function Pagos() {
  const { puede } = useAuth();
  const qc = useQueryClient();
  const [f, setF] = useState({ proveedor_id: "", hasta: "" });
  const proveedores = useProveedores();
  const datos = useQuery({
    queryKey: ["pagos-pendientes", f],
    queryFn: () => api<CuentasAPagar>(`/pagos/pendientes${qs(f)}`),
  });
  const [pagando, setPagando] = useState<FacturaAPagar | null>(null);
  const d = datos.data;

  return (
    <div className="stack">
      <div className="page-head"><h1>Cuentas a pagar</h1></div>
      <div className="row">
        <Field label="Proveedor">
          <select value={f.proveedor_id} onChange={(e) => setF({ ...f, proveedor_id: e.target.value })}>
            <option value="">Todos</option>
            {proveedores.data?.map((p) => <option key={p.id} value={p.id}>{p.razon_social}</option>)}
          </select>
        </Field>
        <Field label="Que venzan hasta"><input type="date" value={f.hasta} onChange={(e) => setF({ ...f, hasta: e.target.value })} /></Field>
      </div>
      <ErrorMsg error={datos.error} />
      {!d ? <Cargando /> : (
        <>
          <div className="kpis">
            <div className="card">
              <div className="kpi-label">Vencido</div>
              <div className="kpi-value" style={{ color: Number(d.vencido_pesos) ? "var(--critical-text)" : undefined }}>
                {pesos(d.vencido_pesos)}
              </div>
            </div>
            <div className="card">
              <div className="kpi-label">Vence en los próximos 7 días</div>
              <div className="kpi-value">{pesos(d.proximos_7_dias_pesos)}</div>
            </div>
            <div className="card">
              <div className="kpi-label">Total adeudado</div>
              <div className="kpi-value">{pesos(d.total_pesos)}</div>
              <div className="kpi-sub">{d.facturas.length} factura{d.facturas.length === 1 ? "" : "s"} (en pesos con la cotización de cada una)</div>
            </div>
          </div>
          <div className="card flush table-wrap">
            <table>
              <thead>
                <tr><th>Vencimiento</th><th /><th>Proveedor</th><th>Comprobante</th><th className="num">Total</th>
                  <th className="num">Saldo</th>{puede("pagos:escribir") && <th />}</tr>
              </thead>
              <tbody>
                {d.facturas.map((x) => (
                  <tr key={x.id}>
                    <td>{fecha(x.vencimiento)}</td>
                    <td><Vence dias={x.dias} /></td>
                    <td>{x.proveedor ?? "—"}</td>
                    <td><Link to={`/facturas/${x.id}`}>{x.comprobante}</Link></td>
                    <td className="num">{monto(x.total, x.moneda)}</td>
                    <td className="num" style={{ fontWeight: 600 }}>{monto(x.saldo, x.moneda)}</td>
                    {puede("pagos:escribir") && (
                      <td><button className="small" onClick={() => setPagando(x)}>Registrar pago</button></td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
            {!d.facturas.length && <div className="empty">No hay facturas confirmadas con saldo pendiente.</div>}
          </div>
          <div className="muted" style={{ fontSize: 12 }}>
            Si la factura no tiene fecha de vencimiento se toma la de emisión. Las notas de crédito no figuran.
          </div>
        </>
      )}
      {pagando && (
        <ModalPago facturaId={pagando.id} saldo={pagando.saldo} moneda={pagando.moneda} onClose={() => setPagando(null)}
          onListo={() => { setPagando(null); qc.invalidateQueries({ queryKey: ["pagos-pendientes"] }); }} />
      )}
    </div>
  );
}
