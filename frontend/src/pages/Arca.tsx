import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { api, qs } from "../api";
import { useAuth } from "../auth";
import { Cargando, ErrorMsg, Field } from "../components/ui";
import { comprobante, cuit, fecha, monto } from "../format";
import type { Conciliacion } from "../types";

export default function Arca() {
  const { puede } = useAuth();
  const qc = useQueryClient();
  const input = useRef<HTMLInputElement>(null);
  const [rango, setRango] = useState({ desde: "", hasta: "" });
  const datos = useQuery({
    queryKey: ["conciliacion", rango],
    queryFn: () => api<Conciliacion>(`/arca/conciliacion${qs(rango)}`),
  });
  const subir = useMutation({
    mutationFn: (archivo: File) => {
      const fd = new FormData();
      fd.append("archivo", archivo);
      return api<{ leidos: number; nuevos: number; desde: string; hasta: string }>("/arca/comprobantes-recibidos", { method: "POST", body: fd });
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["conciliacion"] }),
  });
  const c = datos.data;

  return (
    <div className="stack">
      <div className="page-head">
        <h1>Conciliación con ARCA</h1>
        {puede("facturas:escribir") && (
          <>
            <button className="primary" onClick={() => input.current?.click()} disabled={subir.isPending}>
              {subir.isPending ? "Subiendo…" : "⬆ Subir Mis Comprobantes"}
            </button>
            <input ref={input} type="file" accept=".csv,.xlsx,.txt" hidden
              onChange={(e) => { if (e.target.files?.[0]) subir.mutate(e.target.files[0]); e.target.value = ""; }} />
          </>
        )}
      </div>
      <div className="muted" style={{ fontSize: 13 }}>
        En ARCA entrá a <strong>Mis Comprobantes → Recibidos</strong>, elegí el período y descargá el archivo (CSV o Excel).
        Al subirlo se compara con las facturas cargadas acá. Se puede subir varias veces.
      </div>
      <ErrorMsg error={subir.error ?? datos.error} />
      {subir.data && (
        <div className="alert good">
          Se leyeron {subir.data.leidos} comprobantes ({subir.data.nuevos} nuevos) del {fecha(subir.data.desde)} al {fecha(subir.data.hasta)}.
        </div>
      )}
      <div className="row">
        <Field label="Desde"><input type="date" value={rango.desde} onChange={(e) => setRango({ ...rango, desde: e.target.value })} /></Field>
        <Field label="Hasta"><input type="date" value={rango.hasta} onChange={(e) => setRango({ ...rango, hasta: e.target.value })} /></Field>
      </div>
      {!c ? <Cargando /> : !c.desde ? (
        <div className="card empty">Todavía no se subió ningún archivo de ARCA.</div>
      ) : (
        <>
          <div className="kpis">
            <div className="card"><div className="kpi-label">Coinciden</div><div className="kpi-value">{c.coinciden}</div>
              <div className="kpi-sub">del {fecha(c.desde)} al {fecha(c.hasta)}</div></div>
            <div className="card"><div className="kpi-label">Faltan cargar</div>
              <div className="kpi-value" style={{ color: c.faltan_cargar.length ? "var(--warning-text)" : undefined }}>{c.faltan_cargar.length}</div>
              <div className="kpi-sub">están en ARCA y no en el sistema</div></div>
            <div className="card"><div className="kpi-label">No están en ARCA</div>
              <div className="kpi-value" style={{ color: c.no_estan_en_arca.length ? "var(--critical-text)" : undefined }}>{c.no_estan_en_arca.length}</div>
              <div className="kpi-sub">revisar: podrían ser apócrifas o de otro receptor</div></div>
            <div className="card"><div className="kpi-label">Con diferencias</div><div className="kpi-value">{c.diferencias.length}</div>
              <div className="kpi-sub">mismo comprobante, otro total</div></div>
          </div>

          <Seccion titulo="Faltan cargar" vacio="Todo lo que figura en ARCA está cargado.">
            {c.faltan_cargar.length > 0 && (
              <table>
                <thead><tr><th>Fecha</th><th>Emisor</th><th>Comprobante</th><th className="num">Total</th></tr></thead>
                <tbody>
                  {c.faltan_cargar.map((x) => (
                    <tr key={x.id}>
                      <td>{fecha(x.fecha)}</td>
                      <td>{x.razon_social ?? cuit(x.cuit_emisor)}</td>
                      <td>{comprobante(x)}</td>
                      <td className="num">{monto(x.total, x.moneda)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </Seccion>
          <Seccion titulo="Confirmadas que ARCA no tiene" vacio="Todas las facturas confirmadas del período figuran en ARCA.">
            {c.no_estan_en_arca.length > 0 && (
              <table>
                <thead><tr><th>Fecha</th><th>Proveedor</th><th>Comprobante</th><th className="num">Total</th></tr></thead>
                <tbody>
                  {c.no_estan_en_arca.map((f) => (
                    <tr key={f.id}>
                      <td>{fecha(f.fecha_emision)}</td>
                      <td>{f.proveedor?.razon_social ?? cuit(f.cuit_emisor)}</td>
                      <td><Link to={`/facturas/${f.id}`}>{comprobante(f)}</Link></td>
                      <td className="num">{monto(f.total, f.moneda)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </Seccion>
          <Seccion titulo="Diferencias de importe" vacio="Los importes coinciden.">
            {c.diferencias.length > 0 && (
              <table>
                <thead><tr><th>Comprobante</th><th className="num">Según ARCA</th><th className="num">Cargado</th></tr></thead>
                <tbody>
                  {c.diferencias.map((d) => (
                    <tr key={d.factura_id}>
                      <td><Link to={`/facturas/${d.factura_id}`}>{d.arca.razon_social} · {comprobante(d.arca)}</Link></td>
                      <td className="num">{monto(d.arca.total, d.arca.moneda)}</td>
                      <td className="num">{monto(d.total_cargado, d.arca.moneda)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </Seccion>
        </>
      )}
    </div>
  );
}

function Seccion({ titulo, vacio, children }: { titulo: string; vacio: string; children: ReactNode }) {
  return (
    <div className="card flush table-wrap">
      <div style={{ padding: "14px 16px 4px" }}><h3>{titulo}</h3></div>
      {children || <div className="empty" style={{ padding: 16 }}>{vacio}</div>}
    </div>
  );
}
