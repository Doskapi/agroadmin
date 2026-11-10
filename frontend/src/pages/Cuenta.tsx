import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { api } from "../api";
import { useAuth } from "../auth";
import { Cargando, ErrorMsg, Field } from "../components/ui";
import type { SesionInfo } from "../types";

const fechaHora = (v: string) => new Date(v).toLocaleString("es-AR", { dateStyle: "short", timeStyle: "short" });

function navegador(ua: string | null) {
  if (!ua) return "Desconocido";
  const so = /Windows/.test(ua) ? "Windows" : /iPhone|iPad/.test(ua) ? "iPhone/iPad" : /Android/.test(ua) ? "Android"
    : /Mac OS/.test(ua) ? "Mac" : /Linux/.test(ua) ? "Linux" : "";
  const nav = /Edg\//.test(ua) ? "Edge" : /Chrome\//.test(ua) ? "Chrome" : /Firefox\//.test(ua) ? "Firefox"
    : /Safari\//.test(ua) ? "Safari" : "Navegador";
  return so ? `${nav} en ${so}` : nav;
}

export default function Cuenta() {
  const { usuario } = useAuth();
  return (
    <div className="stack">
      <div className="page-head"><h1>Mi cuenta</h1></div>
      <div className="muted">{usuario?.nombre} · {usuario?.email}</div>
      <div className="grid-2" style={{ alignItems: "start" }}>
        <CambiarPassword />
        <DosPasos />
      </div>
      <Sesiones />
    </div>
  );
}

function CambiarPassword() {
  const [f, setF] = useState({ actual: "", nueva: "", repetir: "" });
  const [ok, setOk] = useState(false);
  const m = useMutation({
    mutationFn: () => api("/auth/cambiar-password", { method: "POST", json: { actual: f.actual, nueva: f.nueva } }),
    onSuccess: () => { setOk(true); setF({ actual: "", nueva: "", repetir: "" }); },
  });
  const noCoinciden = f.repetir !== "" && f.nueva !== f.repetir;
  return (
    <form className="card stack" onSubmit={(e: FormEvent) => { e.preventDefault(); setOk(false); m.mutate(); }}>
      <h2 style={{ margin: 0 }}>Contraseña</h2>
      <ErrorMsg error={m.error} />
      {ok && <div className="alert good">Contraseña cambiada. Se cerraron tus otras sesiones.</div>}
      <Field label="Actual"><input type="password" autoComplete="current-password" required value={f.actual} onChange={(e) => setF({ ...f, actual: e.target.value })} /></Field>
      <Field label="Nueva (10 caracteres o más)"><input type="password" autoComplete="new-password" minLength={10} required value={f.nueva} onChange={(e) => setF({ ...f, nueva: e.target.value })} /></Field>
      <Field label="Repetir la nueva"><input type="password" autoComplete="new-password" required value={f.repetir} onChange={(e) => setF({ ...f, repetir: e.target.value })} /></Field>
      {noCoinciden && <div className="alert warning">Las contraseñas no coinciden</div>}
      <div><button className="primary" disabled={m.isPending || noCoinciden}>Cambiar contraseña</button></div>
    </form>
  );
}

function DosPasos() {
  const { usuario, refrescar } = useAuth();
  const [desactivando, setDesactivando] = useState(false);
  const [f, setF] = useState({ password: "", codigo: "" });
  const desactivar = useMutation({
    mutationFn: () => api("/auth/2fa/desactivar", { method: "POST", json: f }),
    onSuccess: () => { setDesactivando(false); refrescar(); },
  });

  return (
    <div className="card stack">
      <h2 style={{ margin: 0 }}>Verificación en dos pasos</h2>
      {usuario?.totp_activo ? (
        <>
          <div className="alert good">Activa. Al entrar te pedimos un código de tu app de autenticación.</div>
          {!desactivando ? (
            <div><button className="small" onClick={() => setDesactivando(true)}>Desactivar</button></div>
          ) : (
            <form className="stack" onSubmit={(e) => { e.preventDefault(); desactivar.mutate(); }}>
              <ErrorMsg error={desactivar.error} />
              <Field label="Contraseña"><input type="password" required value={f.password} onChange={(e) => setF({ ...f, password: e.target.value })} /></Field>
              <Field label="Código actual"><input inputMode="numeric" required value={f.codigo} onChange={(e) => setF({ ...f, codigo: e.target.value })} /></Field>
              <div className="row">
                <button type="button" onClick={() => setDesactivando(false)}>Cancelar</button>
                <button className="danger" disabled={desactivar.isPending}>Desactivar</button>
              </div>
            </form>
          )}
        </>
      ) : <Activar2FA />}
    </div>
  );
}

