import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// En desarrollo, /api se redirige al backend (localhost:8000, o `api:8000` dentro de docker compose).
const backend = process.env.API_URL ?? "http://localhost:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": { target: backend, rewrite: (p) => p.replace(/^\/api/, "") },
    },
  },
});
