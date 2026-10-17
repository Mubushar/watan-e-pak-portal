import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";

// Every backend call goes through Vite's proxy (`/api/*` -> `${API_TARGET}/*`), so the
// portal is same-origin in development and needs no CORS set-up. `/media` serves
// uploaded listing photos and `/ads.txt` is the AdSense file Google expects at the root.
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const target = env.VITE_API_TARGET || "http://127.0.0.1:8000";
  return {
    plugins: [react()],
    resolve: { alias: { "@": path.resolve(__dirname, "src") } },
    server: {
      port: 5173,
      proxy: {
        "/api": {
          target,
          changeOrigin: true,
          ws: true,
          rewrite: (p) => p.replace(/^\/api/, ""),
        },
        "/media": { target, changeOrigin: true },
        "/ads.txt": { target, changeOrigin: true },
      },
    },
    preview: {
      port: 4173,
      proxy: {
        "/api": { target, changeOrigin: true, ws: true, rewrite: (p) => p.replace(/^\/api/, "") },
        "/media": { target, changeOrigin: true },
        "/ads.txt": { target, changeOrigin: true },
      },
    },
    build: {
      chunkSizeWarningLimit: 1200,
      rollupOptions: {
        output: {
          manualChunks: {
            react: ["react", "react-dom", "react-router-dom"],
            charts: ["recharts"],
            map: ["leaflet", "react-leaflet"],
            motion: ["framer-motion"],
          },
        },
      },
    },
  };
});
