import { Link } from "react-router-dom";
import type { EntradaAuditoria } from "../types";

export const ACCIONES: Record<string, string> = {
  login: "Ingresó", login_fallido: "Intento de ingreso fallido", logout: "Salió",
  sesion_cerrada: "Cerró una sesión", sesiones_cerradas: "Cerró sus otras sesiones",
  password_cambiada: "Cambió su contraseña", recuperacion_pedida: "Pidió recuperar la contraseña",
  password_restablecida: "Restableció la contraseña", "2fa_activada": "Activó la verificación en dos pasos",
  "2fa_desactivada": "Desactivó la verificación en dos pasos", "2fa_reiniciada": "Reinició la verificación en dos pasos",
  usuario_creado: "Creó un usuario", usuario_editado: "Editó un usuario", rol_guardado: "Modificó un rol",
  factura_creada: "Cargó la factura", factura_procesada: "Leyó el comprobante", factura_editada: "Editó la factura",
  factura_confirmada: "Confirmó la factura", factura_anulada: "Anuló la factura", factura_reprocesada: "Pidió volver a leer",
  catalogo_guardado: "Guardó un registro de catálogo",
};

export const fechaHora = (v: string) => new Date(v).toLocaleString("es-AR", { dateStyle: "short", timeStyle: "medium" });

const valor = (v: unknown) => (v === null || v === undefined || v === "" ? "vacío" : Array.isArray(v) ? JSON.stringify(v) : String(v));

/** Resumen legible del detalle de una entrada de auditoría. */
export function DetalleAuditoria({ e }: { e: EntradaAuditoria }) {
  const d = e.detalle ?? {};
  const partes: string[] = [];
  if (d.cambios && typeof d.cambios === "object") {
    for (const [k, par] of Object.entries(d.cambios as Record<string, unknown>)) {
      if (Array.isArray(par) && par.length === 2) partes.push(`${k}: ${valor(par[0])} → ${valor(par[1])}`);
      else partes.push(`${k}: ${valor(par)}`);
    }
  }
  if (d.motivo) partes.push(`Motivo: ${d.motivo}`);
  if (d.email && e.accion === "login_fallido") partes.push(`Email: ${d.email}`);
  if (Array.isArray(d.advertencias) && d.advertencias.length) partes.push(`Advertencias: ${d.advertencias.join("; ")}`);
  if (Array.isArray(d.fuentes)) partes.push(`Fuentes: ${(d.fuentes as string[]).join(", ") || "ninguna"}`);
  if (d.origen) partes.push(d.origen === "importacion" ? `Importada (${d.archivo ?? "archivo"})` : "Carga manual");
  if (d.masiva) partes.push("(acción masiva)");
  return <span style={{ fontSize: 13 }}>{partes.join(" · ")}</span>;
}

export function LinkEntidad({ e }: { e: EntradaAuditoria }) {
  if (e.entidad === "factura" && e.entidad_id) return <Link to={`/facturas/${e.entidad_id}`}>Factura #{e.entidad_id}</Link>;
  if (!e.entidad) return null;
  return <span>{e.entidad} {e.entidad_id ? `#${e.entidad_id}` : ""}</span>;
}
