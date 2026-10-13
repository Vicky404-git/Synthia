/// <reference types="vitest" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The backend base URL is injected at build time via VITE_API_BASE_URL.
// During local development we proxy API calls to the FastAPI server so the
// frontend can use relative URLs.
const backendTarget = process.env.VITE_DEV_BACKEND ?? "http://localhost:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    port: 5173,
    proxy: {
      "/api": { target: backendTarget, changeOrigin: true },
      "/health": { target: backendTarget, changeOrigin: true },
      "/ready": { target: backendTarget, changeOrigin: true },
    },
  },
  preview: {
    host: true,
    port: 4173,
  },
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    css: false,
  },
});
