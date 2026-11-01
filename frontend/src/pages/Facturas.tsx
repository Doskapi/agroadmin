import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState, type DragEvent } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { api, qs } from "../api";
import { useAuth } from "../auth";
import { BadgeFactura, ErrorMsg, Field } from "../components/ui";
import { comprobante, cuit, fecha, monto } from "../format";
import { useProveedores } from "../hooks";
import type { EstadoFactura, Factura, FacturaResumen } from "../types";

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

export default function Facturas() {
  const { puede } = useAuth();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [params, setParams] = useSearchParams();
  const estado = params.get("estado") ?? "";
  const proveedor_id = params.get("proveedor_id") ?? "";
  const desde = params.get("desde") ?? "";
  const hasta = params.get("hasta") ?? "";
  const [limite, setLimite] = useState(POR_PAGINA);
  const proveedores = useProveedores();

  const setFiltro = (k: string, v: string) => {
    const p = new URLSearchParams(params);
    if (v) p.set(k, v);
    else p.delete(k);
    setParams(p, { replace: true });
    setLimite(POR_PAGINA);
  };

  const filtros = { estado, proveedor_id, desde, hasta };
  const lista = useQuery({
    queryKey: ["facturas", filtros, limite],
    // pedimos una de más para saber si hay otra página
    queryFn: () => api<FacturaResumen[]>(`/facturas${qs({ ...filtros, limit: limite + 1 })}`),
    // mientras haya facturas procesándose, refrescamos solo
    refetchInterval: (q) => (q.state.data?.some((f) => f.estado === "procesando") ? 2500 : false),
  });
  const filas = lista.data?.slice(0, limite) ?? [];
  const hayMas = (lista.data?.length ?? 0) > limite;

  const crearManual = useMutation({
    mutationFn: () => api<Factura>("/facturas", { method: "POST", json: {} }),
    onSuccess: (f) => navigate(`/facturas/${f.id}`),
  });

  return (
    <div className="stack">
      <div className="page-head">
        <h1>Facturas</h1>
        {puede("facturas:escribir") && (
          <button onClick={() => crearManual.mutate()} disabled={crearManual.isPending}>+ Carga manual</button>
        )}
      </div>

      {puede("facturas:escribir") && (
        <Importador onImportado={() => qc.invalidateQueries({ queryKey: ["facturas"] })} />
      )}

      <div>
        <div className="tabs" role="tablist">
          {TABS.map((t) => (
            <button key={t.valor} role="tab" aria-selected={estado === t.valor}
              className={estado === t.valor ? "active" : ""} onClick={() => setFiltro("estado", t.valor)}>
              {t.texto}
            </button>
          ))}
        </div>
        <div className="row" style={{ marginBottom: 12 }}>
          <Field label="Proveedor">
            <select value={proveedor_id} onChange={(e) => setFiltro("proveedor_id", e.target.value)}>
              <option value="">Todos</option>
              {proveedores.data?.map((p) => <option key={p.id} value={p.id}>{p.razon_social}</option>)}
            </select>
          </Field>
          <Field label="Desde"><input type="date" value={desde} onChange={(e) => setFiltro("desde", e.target.value)} /></Field>
          <Field label="Hasta"><input type="date" value={hasta} onChange={(e) => setFiltro("hasta", e.target.value)} /></Field>
        </div>

        <ErrorMsg error={lista.error} />
        <div className="card flush table-wrap">
          <table>
            <thead>
              <tr>
                <th>Fecha</th><th>Proveedor</th><th>Comprobante</th><th className="num">Total</th><th>Estado</th>
              </tr>
            </thead>
            <tbody>
              {filas.map((f) => (
                <tr key={f.id} className="clickable" onClick={() => navigate(`/facturas/${f.id}`)}>
                  <td>{fecha(f.fecha_emision)}</td>
                  <td>
                    {f.proveedor?.razon_social ?? <span className="muted">{f.cuit_emisor ? cuit(f.cuit_emisor) : "—"}</span>}
                  </td>
                  <td>{comprobante(f)}</td>
                  <td className="num">{monto(f.total, f.moneda)}</td>
                  <td><BadgeFactura estado={f.estado} /></td>
                </tr>
              ))}
            </tbody>
          </table>
          {lista.isPending && <div className="empty"><span className="spinner" /></div>}
          {lista.isSuccess && filas.length === 0 && <div className="empty">No hay facturas con estos filtros.</div>}
        </div>
        {hayMas && (
          <div style={{ textAlign: "center", marginTop: 12 }}>
            <button onClick={() => setLimite((l) => l + POR_PAGINA)}>Ver más</button>
          </div>
        )}
      </div>
    </div>
  );
}

function Importador({ onImportado }: { onImportado: () => void }) {
  const input = useRef<HTMLInputElement>(null);
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
      {errores.length > 0 && (
        <div className="alert critical">
          No se pudieron importar:
          <ul>{errores.map((e) => <li key={e}>{e}</li>)}</ul>
        </div>
      )}
    </div>
  );
}
