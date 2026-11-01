import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../api";
import { useAuth } from "../auth";
import { ErrorMsg, Field, Modal } from "../components/ui";
import type { Rol, Usuario } from "../types";

export default function Usuarios() {
  const { usuario: yo } = useAuth();
  const usuarios = useQuery({ queryKey: ["usuarios"], queryFn: () => api<Usuario[]>("/usuarios") });
  const roles = useQuery({ queryKey: ["roles"], queryFn: () => api<Rol[]>("/roles") });
  const permisos = useQuery({ queryKey: ["permisos"], queryFn: () => api<Record<string, string>>("/permisos") });
  const [editando, setEditando] = useState<Usuario | "nuevo" | null>(null);

  return (
    <div className="stack">
      <div className="page-head">
        <h1>Usuarios</h1>
        <button className="primary" onClick={() => setEditando("nuevo")}>+ Usuario</button>
      </div>
      <ErrorMsg error={usuarios.error} />
      <div className="card flush table-wrap">
        <table>
          <thead><tr><th>Nombre</th><th>Email</th><th>Roles</th><th>Estado</th></tr></thead>
          <tbody>
            {usuarios.data?.map((u) => (
              <tr key={u.id} className="clickable" onClick={() => setEditando(u)}>
                <td>{u.nombre}{u.id === yo?.id && <span className="muted"> (vos)</span>}</td>
                <td>{u.email}</td>
                <td>{u.roles.join(", ") || <span className="muted">sin rol</span>}</td>
                <td>{u.activo ? <span className="badge good">✓ Activo</span> : <span className="badge muted">– Inactivo</span>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="card">
        <h2>Roles</h2>
        <div className="stack" style={{ gap: 10 }}>
          {roles.data?.map((r) => (
            <div key={r.id}>
              <strong>{r.nombre}</strong> <span className="muted">— {r.descripcion}</span>
              <div className="muted" style={{ fontSize: 12 }}>
                {r.permisos.map((p) => permisos.data?.[p] ?? p).join(" · ")}
              </div>
            </div>
          ))}
        </div>
      </div>

      {editando && roles.data && (
        <FormUsuario u={editando === "nuevo" ? null : editando} roles={roles.data} esYo={editando !== "nuevo" && editando.id === yo?.id}
          onClose={() => setEditando(null)} />
      )}
    </div>
  );
}

function FormUsuario({ u, roles, esYo, onClose }: { u: Usuario | null; roles: Rol[]; esYo: boolean; onClose: () => void }) {
  const qc = useQueryClient();
  const [f, setF] = useState({ nombre: u?.nombre ?? "", email: u?.email ?? "", password: "", activo: u?.activo ?? true });
  const [sel, setSel] = useState<string[]>(u?.roles ?? []);

  const guardar = useMutation({
    mutationFn: () => {
      if (!u) return api("/usuarios", { method: "POST", json: { ...f, roles: sel } });
      const json: Record<string, unknown> = { nombre: f.nombre, activo: f.activo, roles: sel };
      if (f.password) json.password = f.password;
      return api(`/usuarios/${u.id}`, { method: "PATCH", json });
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["usuarios"] });
      if (esYo) qc.invalidateQueries({ queryKey: ["yo"] });
      onClose();
    },
  });
  const toggle = (r: string) => setSel((s) => (s.includes(r) ? s.filter((x) => x !== r) : [...s, r]));

  return (
    <Modal titulo={u ? `Editar ${u.nombre}` : "Nuevo usuario"} onClose={onClose}>
      <form onSubmit={(e) => { e.preventDefault(); guardar.mutate(); }}>
        <ErrorMsg error={guardar.error} />
        <div className="form-grid" style={{ marginTop: 8 }}>
          <Field label="Nombre"><input required value={f.nombre} onChange={(e) => setF({ ...f, nombre: e.target.value })} /></Field>
          <Field label="Email"><input type="email" required disabled={!!u} value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} /></Field>
          <Field label={u ? "Nueva contraseña (opcional)" : "Contraseña"}>
            <input type="password" autoComplete="new-password" minLength={8} required={!u} value={f.password}
              onChange={(e) => setF({ ...f, password: e.target.value })} />
          </Field>
        </div>
        <h3 style={{ marginTop: 16 }}>Roles</h3>
        <div className="stack" style={{ gap: 6 }}>
          {roles.map((r) => (
            <label key={r.id} className="row" style={{ gap: 8 }}>
              <input type="checkbox" checked={sel.includes(r.nombre)} onChange={() => toggle(r.nombre)}
                disabled={esYo && r.nombre === "admin"} />
              <span><strong>{r.nombre}</strong> <span className="muted">— {r.descripcion}</span></span>
            </label>
          ))}
        </div>
        {u && !esYo && (
          <label className="row" style={{ gap: 8, marginTop: 16 }}>
            <input type="checkbox" checked={f.activo} onChange={(e) => setF({ ...f, activo: e.target.checked })} />
            Usuario activo (desmarcar para bloquear el acceso)
          </label>
        )}
        <div className="modal-actions">
          <button type="button" onClick={onClose}>Cancelar</button>
          <button className="primary" disabled={guardar.isPending}>Guardar</button>
        </div>
      </form>
    </Modal>
  );
}
