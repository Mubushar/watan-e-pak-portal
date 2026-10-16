import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";

// In `npm run dev` the browser build talks to FastAPI through this proxy
// (`/api/*` -> `${VITE_API_TARGET}/*`). Packaged desktop/mobile builds call the
// backend URL directly (see src/lib/config.ts) — the backend allows CORS.
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const target = env.VITE_API_TARGET || "http://127.0.0.1:8000";
  const proxy = {
    "/api": { target, changeOrigin: true, rewrite: (p: string) => p.replace(/^\/api/, "") },
  };
  return {
    plugins: [react()],
    // Relative asset URLs so the same dist/ loads from Capacitor, Electron and a web server.
    base: "./",
    resolve: { alias: { "@": path.resolve(__dirname, "src") } },
    server: { port: 5174, proxy },
    preview: { port: 4174, proxy },
    build: {
      target: "es2020",
      chunkSizeWarningLimit: 900,
      rollupOptions: {
        output: { manualChunks: { react: ["react", "react-dom", "react-router-dom"], motion: ["framer-motion"] } },
      },
    },
  };
});
