import { useState, type FormEvent } from "react";
import { api } from "../api";
import { useAuth } from "../auth";
import { ErrorMsg, Field } from "../components/ui";

type Paso = { tipo: "password" } | { tipo: "codigo"; desafio: string } | { tipo: "recuperar" } | { tipo: "enviado"; mensaje: string };

export default function Login() {
  const { login, login2fa } = useAuth();
  const [paso, setPaso] = useState<Paso>({ tipo: "password" });
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [codigo, setCodigo] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [enviando, setEnviando] = useState(false);

  async function enviar(e: FormEvent, accion: () => Promise<void>) {
    e.preventDefault();
    setEnviando(true);
    setError(null);
    try {
      await accion();
    } catch (err) {
      setError(err);
    } finally {
      setEnviando(false);
    }
  }

  const titulo = (
    <div>
      <h1>🌾 Gestión Agro</h1>
      <div className="muted">
        {paso.tipo === "codigo" ? "Verificación en dos pasos"
          : paso.tipo === "recuperar" || paso.tipo === "enviado" ? "Recuperar la contraseña" : "Ingresá con tu usuario"}
      </div>
    </div>
  );

  if (paso.tipo === "codigo") {
    return (
      <div className="login">
        <form className="card stack" onSubmit={(e) => enviar(e, () => login2fa(paso.desafio, codigo))}>
          {titulo}
          <ErrorMsg error={error} />
          <Field label="Código de 6 dígitos de tu app de autenticación">
            <input inputMode="numeric" autoComplete="one-time-code" pattern="[0-9 ]{6,8}" required autoFocus
              value={codigo} onChange={(e) => setCodigo(e.target.value)} />
          </Field>
          <button className="primary" disabled={enviando}>{enviando ? "Verificando…" : "Verificar"}</button>
          <button type="button" className="link" onClick={() => { setPaso({ tipo: "password" }); setCodigo(""); setError(null); }}>
            ← Volver
          </button>
        </form>
      </div>
    );
  }

  if (paso.tipo === "recuperar" || paso.tipo === "enviado") {
    return (
      <div className="login">
        <form className="card stack" onSubmit={(e) => enviar(e, async () => {
          const r = await api<{ detail: string }>("/auth/recuperar", { method: "POST", json: { email } });
          setPaso({ tipo: "enviado", mensaje: r.detail });
        })}>
          {titulo}
          <ErrorMsg error={error} />
          {paso.tipo === "enviado" ? <div className="alert good">{paso.mensaje}</div> : (
            <>
              <Field label="Email">
                <input type="email" autoComplete="username" required value={email} onChange={(e) => setEmail(e.target.value)} autoFocus />
              </Field>
              <button className="primary" disabled={enviando}>{enviando ? "Enviando…" : "Enviarme un link"}</button>
            </>
          )}
          <button type="button" className="link" onClick={() => { setPaso({ tipo: "password" }); setError(null); }}>← Volver</button>
          <div className="muted" style={{ fontSize: 12 }}>
            Si no te llega el correo, pedile a un administrador que te cambie la contraseña.
          </div>
        </form>
      </div>
    );
  }

  return (
    <div className="login">
      <form className="card stack" onSubmit={(e) => enviar(e, async () => {
        const r = await login(email, password);
        if (!r.ok) setPaso({ tipo: "codigo", desafio: r.desafio });
      })}>
        {titulo}
        <ErrorMsg error={error} />
        <Field label="Email">
          <input type="email" autoComplete="username" required value={email} onChange={(e) => setEmail(e.target.value)} autoFocus />
        </Field>
        <Field label="Contraseña">
          <input type="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} />
        </Field>
        <button className="primary" disabled={enviando}>{enviando ? "Ingresando…" : "Ingresar"}</button>
        <button type="button" className="link" onClick={() => { setPaso({ tipo: "recuperar" }); setError(null); }}>
          ¿Olvidaste tu contraseña?
        </button>
      </form>
    </div>
  );
}
