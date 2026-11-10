import { afterEach, describe, expect, it, vi } from "vitest";
import { api, ApiError, qs, setOnUnauthorized } from "../api";

const respuesta = (status: number, body: unknown) =>
  new Response(body === undefined ? null : JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

afterEach(() => vi.unstubAllGlobals());

describe("qs", () => {
  it("ignora los valores vacíos", () => {
    expect(qs({ a: 1, b: "", c: null, d: undefined, e: false })).toBe("?a=1&e=false");
    expect(qs({})).toBe("");
  });
});

describe("api", () => {
  it("manda el header anti-CSRF y la cookie, y el cuerpo como JSON", async () => {
    const fetch = vi.fn().mockResolvedValue(respuesta(200, { ok: true }));
    vi.stubGlobal("fetch", fetch);
    await api("/facturas", { method: "POST", json: { total: 1 } });
    const [url, init] = fetch.mock.calls[0];
    expect(url).toBe("/api/facturas");
    expect(init.credentials).toBe("same-origin");
    expect(init.headers.get("X-Requested-With")).toBe("agroadmin");
    expect(init.headers.get("Content-Type")).toBe("application/json");
    expect(init.body).toBe('{"total":1}');
  });

  it("avisa cuando la sesión venció (401)", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(respuesta(401, { detail: "Sesión vencida" })));
    const vencida = vi.fn();
    setOnUnauthorized(vencida);
    await expect(api("/facturas")).rejects.toThrow("Sesión vencida");
    expect(vencida).toHaveBeenCalledOnce();
  });

  it("no trata un login fallido como sesión vencida", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(respuesta(401, { detail: "Email o contraseña incorrectos" })));
    const vencida = vi.fn();
    setOnUnauthorized(vencida);
    await expect(api("/auth/login", { method: "POST" })).rejects.toBeInstanceOf(ApiError);
    expect(vencida).not.toHaveBeenCalled();
  });

  it("convierte los errores de validación de FastAPI en un mensaje legible", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(respuesta(422, {
      detail: [{ loc: ["body", "imputaciones", 0, "porcentaje"], msg: "Input should be greater than 0" }],
    })));
    await expect(api("/facturas/1", { method: "PATCH", json: {} })).rejects.toThrow(
      "imputaciones.0.porcentaje: Input should be greater than 0");
  });

  it("explica cuando el servidor no responde", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("<html>", { status: 502 })));
    await expect(api("/facturas")).rejects.toThrow("El servidor no responde");
  });
});
