import { useQuery, useQueryClient } from "@tanstack/react-query";
import { createContext, useCallback, useContext, useEffect, useMemo, type ReactNode } from "react";
import { api, ApiError, setOnUnauthorized } from "./api";
import type { Permiso, Usuario } from "./types";

export type ResultadoLogin = { ok: true } | { ok: false; desafio: string };

interface AuthCtx {
  usuario: Usuario | null;
  cargando: boolean;
  /** Error que no es "no hay sesión" (ej. el servidor no responde) */
  error: unknown;
  reintentar: () => void;
  login: (email: string, password: string) => Promise<ResultadoLogin>;
  login2fa: (desafio: string, codigo: string) => Promise<void>;
  logout: () => Promise<void>;
  refrescar: () => Promise<unknown>;
  puede: (p: Permiso) => boolean;
}

const Ctx = createContext<AuthCtx | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const qc = useQueryClient();

  // La sesión vive en una cookie httpOnly: preguntamos al servidor quién somos.
  const yo = useQuery({
    queryKey: ["yo"],
    queryFn: async () => {
      try {
        return await api<Usuario>("/auth/yo");
      } catch (e) {
        if (e instanceof ApiError && e.status === 401) return null;
        throw e;
      }
    },
    retry: 1,
    staleTime: Infinity,
  });

  const sinSesion = useCallback(() => {
    qc.removeQueries({ predicate: (q) => q.queryKey[0] !== "yo" });
    qc.setQueryData(["yo"], null);
  }, [qc]);

  useEffect(() => setOnUnauthorized(sinSesion), [sinSesion]);

  const login = useCallback(async (email: string, password: string): Promise<ResultadoLogin> => {
    const body = new URLSearchParams({ username: email, password });
    const r = await api<{ requiere_2fa: boolean; desafio: string | null }>("/auth/login", { method: "POST", body });
    if (r.requiere_2fa && r.desafio) return { ok: false, desafio: r.desafio };
    await qc.invalidateQueries({ queryKey: ["yo"] });
    return { ok: true };
  }, [qc]);

  const login2fa = useCallback(async (desafio: string, codigo: string) => {
    await api("/auth/login/2fa", { method: "POST", json: { desafio, codigo } });
    await qc.invalidateQueries({ queryKey: ["yo"] });
  }, [qc]);

  const logout = useCallback(async () => {
    try {
      await api("/auth/logout", { method: "POST" });
    } finally {
      sinSesion();
    }
  }, [sinSesion]);

  const value = useMemo<AuthCtx>(() => {
    const usuario = yo.data ?? null;
    return {
      usuario,
      cargando: yo.isPending,
      error: yo.error,
      reintentar: () => yo.refetch(),
      login,
      login2fa,
      logout,
      refrescar: () => qc.invalidateQueries({ queryKey: ["yo"] }),
      puede: (p) => !!usuario?.permisos.includes(p) && !usuario.debe_activar_2fa,
    };
  }, [yo, login, login2fa, logout, qc]);

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useAuth() {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useAuth fuera de AuthProvider");
  return ctx;
}
