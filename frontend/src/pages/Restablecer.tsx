import { useState, type FormEvent } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { api } from "../api";
import { ErrorMsg, Field } from "../components/ui";

/** Página pública a la que lleva el link del correo de recuperación. */
export default function Restablecer() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const [nueva, setNueva] = useState("");
  const [repetir, setRepetir] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [listo, setListo] = useState(false);
  const [enviando, setEnviando] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (nueva !== repetir) return setError(new Error("Las contraseñas no coinciden"));
    setEnviando(true);
    setError(null);
    try {
      await api("/auth/restablecer", { method: "POST", json: { token: params.get("token") ?? "", nueva } });
      setListo(true);
    } catch (err) {
      setError(err);
    } finally {
      setEnviando(false);
    }
  }

  return (
    <div className="login">
      <form className="card stack" onSubmit={onSubmit}>
        <div>
          <h1>🌾 Gestión Agro</h1>
          <div className="muted">Elegí una contraseña nueva</div>
        </div>
        <ErrorMsg error={error} />
        {listo ? (
          <>
            <div className="alert good">Listo. Ya podés entrar con tu contraseña nueva.</div>
            <button type="button" className="primary" onClick={() => navigate("/", { replace: true })}>Ir a ingresar</button>
          </>
        ) : (
          <>
            <Field label="Contraseña nueva (10 caracteres o más)">
              <input type="password" autoComplete="new-password" minLength={10} required value={nueva} onChange={(e) => setNueva(e.target.value)} autoFocus />
            </Field>
            <Field label="Repetila">
              <input type="password" autoComplete="new-password" minLength={10} required value={repetir} onChange={(e) => setRepetir(e.target.value)} />
            </Field>
            <button className="primary" disabled={enviando}>Guardar</button>
          </>
        )}
      </form>
    </div>
  );
}
