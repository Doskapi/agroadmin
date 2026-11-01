import { useQuery } from "@tanstack/react-query";
import { api } from "./api";
import type { Campania, Campo, Categoria, Proveedor } from "./types";

// Catálogos chicos que se usan en muchos formularios: se cachean 5 minutos.
const opts = { staleTime: 5 * 60_000 };

export const useProveedores = () =>
  useQuery({ queryKey: ["proveedores"], queryFn: () => api<Proveedor[]>("/proveedores"), ...opts });
export const useCampos = () => useQuery({ queryKey: ["campos"], queryFn: () => api<Campo[]>("/campos"), ...opts });
export const useCampanias = () =>
  useQuery({ queryKey: ["campanias"], queryFn: () => api<Campania[]>("/campanias"), ...opts });
export const useCategorias = () =>
  useQuery({ queryKey: ["categorias"], queryFn: () => api<Categoria[]>("/categorias"), ...opts });
