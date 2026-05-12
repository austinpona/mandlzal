import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Vite proxies /api -> FastAPI in dev so the browser never hits CORS.
// Override via VITE_API_TARGET / VITE_PORT (used by e2e tests).
const API_TARGET = process.env.VITE_API_TARGET || "http://127.0.0.1:8000";
const PORT = process.env.VITE_PORT ? Number(process.env.VITE_PORT) : 5173;

export default defineConfig({
  plugins: [react()],
  server: {
    port: PORT,
    strictPort: true,
    proxy: {
      "/api": {
        target: API_TARGET,
        changeOrigin: true,
        rewrite: (p: string) => p.replace(/^\/api/, ""),
      },
    },
  },
});