/** Alta de la verificación en dos pasos: muestra el QR y pide un código para confirmar. */
export function Activar2FA() {
  const { refrescar } = useAuth();
  const [codigo, setCodigo] = useState("");
  const inicio = useMutation({
    mutationFn: () => api<{ secreto: string; uri: string; qr_png: string }>("/auth/2fa/iniciar", { method: "POST" }),
  });
  const activar = useMutation({
    mutationFn: () => api("/auth/2fa/activar", { method: "POST", json: { codigo } }),
    onSuccess: () => refrescar(),
  });

  if (!inicio.data) {
    return (
      <div className="stack">
        <div className="muted">
          Además de la contraseña, al entrar se pide un código que genera una app en tu celular
          (Google Authenticator, Microsoft Authenticator, Authy, 1Password…).
        </div>
        <ErrorMsg error={inicio.error} />
        <div><button className="primary" onClick={() => inicio.mutate()} disabled={inicio.isPending}>Configurar</button></div>
      </div>
    );
  }
  return (
    <form className="stack" onSubmit={(e) => { e.preventDefault(); activar.mutate(); }}>
      <div>1. Escaneá este código con la app de autenticación:</div>
      <img src={`data:image/png;base64,${inicio.data.qr_png}`} alt="Código QR para la app de autenticación"
        style={{ width: 200, height: 200, imageRendering: "pixelated", background: "#fff", borderRadius: 6 }} />
      <details>
        <summary className="muted" style={{ cursor: "pointer" }}>¿No podés escanearlo? Cargá esta clave a mano</summary>
        <code style={{ wordBreak: "break-all" }}>{inicio.data.secreto}</code>
      </details>
      <ErrorMsg error={activar.error} />
      <Field label="2. Escribí el código de 6 dígitos que muestra la app">
        <input inputMode="numeric" autoComplete="one-time-code" required value={codigo} onChange={(e) => setCodigo(e.target.value)} />
      </Field>
      <div><button className="primary" disabled={activar.isPending}>Activar</button></div>
    </form>
  );
}

function Sesiones() {
  const qc = useQueryClient();
  const lista = useQuery({ queryKey: ["sesiones"], queryFn: () => api<SesionInfo[]>("/auth/sesiones") });
  const refrescar = () => qc.invalidateQueries({ queryKey: ["sesiones"] });
  const cerrar = useMutation({ mutationFn: (id: number) => api(`/auth/sesiones/${id}`, { method: "DELETE" }), onSuccess: refrescar });
  const cerrarOtras = useMutation({ mutationFn: () => api("/auth/sesiones/cerrar-otras", { method: "POST" }), onSuccess: refrescar });
  const otras = (lista.data ?? []).filter((s) => !s.actual).length;

  return (
    <div className="card stack">
      <div className="row" style={{ justifyContent: "space-between" }}>
        <h2 style={{ margin: 0 }}>Sesiones abiertas</h2>
        {otras > 0 && (
          <button className="small" onClick={() => cerrarOtras.mutate()} disabled={cerrarOtras.isPending}>
            Cerrar las otras {otras}
          </button>
        )}
      </div>
      <ErrorMsg error={cerrar.error ?? cerrarOtras.error} />
      {lista.isPending ? <Cargando /> : (
        <div className="table-wrap">
          <table>
            <thead><tr><th>Dispositivo</th><th>IP</th><th>Inicio</th><th>Último uso</th><th /></tr></thead>
            <tbody>
              {lista.data?.map((s) => (
                <tr key={s.id}>
                  <td>{navegador(s.user_agent)}{s.actual && <span className="badge good" style={{ marginLeft: 6 }}>Esta</span>}</td>
                  <td>{s.ip ?? "—"}</td>
                  <td>{fechaHora(s.creada)}</td>
                  <td>{fechaHora(s.ultima_actividad)}</td>
                  <td>{!s.actual && <button className="small" onClick={() => cerrar.mutate(s.id)}>Cerrar</button>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
