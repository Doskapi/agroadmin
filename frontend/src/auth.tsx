import { useQuery, useQueryClient } from "@tanstack/react-query";
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { api, getToken, setOnUnauthorized, setToken } from "./api";
import type { Permiso, Usuario } from "./types";

interface AuthCtx {
  usuario: Usuario | null;
  cargando: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
  puede: (p: Permiso) => boolean;
}

const Ctx = createContext<AuthCtx | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const qc = useQueryClient();
  const [token, setTok] = useState(getToken);

  const logout = useCallback(() => {
    setToken(null);
    setTok(null);
    qc.clear();
  }, [qc]);

  useEffect(() => setOnUnauthorized(logout), [logout]);

  const yo = useQuery({
    queryKey: ["yo", token],
    queryFn: () => api<Usuario>("/auth/yo"),
    enabled: !!token,
    retry: false,
  });

  const login = useCallback(async (email: string, password: string) => {
    const body = new URLSearchParams({ username: email, password });
    const { access_token } = await api<{ access_token: string }>("/auth/login", { method: "POST", body });
    setToken(access_token);
    setTok(access_token);
  }, []);

  const value = useMemo<AuthCtx>(() => {
    const usuario = token ? (yo.data ?? null) : null;
    return {
      usuario,
      cargando: !!token && yo.isPending,
      login,
      logout,
      puede: (p) => !!usuario?.permisos.includes(p),
    };
  }, [token, yo.data, yo.isPending, login, logout]);

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useAuth() {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useAuth fuera de AuthProvider");
  return ctx;
}
