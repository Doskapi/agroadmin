import { useState, type FormEvent } from "react";
import { useAuth } from "../auth";
import { ErrorMsg, Field } from "../components/ui";

export default function Login() {
  const { login } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [enviando, setEnviando] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setEnviando(true);
    setError(null);
    try {
      await login(email, password);
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
          <div className="muted">Ingresá con tu usuario</div>
        </div>
        <ErrorMsg error={error} />
        <Field label="Email">
          <input type="email" autoComplete="username" required value={email} onChange={(e) => setEmail(e.target.value)} autoFocus />
        </Field>
        <Field label="Contraseña">
          <input type="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} />
        </Field>
        <button className="primary" disabled={enviando}>{enviando ? "Ingresando…" : "Ingresar"}</button>
      </form>
    </div>
  );
}
