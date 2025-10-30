import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const API_TARGET = process.env.VITE_API_PROXY || "http://127.0.0.1:8082";
const PUBLIC_HOST = process.env.VITE_PUBLIC_HOST || undefined;

export default defineConfig({
  plugins: [react()],
  server: {
    host: "0.0.0.0",
    port: 5173,
    proxy: {
      "/nerdle": { target: API_TARGET, changeOrigin: true },
      "/health": { target: API_TARGET, changeOrigin: true },
    },
    hmr: PUBLIC_HOST ? { host: PUBLIC_HOST } : true,
  },
  preview: {
    host: "0.0.0.0",
    port: 5173,
  },
});
