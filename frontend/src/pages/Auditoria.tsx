import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, qs } from "../api";
import { useAuth } from "../auth";
import { ACCIONES, DetalleAuditoria, fechaHora, LinkEntidad } from "../components/Auditoria";
import { Cargando, ErrorMsg, Field } from "../components/ui";
import type { EntradaAuditoria, Usuario } from "../types";

const POR_PAGINA = 100;

export default function Auditoria() {
  const { puede } = useAuth();
  const [f, setF] = useState({ accion: "", entidad: "", usuario_id: "", desde: "", hasta: "" });
  const [pagina, setPagina] = useState(1);
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => { setF({ ...f, [k]: e.target.value }); setPagina(1); };
  const query = qs({ ...f, limit: POR_PAGINA, offset: (pagina - 1) * POR_PAGINA });
  const datos = useQuery({
    queryKey: ["auditoria", query],
    queryFn: () => api<{ items: EntradaAuditoria[]; total: number }>(`/auditoria${query}`),
    placeholderData: (p) => p,
  });
  const acciones = useQuery({ queryKey: ["auditoria-acciones"], queryFn: () => api<string[]>("/auditoria/acciones") });
  const usuarios = useQuery({
    queryKey: ["usuarios"], queryFn: () => api<Usuario[]>("/usuarios"), enabled: puede("usuarios:admin"),
  });
  const paginas = Math.max(1, Math.ceil((datos.data?.total ?? 0) / POR_PAGINA));

  return (
    <div className="stack">
      <div className="page-head"><h1>Auditoría</h1></div>
      <div className="row">
        <Field label="Acción">
          <select value={f.accion} onChange={set("accion")}>
            <option value="">Todas</option>
            {acciones.data?.map((a) => <option key={a} value={a}>{ACCIONES[a] ?? a}</option>)}
          </select>
        </Field>
        <Field label="Sobre">
          <select value={f.entidad} onChange={set("entidad")}>
            <option value="">Todo</option>
            <option value="factura">Facturas</option>
            <option value="usuario">Usuarios</option>
            <option value="rol">Roles</option>
            <option value="proveedores">Proveedores</option>
            <option value="campos">Campos</option>
          </select>
        </Field>
        {puede("usuarios:admin") && (
          <Field label="Usuario">
            <select value={f.usuario_id} onChange={set("usuario_id")}>
              <option value="">Todos</option>
              {usuarios.data?.map((u) => <option key={u.id} value={u.id}>{u.nombre}</option>)}
            </select>
          </Field>
        )}
        <Field label="Desde"><input type="date" value={f.desde} onChange={set("desde")} /></Field>
        <Field label="Hasta"><input type="date" value={f.hasta} onChange={set("hasta")} /></Field>
      </div>
      <ErrorMsg error={datos.error} />
      {datos.isPending ? <Cargando /> : (
        <div className="card flush table-wrap">
          <table>
            <thead><tr><th>Fecha</th><th>Usuario</th><th>Acción</th><th>Sobre</th><th>Detalle</th><th>IP</th></tr></thead>
            <tbody>
              {datos.data?.items.map((e) => (
                <tr key={e.id}>
                  <td style={{ whiteSpace: "nowrap" }}>{fechaHora(e.fecha)}</td>
                  <td>{e.usuario ?? <span className="muted">Sistema</span>}</td>
                  <td>{ACCIONES[e.accion] ?? e.accion}</td>
                  <td><LinkEntidad e={e} /></td>
                  <td><DetalleAuditoria e={e} /></td>
                  <td className="muted">{e.ip ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {!datos.data?.items.length && <div className="empty">Sin registros con estos filtros.</div>}
        </div>
      )}
      {paginas > 1 && (
        <div className="row" style={{ justifyContent: "center" }}>
          <button className="small" disabled={pagina <= 1} onClick={() => setPagina(pagina - 1)}>← Anterior</button>
          <span className="muted">Página {pagina} de {paginas}</span>
          <button className="small" disabled={pagina >= paginas} onClick={() => setPagina(pagina + 1)}>Siguiente →</button>
        </div>
      )}
    </div>
  );
}
