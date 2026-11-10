import type { ReactNode } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { useAuth } from "./auth";
import { Cargando, ErrorMsg } from "./components/ui";
import Layout from "./components/Layout";
import Auditoria from "./pages/Auditoria";
import CartasPorte from "./pages/CartasPorte";
import Catalogos from "./pages/Catalogos";
import Cuenta, { Activar2FA } from "./pages/Cuenta";
import Dashboard from "./pages/Dashboard";
import FacturaDetalle from "./pages/FacturaDetalle";
import Facturas from "./pages/Facturas";
import Login from "./pages/Login";
import Reportes from "./pages/Reportes";
import Restablecer from "./pages/Restablecer";
import Usuarios from "./pages/Usuarios";
import type { Permiso } from "./types";

function Requiere({ permiso, children }: { permiso: Permiso; children: ReactNode }) {
  const { puede } = useAuth();
  return puede(permiso) ? children : <div className="empty">No tenés permiso para ver esta sección.</div>;
}

/** Primera sección a la que el usuario tiene acceso (el personal de campo no ve el dashboard). */
function Inicio() {
  const { puede } = useAuth();
  if (puede("reportes:ver")) return <Dashboard />;
  if (puede("facturas:leer")) return <Navigate to="/facturas" replace />;
  if (puede("cartas_porte:leer")) return <Navigate to="/cartas-porte" replace />;
  return <div className="empty">Tu usuario no tiene secciones asignadas.</div>;
}

/** El rol del usuario exige verificación en dos pasos y todavía no la configuró: no puede hacer otra cosa. */
function Exigir2FA() {
  const { logout } = useAuth();
  return (
    <div className="login">
      <div className="card stack" style={{ maxWidth: 440 }}>
        <h1>Activá la verificación en dos pasos</h1>
        <div className="muted">Tu rol tiene acceso a datos sensibles, así que para seguir hace falta configurarla.</div>
        <Activar2FA />
        <button className="link" onClick={logout}>Salir</button>
      </div>
    </div>
  );
}

export default function App() {
  const { usuario, cargando, error, reintentar } = useAuth();
  const { pathname } = useLocation();
  if (pathname === "/restablecer") return <Restablecer />;
  if (cargando) return <Cargando />;
  if (error) {
    return (
      <div className="login">
        <div className="card stack">
          <ErrorMsg error={error} />
          <button className="primary" onClick={reintentar}>Reintentar</button>
        </div>
      </div>
    );
  }
  if (!usuario) return <Login />;
  if (usuario.debe_activar_2fa) return <Exigir2FA />;

  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Inicio />} />
        <Route path="facturas" element={<Requiere permiso="facturas:leer"><Facturas /></Requiere>} />
        <Route path="facturas/:id" element={<Requiere permiso="facturas:leer"><FacturaDetalle /></Requiere>} />
        <Route path="cartas-porte" element={<Requiere permiso="cartas_porte:leer"><CartasPorte /></Requiere>} />
        <Route path="reportes" element={<Requiere permiso="reportes:ver"><Reportes /></Requiere>} />
        <Route path="catalogos" element={<Requiere permiso="catalogos:leer"><Catalogos /></Requiere>} />
        <Route path="usuarios" element={<Requiere permiso="usuarios:admin"><Usuarios /></Requiere>} />
        <Route path="auditoria" element={<Requiere permiso="auditoria:ver"><Auditoria /></Requiere>} />
        <Route path="cuenta" element={<Cuenta />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
