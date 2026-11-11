/** Cliente HTTP. La sesión viaja en una cookie httpOnly que pone el servidor (JavaScript no la ve). */

// Versiones anteriores guardaban el token en localStorage: se borra para no dejarlo expuesto.
try {
  localStorage.removeItem("agro_token");
} catch {
  /* sin almacenamiento */
}

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

let onUnauthorized: () => void = () => {};
export function setOnUnauthorized(fn: () => void) {
  onUnauthorized = fn;
}

function mensajeDeError(body: unknown, status: number): string {
  const detail = (body as { detail?: unknown })?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    // Errores de validación de FastAPI
    return detail
      .map((d: { loc?: unknown[]; msg?: string }) => `${(d.loc ?? []).slice(1).join(".")}: ${d.msg}`)
      .join("; ");
  }
  if (status === 502 || status === 503) return "El servidor no responde. Probá de nuevo en un momento";
  return `Error ${status}`;
}

async function request(path: string, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers);
  // La API exige este header en los pedidos con cookie que modifican datos (protección contra CSRF)
  headers.set("X-Requested-With", "agroadmin");
  if (init.body && !(init.body instanceof FormData) && !(init.body instanceof URLSearchParams)) {
    headers.set("Content-Type", "application/json");
  }
  let res: Response;
  try {
    res = await fetch(`/api${path}`, { ...init, headers, credentials: "same-origin" });
  } catch {
    throw new ApiError(0, "Sin conexión con el servidor. Revisá internet y probá de nuevo");
  }
  if (res.status === 401 && !path.startsWith("/auth/login")) onUnauthorized();
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new ApiError(res.status, mensajeDeError(body, res.status));
  }
  return res;
}

export async function api<T>(path: string, init: RequestInit & { json?: unknown } = {}): Promise<T> {
  const { json, ...rest } = init;
  const res = await request(path, json !== undefined ? { ...rest, body: JSON.stringify(json) } : rest);
  if (res.status === 204 || res.status === 202 && res.headers.get("content-length") === "0") return undefined as T;
  return res.json();
}

export async function apiBlob(path: string): Promise<Blob> {
  return (await request(path)).blob();
}

/** Arma un query string ignorando valores vacíos. */
export function qs(params: Record<string, string | number | boolean | null | undefined>): string {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== "") p.set(k, String(v));
  }
  const s = p.toString();
  return s ? `?${s}` : "";
}

export async function descargar(path: string, nombre: string) {
  const blob = await apiBlob(path);
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = nombre;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
