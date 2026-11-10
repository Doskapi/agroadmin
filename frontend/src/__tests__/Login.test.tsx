import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AuthProvider } from "../auth";
import Login from "../pages/Login";

const json = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

function montar() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <AuthProvider><Login /></AuthProvider>
    </QueryClientProvider>,
  );
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("Login", () => {
  it("pide el código de verificación cuando el usuario tiene dos pasos", async () => {
    const fetch = vi.fn(async (url: string, _init?: RequestInit) => {
      if (url === "/api/auth/yo") return json(401, { detail: "No autenticado" });
      if (url === "/api/auth/login") return json(200, { requiere_2fa: true, desafio: "d123", access_token: null });
      if (url === "/api/auth/login/2fa") return json(200, { requiere_2fa: false, access_token: null });
      throw new Error(`inesperado: ${url}`);
    });
    vi.stubGlobal("fetch", fetch);
    const { container } = montar();

    fireEvent.change(container.querySelector('input[type="email"]')!, { target: { value: "ana@test.com" } });
    fireEvent.change(container.querySelector('input[type="password"]')!, { target: { value: "clave-segura-1" } });
    await act(async () => fireEvent.click(screen.getByRole("button", { name: "Ingresar" })));

    expect(await screen.findByText("Verificación en dos pasos")).toBeTruthy();
    const login = fetch.mock.calls.find(([u]) => u === "/api/auth/login")!;
    expect(String(login[1]?.body)).toBe("username=ana%40test.com&password=clave-segura-1");

    fireEvent.change(container.querySelector('input[autocomplete="one-time-code"]')!, { target: { value: "123456" } });
    await act(async () => fireEvent.click(screen.getByRole("button", { name: "Verificar" })));
    const paso2 = fetch.mock.calls.find(([u]) => u === "/api/auth/login/2fa")!;
    expect(JSON.parse(String(paso2[1]?.body))).toEqual({ desafio: "d123", codigo: "123456" });
  });

  it("muestra el error si la contraseña es incorrecta", async () => {
    vi.stubGlobal("fetch", vi.fn(async (url: string) =>
      url === "/api/auth/yo" ? json(401, {}) : json(401, { detail: "Email o contraseña incorrectos" })));
    const { container } = montar();
    fireEvent.change(container.querySelector('input[type="email"]')!, { target: { value: "ana@test.com" } });
    fireEvent.change(container.querySelector('input[type="password"]')!, { target: { value: "mal" } });
    await act(async () => fireEvent.click(screen.getByRole("button", { name: "Ingresar" })));
    expect(await screen.findByText("Email o contraseña incorrectos")).toBeTruthy();
  });
});
