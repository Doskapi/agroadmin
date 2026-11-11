import { useQuery } from "@tanstack/react-query";
import { Link, NavLink, Outlet } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";
import type { Permiso, Resumen } from "../types";

const LINKS: { to: string; texto: string; permiso: Permiso }[] = [
  { to: "/", texto: "Dashboard", permiso: "reportes:ver" },
  { to: "/facturas", texto: "Facturas", permiso: "facturas:leer" },
  { to: "/pagos", texto: "A pagar", permiso: "facturas:leer" },
  { to: "/arca", texto: "Conciliación ARCA", permiso: "facturas:leer" },
  { to: "/cartas-porte", texto: "Cartas de porte", permiso: "cartas_porte:leer" },
  { to: "/ventas", texto: "Ventas", permiso: "ventas:leer" },
  { to: "/reportes", texto: "Reportes", permiso: "reportes:ver" },
  { to: "/catalogos", texto: "Catálogos", permiso: "catalogos:leer" },
  { to: "/usuarios", texto: "Usuarios", permiso: "usuarios:admin" },
  { to: "/auditoria", texto: "Auditoría", permiso: "auditoria:ver" },
];

export default function Layout() {
  const { usuario, logout, puede } = useAuth();
  // Contador de facturas a revisar en el menú
  const resumen = useQuery({
    queryKey: ["resumen", {}],
    queryFn: () => api<Resumen>("/reportes/resumen"),
    enabled: puede("reportes:ver"),
  });
  const pendientes = resumen.data?.pendientes_revision ?? 0;

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">🌾 Gestión Agro</div>
        <nav className="nav">
          {LINKS.filter((l) => puede(l.permiso)).map((l) => (
            <NavLink key={l.to} to={l.to} end={l.to === "/"}>
              {l.texto}
              {l.to === "/facturas" && pendientes > 0 && (
                <span className="badge warning" title="Facturas a revisar">{pendientes}</span>
              )}
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-footer">
          <div style={{ fontWeight: 600 }}>{usuario?.nombre}</div>
          <div className="muted" style={{ marginBottom: 8 }}>{usuario?.roles.join(", ")}</div>
          <div className="row">
            <Link to="/cuenta" className="btn small">Mi cuenta</Link>
            <button className="small" onClick={logout}>Salir</button>
          </div>
        </div>
      </aside>
      <main className="main">
        <Outlet />
      </main>
    </div>
  );
}
