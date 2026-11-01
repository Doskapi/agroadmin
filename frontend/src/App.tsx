import type { ReactNode } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { useAuth } from "./auth";
import { Cargando } from "./components/ui";
import Layout from "./components/Layout";
import CartasPorte from "./pages/CartasPorte";
import Catalogos from "./pages/Catalogos";
import Dashboard from "./pages/Dashboard";
import FacturaDetalle from "./pages/FacturaDetalle";
import Facturas from "./pages/Facturas";
import Login from "./pages/Login";
import Reportes from "./pages/Reportes";
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

export default function App() {
  const { usuario, cargando } = useAuth();
  if (cargando) return <Cargando />;
  if (!usuario) return <Login />;

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
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
